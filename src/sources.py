"""
sources.py - Sammelt Kandidaten-Artikel aus zwei Quellen:
1) RSS-Feeds der Prioritaetsquellen (config/quellen.yaml)
2) Ergaenzende Suche ueber Anthropics Web-Search-Tool (Teil der Claude-API)

Hinweis zur Websuche: Urspruenglich war hierfuer die Google Custom Search
JSON API vorgesehen. Die nimmt seit 2025 aber keine neuen Kunden mehr an
(developers.google.com/custom-search/v1/overview: "closed to new customers"),
Abschaltung fuer Bestandskunden zum 1.1.2027. Deshalb stattdessen Anthropics
eigenes Web-Search-Tool - kein zusaetzlicher Account/Key noetig, laeuft ueber
den ohnehin vorhandenen ANTHROPIC_API_KEY, ca. 10$ pro 1000 Suchen.

Gibt eine Liste roher Kandidaten zurueck - noch nicht bewertet oder
gegen die Datenbank dedupliziert, das passiert in main.py / bewertung.py.
"""

from datetime import datetime, timedelta, timezone

import feedparser
import yaml

ROLLIERENDES_FENSTER_STUNDEN = 30  # siehe Konzept: 30h statt starr "seit Mitternacht"


def lade_config(pfad: str = "config/quellen.yaml") -> dict:
    with open(pfad, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _im_zeitfenster(struct_time, stunden: int = ROLLIERENDES_FENSTER_STUNDEN) -> bool:
    """Prueft, ob ein Feed-Eintrag innerhalb des rollierenden Zeitfensters liegt."""
    if struct_time is None:
        return True  # kein Datum im Feed -> lieber mitnehmen als versehentlich verpassen
    veroeffentlicht = datetime(*struct_time[:6], tzinfo=timezone.utc)
    grenze = datetime.now(timezone.utc) - timedelta(hours=stunden)
    return veroeffentlicht >= grenze


def hole_rss_kandidaten(rss_quellen: list[dict]) -> list[dict]:
    """Klappert alle konfigurierten RSS-Feeds ab und filtert auf das Zeitfenster."""
    kandidaten = []
    for quelle in rss_quellen:
        feed = feedparser.parse(quelle["url"])
        for entry in feed.entries:
            datum = entry.get("published_parsed") or entry.get("updated_parsed")
            if not _im_zeitfenster(datum):
                continue
            kandidaten.append({
                "titel": entry.get("title", "").strip(),
                "artikel_url": entry.get("link", "").strip(),
                "roher_text": entry.get("summary", ""),
                "quelle_name": quelle["name"],
                "quelle_url": quelle["url"],
            })
    return kandidaten


SUCH_SYSTEM_PROMPT = """Du suchst im Web nach aktuellen KI-News zu einem \
gegebenen Thema. Nutze das Websuche-Tool, um passende, kuerzlich \
veroeffentlichte Artikel zu finden (idealerweise aus den letzten 2 Tagen, \
aeltere nur wenn nichts Aktuelleres existiert).

Antworte AUSSCHLIESSLICH mit einem JSON-Array (keine Erklaerungen, kein \
Markdown), mit maximal 5 Eintraegen. Jeder Eintrag:
{"titel": "Titel des Artikels", "url": "https://...", "kurzbeschreibung": "1 Satz worum es geht"}

Wenn nichts Relevantes gefunden wird, gib ein leeres Array zurueck: []"""


def hole_web_suche_kandidaten(suchanfragen: list[str]) -> list[dict]:
    """
    Ergaenzende Suche ueber Anthropics Web-Search-Tool - deckt v.a. Anthropic
    und Meta AI ab, die keinen eigenen RSS-Feed haben. Ein API-Call pro Query.
    """
    import anthropic  # lokal importiert, damit dieses Modul auch ohne
    import os          # anthropic-Paket fuer reine RSS-Nutzung lauffaehig bleibt
    from utils import parse_json_antwort

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kandidaten = []

    for query in suchanfragen:
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
                system=SUCH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": query}],
            )
            text_bloecke = [b.text for b in response.content if b.type == "text"]
            gefunden = parse_json_antwort("\n".join(text_bloecke))
        except Exception as e:
            print(f"Fehler bei Websuche '{query}': {e}")
            continue

        for eintrag in gefunden:
            if not eintrag.get("url"):
                continue
            kandidaten.append({
                "titel": eintrag.get("titel", "").strip(),
                "artikel_url": eintrag.get("url", "").strip(),
                "roher_text": eintrag.get("kurzbeschreibung", ""),
                "quelle_name": None,  # wird in db.py aus der Domain abgeleitet
                "quelle_url": None,
            })
    return kandidaten
