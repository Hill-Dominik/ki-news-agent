"""
db.py - Supabase-Anbindung fuer den KI-News-Agenten.

Nutzt den service_role-Key (voller Schreibzugriff, umgeht Row Level Security).
Der Key kommt AUSSCHLIESSLICH aus der Umgebungsvariable SUPABASE_SERVICE_KEY
(lokal via .env, in der Automatisierung via GitHub Actions Secret) und darf
niemals im Code, in Commits oder im Klartext irgendwo landen.
"""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from supabase import create_client, Client


def get_client() -> Client:
    """Baut den Supabase-Client aus den Umgebungsvariablen."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_or_create_quelle(client: Client, name: str, url: str) -> int:
    """Gibt die id der Quelle zurueck, legt sie an falls noch nicht vorhanden."""
    existing = client.table("quellen").select("id").eq("url", url).execute()
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("quellen").insert({"name": name, "url": url}).execute()
    return inserted.data[0]["id"]


def quelle_info_from_domain(article_url: str) -> tuple[str, str]:
    """
    Leitet Name + URL einer Quelle aus der Domain eines Artikels ab.
    Fallback fuer Google-Suchergebnisse, die keinem festen RSS-Feed
    aus der Prioritaetsliste zugeordnet werden koennen (z.B. Anthropic,
    Meta AI oder ein zufaelliger Treffer bei anderen Publishern).
    """
    domain = urlparse(article_url).netloc.replace("www.", "")
    return domain, f"https://{domain}"


def get_or_create_kategorie(client: Client, name: str) -> int:
    """Gibt die id der Kategorie zurueck, legt sie an falls noch nicht vorhanden."""
    existing = client.table("kategorien").select("id").eq("name", name).execute()
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("kategorien").insert({"name": name}).execute()
    return inserted.data[0]["id"]


def artikel_existiert(client: Client, artikel_url: str) -> bool:
    """Dedup Stufe 1: URL-Exact-Match gegen bereits gespeicherte Artikel."""
    result = (
        client.table("news_eintraege")
        .select("id")
        .eq("artikel_url", artikel_url)
        .execute()
    )
    return len(result.data) > 0


def get_letzte_titel(client: Client, tage: int = 3) -> list[str]:
    """Titel der letzten X Tage - Grundlage fuer den LLM-Dedup-Check (Stufe 2)."""
    grenze = (datetime.now(timezone.utc) - timedelta(days=tage)).date().isoformat()
    result = (
        client.table("news_eintraege")
        .select("titel")
        .gte("datum", grenze)
        .execute()
    )
    return [row["titel"] for row in result.data]


def speichere_eintrag(client: Client, eintrag: dict) -> None:
    """
    Erwartet ein dict mit den Feldern:
    datum, titel, kernaussage, artikel_url, quelle_id, kategorie_id,
    relevanz, zusatzdaten
    """
    client.table("news_eintraege").insert(eintrag).execute()
