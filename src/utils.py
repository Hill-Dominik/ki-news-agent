"""
utils.py - Kleine Hilfsfunktionen, die von mehreren Modulen gebraucht werden.

hole_eintraege / gruppiere_nach_kategorie / formatiere_fuer_prompt werden
gemeinsam von weekly_summary.py (tage=7) und dem taeglichen Podcast-Skript
(tage=1) genutzt - vermeidet Code-Duplikation bei Abfrage und Formatierung.
Die eigentlichen Sonnet-Prompts/-Calls bleiben bewusst PRO Skript getrennt,
da die Ausgabeform unterschiedlich ist (Markdown+Teaser vs. reiner
Sprechtext fuer TTS).
"""

import json
from datetime import date, timedelta


def parse_json_antwort(text: str):
    """
    Robust gegen den Fall, dass Claude die Antwort trotz Anweisung doch in
    ```-Markdown-Fences packt. Wird von bewertung.py und weekly_summary.py
    genutzt.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def hole_eintraege(client, tage: int, relevanz_filter: list[str] | None = None) -> list[dict]:
    """
    Holt news_eintraege der letzten `tage` Tage, optional gefiltert auf
    bestimmte Relevanz-Stufen (z.B. ["Hoch", "Mittel"]). Parametrisiert
    nutzbar fuer 1 Tag (Podcast) oder 7 Tage (Wochenrueckblick).
    """
    grenze = (date.today() - timedelta(days=tage)).isoformat()
    query = (
        client.table("news_eintraege")
        .select("titel, kernaussage, relevanz, datum, kategorien(name)")
        .gte("datum", grenze)
        .order("datum", desc=True)
    )
    if relevanz_filter:
        query = query.in_("relevanz", relevanz_filter)
    return query.execute().data


def gruppiere_nach_kategorie(eintraege: list[dict]) -> dict[str, list[dict]]:
    """Gruppiert Eintraege nach Kategorie-Name (Fallback: 'Sonstiges')."""
    gruppen: dict[str, list[dict]] = {}
    for e in eintraege:
        kategorie = e["kategorien"]["name"] if e.get("kategorien") else "Sonstiges"
        gruppen.setdefault(kategorie, []).append(e)
    return gruppen


def formatiere_fuer_prompt(gruppen: dict[str, list[dict]]) -> str:
    """Formatiert gruppierte Eintraege als Kategorie-Ueberschriften + Bullets fuers Prompt."""
    zeilen = []
    for kategorie, eintraege in gruppen.items():
        zeilen.append(f"\n## {kategorie}")
        for e in eintraege:
            zeilen.append(f"- [{e['relevanz']}] {e['titel']}: {e['kernaussage']}")
    return "\n".join(zeilen)
