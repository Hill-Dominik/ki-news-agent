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

    return parse_json_antwort(response.content[0].text)
