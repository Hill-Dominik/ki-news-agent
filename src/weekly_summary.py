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
from utils import parse_json_antwort, hole_eintraege, gruppiere_nach_kategorie, formatiere_fuer_prompt

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


def generiere_rueckblick(rohdaten: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODELL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": rohdaten}],
    )
    # Nur Text-Bloecke rausfiltern - Sonnet kann zusaetzlich ThinkingBlocks
    # zurueckgeben, die keinen .text haben.
    text_bloecke = [b.text for b in response.content if b.type == "text"]
    return parse_json_antwort("\n".join(text_bloecke))


def main():
    client = get_client()

    eintraege = hole_eintraege(client, tage=7, relevanz_filter=["Hoch", "Mittel"])
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
