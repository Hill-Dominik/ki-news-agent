"""
bewertung.py - Ruft die Anthropic API auf, um pro Kandidat:
- eine Kernaussage (Zusammenfassung) zu erzeugen
- eine Kategorie zuzuordnen
- die Relevanz nach der festen Drei-Stufen-Regel einzuschaetzen
- inhaltliche Duplikate gegenueber den letzten Tagen zu erkennen (Dedup Stufe 2)

Nutzt Claude Haiku 4.5 - das guenstigste Modell, reicht fuer diese Aufgabe
locker (Zusammenfassung/Klassifikation, keine komplexe Analyse).
"""

import os

import anthropic

from utils import parse_json_antwort

MODELL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """Du bewertest KI-News fuer eine automatisierte Datenbank. \
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, kein Fliesstext, keine Markdown-Codebloecke.

Relevanz-Regel (strikt anwenden):
- "Hoch": Groessere Modell-Releases namhafter Anbieter, regulatorische Entscheidungen \
mit breiter Wirkung, mehrfach unabhaengig bestaetigte Durchbrueche.
- "Mittel": Feature-Updates, kleinere Tool-Releases, Studien ohne grosse \
Oeffentlichkeitswirkung.
- "Niedrig": Meinungsartikel, Spekulation/Geruechte, reine Marketinginhalte, \
nischige Detail-Updates.

Gib genau folgendes JSON-Format zurueck:
{
  "ist_duplikat": true/false,
  "kernaussage": "1-2 Saetze auf Deutsch, worum es inhaltlich geht",
  "kategorie": "kurzes Themen-Label, z.B. 'Modell-Release', 'Regulierung', 'Forschung'",
  "relevanz": "Hoch" | "Mittel" | "Niedrig",
  "begruendung_relevanz": "ein Satz, warum diese Einstufung"
}

"ist_duplikat" ist true, wenn der Artikel inhaltlich (nicht nur per URL) \
dieselbe Story wie einer der genannten kuerzlichen Titel behandelt."""


def bewerte_artikel(kandidat: dict, letzte_titel: list[str]) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_content = (
        f"Titel: {kandidat['titel']}\n"
        f"Auszug: {kandidat.get('roher_text', '')[:1500]}\n\n"
        f"Kuerzlich bereits gespeicherte Titel (letzte Tage):\n"
        + "\n".join(f"- {t}" for t in letzte_titel[:50])
    )

    response = client.messages.create(
        model=MODELL,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Nur Text-Bloecke rausfiltern - Claude kann zusaetzlich ThinkingBlocks
    # zurueckgeben, die keinen .text haben (siehe Bug in weekly_summary.py).
    text_bloecke = [b.text for b in response.content if b.type == "text"]
    return parse_json_antwort("\n".join(text_bloecke))


# --- Gebuendelte Bewertung (seit 23.11.2026, Kostensenkung) ---------------
# Statt einem API-Aufruf pro Artikel werden bis zu PAKET_GROESSE Artikel in
# einem Aufruf bewertet. Systemprompt und die Liste der letzten Titel werden
# so nur einmal pro Paket statt einmal pro Artikel bezahlt.

PAKET_GROESSE = 10

BATCH_ZUSATZ = """

Du bekommst diesmal MEHRERE nummerierte Artikel. Bewerte jeden einzeln nach \
denselben Regeln. Antworte AUSSCHLIESSLICH mit einem JSON-Array, ein Objekt \
pro Artikel, jeweils mit dem zusaetzlichen Feld "nr" (die Nummer des Artikels):
[{"nr": 1, "ist_duplikat": ..., "kernaussage": ..., "kategorie": ..., \
"relevanz": ..., "begruendung_relevanz": ...}, ...]

"ist_duplikat" ist auch true, wenn ein Artikel dieselbe Story wie ein \
FRUEHERER Artikel in derselben Liste behandelt (der erste bleibt false)."""

PFLICHTFELDER = ("kernaussage", "kategorie", "relevanz", "begruendung_relevanz")


def _bewerte_paket(paket: list[dict], letzte_titel: list[str]) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    artikel_text = "\n\n".join(
        f"[{nr}] Titel: {k['titel']}\nAuszug: {k.get('roher_text', '')[:1500]}"
        for nr, k in enumerate(paket, start=1)
    )
    user_content = (
        f"{artikel_text}\n\n"
        f"Kuerzlich bereits gespeicherte Titel (letzte Tage):\n"
        + "\n".join(f"- {t}" for t in letzte_titel[-50:])  # neueste zuerst mitnehmen
    )

    response = client.messages.create(
        model=MODELL,
        max_tokens=400 * len(paket),
        system=SYSTEM_PROMPT + BATCH_ZUSATZ,
        messages=[{"role": "user", "content": user_content}],
    )
    print(f"  Paket ({len(paket)} Artikel): {response.usage.input_tokens} Input-, "
          f"{response.usage.output_tokens} Output-Tokens")

    text_bloecke = [b.text for b in response.content if b.type == "text"]
    ergebnis = parse_json_antwort("\n".join(text_bloecke))

    nach_nr = {int(e["nr"]): e for e in ergebnis if isinstance(e, dict) and "nr" in e}
    bewertungen = []
    for nr in range(1, len(paket) + 1):
        b = nach_nr.get(nr)
        if not b or any(not b.get(f) for f in PFLICHTFELDER):
            raise ValueError(f"Bewertung fuer Artikel {nr} fehlt oder ist unvollstaendig.")
        bewertungen.append(b)
    return bewertungen


def bewerte_artikel_gebuendelt(kandidaten: list[dict], letzte_titel: list[str]) -> list[dict | None]:
    """
    Bewertet alle Kandidaten in Paketen. Gibt eine Liste in derselben
    Reihenfolge zurueck (None = Bewertung fehlgeschlagen). Schlaegt ein Paket
    fehl, werden dessen Artikel einzeln nachbewertet - so geht nie ein ganzer
    Tag verloren.
    """
    titel_bisher = list(letzte_titel)
    alle = []
    for start in range(0, len(kandidaten), PAKET_GROESSE):
        paket = kandidaten[start:start + PAKET_GROESSE]
        try:
            bewertungen = _bewerte_paket(paket, titel_bisher)
        except Exception as e:
            print(f"  Paket fehlgeschlagen ({e}) - bewerte diese Artikel einzeln.")
            bewertungen = []
            for k in paket:
                try:
                    bewertungen.append(bewerte_artikel(k, titel_bisher))
                except Exception as e2:
                    print(f"  Fehler bei Einzelbewertung '{k['titel'][:60]}': {e2}")
                    bewertungen.append(None)
        # Titel dieses Pakets fuer die Duplikatpruefung der naechsten Pakete merken
        for k, b in zip(paket, bewertungen):
            if b and not b.get("ist_duplikat"):
                titel_bisher.append(k["titel"])
        alle.extend(bewertungen)
    return alle
