"""
main.py - Orchestriert einen kompletten Lauf des KI-News-Agenten:

1) Kandidaten sammeln (RSS-Prioritaetsquellen + ergaenzende Google-Suche)
2) Dedup Stufe 1: URL-Exact-Match gegen die Datenbank
3) Pro verbliebenem Kandidaten: Claude-Bewertung (inkl. Dedup Stufe 2)
4) Nicht-Duplikate mit Zusammenfassung/Kategorie/Relevanz in die DB schreiben

Wird taeglich per GitHub Actions ausgefuehrt (.github/workflows/daily_run.yml),
kann aber genauso gut lokal mit "python src/main.py" laufen.
"""

from datetime import date

from dotenv import load_dotenv

# Laedt eine lokale .env falls vorhanden. In GitHub Actions ohne Wirkung,
# da die Secrets dort bereits als echte Umgebungsvariablen gesetzt sind.
load_dotenv()

from db import (
    get_client,
    get_or_create_quelle,
    get_or_create_kategorie,
    quelle_info_from_domain,
    artikel_existiert,
    get_letzte_titel,
    speichere_eintrag,
)
from sources import lade_config, hole_rss_kandidaten, hole_web_suche_kandidaten
from bewertung import bewerte_artikel


def main():
    client = get_client()
    config = lade_config()

    # Prioritaetsquellen einmalig in der DB sicherstellen (upsert-artig)
    for quelle in config["rss_quellen"]:
        get_or_create_quelle(client, quelle["name"], quelle["url"])

    kandidaten = hole_rss_kandidaten(config["rss_quellen"])
    kandidaten += hole_web_suche_kandidaten(config.get("suchanfragen", []))
    print(f"{len(kandidaten)} Kandidaten gefunden.")

    # Dedup innerhalb des aktuellen Laufs: RSS und Websuche koennen zufaellig
    # denselben Artikel liefern - ohne diesen Schritt wuerde der zweite Fund
    # beim Speichern gegen die Unique-Constraint auf artikel_url knallen.
    gesehene_urls = set()
    eindeutige_kandidaten = []
    for k in kandidaten:
        if k["artikel_url"] and k["artikel_url"] not in gesehene_urls:
            gesehene_urls.add(k["artikel_url"])
            eindeutige_kandidaten.append(k)
    kandidaten = eindeutige_kandidaten
    print(f"{len(kandidaten)} nach Dedup innerhalb des Laufs.")

    # Dedup Stufe 1: URL-Exact-Match gegen die Datenbank
    neue_kandidaten = [
        k for k in kandidaten
        if k["artikel_url"] and not artikel_existiert(client, k["artikel_url"])
    ]
    print(f"{len(neue_kandidaten)} nach URL-Dedup gegen DB uebrig.")

    letzte_titel = get_letzte_titel(client, tage=3)
    gespeichert = 0

    for i, kandidat in enumerate(neue_kandidaten, start=1):
        print(f"Bewerte {i}/{len(neue_kandidaten)}: {kandidat['titel'][:70]}")
        try:
            bewertung = bewerte_artikel(kandidat, letzte_titel)
        except Exception as e:
            print(f"  Fehler bei Bewertung: {e}")
            continue

        if bewertung.get("ist_duplikat"):
            print("  -> Duplikat (inhaltlich), uebersprungen")
            continue

        if kandidat["quelle_name"] and kandidat["quelle_url"]:
            quelle_name, quelle_url = kandidat["quelle_name"], kandidat["quelle_url"]
        else:
            quelle_name, quelle_url = quelle_info_from_domain(kandidat["artikel_url"])

        quelle_id = get_or_create_quelle(client, quelle_name, quelle_url)
        kategorie_id = get_or_create_kategorie(client, bewertung["kategorie"])

        try:
            speichere_eintrag(client, {
                "datum": date.today().isoformat(),
                "titel": kandidat["titel"],
                "kernaussage": bewertung["kernaussage"],
                "artikel_url": kandidat["artikel_url"],
                "quelle_id": quelle_id,
                "kategorie_id": kategorie_id,
                "relevanz": bewertung["relevanz"],
                "zusatzdaten": {"begruendung_relevanz": bewertung["begruendung_relevanz"]},
            })
            gespeichert += 1
        except Exception as e:
            print(f"  Fehler beim Speichern: {e}")
            continue

        letzte_titel.append(kandidat["titel"])  # fuer Dedup innerhalb desselben Laufs

    print(f"{gespeichert} neue Eintraege gespeichert.")


if __name__ == "__main__":
    main()
