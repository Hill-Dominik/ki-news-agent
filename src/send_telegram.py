"""
send_telegram.py - Verschickt den neuesten Wochenrueckblick-Teaser per
Telegram. Laeuft in einem eigenen, komplett unabhaengigen Workflow
(weekly-telegram-send.yml), rein lesender Zugriff auf wochenrueckblicke -
ruehrt weder den taeglichen Sammel-Workflow noch weekly-summary.yml an.
"""

import os

from dotenv import load_dotenv
load_dotenv()

import requests

from db import get_client

DASHBOARD_URL = "https://dome-ki-news.streamlit.app/"


def hole_neuesten_teaser(client) -> dict | None:
    result = (
        client.table("wochenrueckblicke")
        .select("datum_von, datum_bis, teaser")
        .order("erstellt_am", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def sende_telegram_nachricht(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()


def main():
    client = get_client()
    eintrag = hole_neuesten_teaser(client)

    if not eintrag or not eintrag.get("teaser"):
        print("Kein Wochenrueckblick mit Teaser gefunden, nichts zu versenden.")
        return

    nachricht = (
        f"📋 KI-News-Wochenrückblick ({eintrag['datum_von']} – {eintrag['datum_bis']})\n\n"
        f"{eintrag['teaser']}\n\n"
        f"Volle Übersicht: {DASHBOARD_URL}"
    )

    sende_telegram_nachricht(nachricht)
    print("Telegram-Nachricht verschickt.")


if __name__ == "__main__":
    main()
