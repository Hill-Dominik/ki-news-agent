"""
weekly_summary.py - Erzeugt einmal woechentlich eine strukturierte
Zusammenfassung der wichtigsten News der letzten 7 Tage und speichert sie
in der Tabelle wochenrueckblicke.

Laeuft komplett unabhaengig vom taeglichen Sammel-Workflow (main.py) -
reiner Lesezugriff auf news_eintraege, kein Eingriff in die laufende
Pipeline. Nutzt Sonnet statt Haiku fuer bessere sprachliche Kohaerenz
im Fliesstext (laeuft nur 1x/Woche, Kostenunterschied vernachlaessigbar).
"""

import os
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

import anthropic

from db import get_client
from utils import parse_json_antwort

MODELL = "claude-sonnet-5"

SYSTEM_PROMPT = """Du schreibst einen woechentlichen KI-News-Rueckblick auf Deutsch. \
Du bekommst eine Liste von News-Eintraegen der letzten 7 Tage, gruppiert nach Kategorie.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt (kein Markdown-Codefence \
drumherum), mit genau zwei Feldern:

{
  "text": "Der volle Rueckblick als Markdown, siehe Struktur unten",
  "teaser": "Kurze 3-4-Saetze-Fassung als reiner Fliesstext (kein Markdown), fuer Telegram"
}

Struktur von "text":
- Eine kurze Einleitung (1-2 Saetze), was die Woche insgesamt gepraegt hat
- Pro Kategorie eine Ueberschrift (##) mit Bullet-Points zu den wichtigsten
  Eintraegen dieser Kategorie (kurz, praegnant, kein reines Abschreiben der
  Kernaussagen)

"teaser": Fasst die 1-2 wichtigsten Ereignisse der Woche zusammen, ohne
Markdown-Formatierung, damit es direkt als Chat-Nachricht lesbar ist.

Schreibstil: sachlich, kompakt, fuer ein Fachpublikum (IT/KI-affin)."""


def hole_eintraege_der_woche(client, tage: int = 7) -> list[dict]:
    grenze = (date.today() - timedelta(days=tage)).isoformat()
    result = (
        client.table("news_eintraege")
        .select("titel, kernaussage, relevanz, datum, kategorien(name)")
        .gte("datum", grenze)
        .in_("relevanz", ["Hoch", "Mittel"])
        .order("datum", desc=True)
        .execute()
    )
    return result.data


def gruppiere_nach_kategorie(eintraege: list[dict]) -> dict[str, list[dict]]:
    gruppen: dict[str, list[dict]] = {}
    for e in eintraege:
        kategorie = e["kategorien"]["name"] if e.get("kategorien") else "Sonstiges"
        gruppen.setdefault(kategorie, []).append(e)
    return gruppen


def formatiere_fuer_prompt(gruppen: dict[str, list[dict]]) -> str:
    zeilen = []
    for kategorie, eintraege in gruppen.items():
        zeilen.append(f"\n## {kategorie}")
        for e in eintraege:
            zeilen.append(f"- [{e['relevanz']}] {e['titel']}: {e['kernaussage']}")
    return "\n".join(zeilen)


def generiere_rueckblick(rohdaten: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODELL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": rohdaten}],
    )
    return parse_json_antwort(response.content[0].text)


def main():
    client = get_client()

    eintraege = hole_eintraege_der_woche(client)
    print(f"{len(eintraege)} Eintraege (Hoch+Mittel) der letzten 7 Tage gefunden.")

    if not eintraege:
        print("Keine Eintraege, kein Rueckblick generiert.")
        return

    gruppen = gruppiere_nach_kategorie(eintraege)
    rohdaten = formatiere_fuer_prompt(gruppen)
    ergebnis = generiere_rueckblick(rohdaten)

    heute = date.today()
    datum_von = heute - timedelta(days=7)

    client.table("wochenrueckblicke").insert({
        "datum_von": datum_von.isoformat(),
        "datum_bis": heute.isoformat(),
        "text": ergebnis["text"],
        "teaser": ergebnis["teaser"],
    }).execute()

    print("Wochenrueckblick gespeichert.")


if __name__ == "__main__":
    main()
