"""
daily_podcast.py - Erzeugt einmal taeglich einen kurzen Podcast (Audio) aus
den News-Eintraegen der letzten 24 Stunden und verschickt ihn per Telegram.

Laeuft in einem eigenen, komplett unabhaengigen Workflow (daily-podcast.yml),
kurz nach dem taeglichen Sammellauf - ruehrt weder diesen noch die anderen
Workflows (weekly-summary, weekly-telegram-send) an.
"""

import json
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

import anthropic
import requests
from google.cloud import texttospeech
from google.oauth2 import service_account

from db import get_client
from utils import hole_eintraege, gruppiere_nach_kategorie, formatiere_fuer_prompt

MODELL = "claude-sonnet-5"
STIMME = "de-DE-Neural2-B"  # maennliche Stimme; de-DE-Neural2-A waere weiblich

SYSTEM_PROMPT = """Du schreibst das Skript fuer einen kurzen taeglichen \
KI-News-Podcast auf Deutsch, zum Vorlesen per Text-zu-Sprache.

Du bekommst eine Liste von News-Eintraegen des heutigen Tages, gruppiert \
nach Kategorie.

WICHTIG - reiner Sprechtext, kein Markdown:
- Keine Ueberschriften (kein #), keine Bullet-Points (kein -), keine \
Sternchen oder sonstige Formatierung - alles wuerde beim Vorlesen woertlich \
mitgesprochen werden
- Ein zusammenhaengender, natuerlich klingender Fliesstext mit Uebergaengen \
zwischen den Themen (z.B. "Weiter geht's mit...", "Ausserdem gab es heute...")
- Kurze Begruessung am Anfang ("Hier ist dein KI-News-Update fuer den {datum}."), \
kein Abmoderations-Kitsch am Ende noetig, ein kurzer Abschluss reicht

Laenge: an der Menge der Themen orientieren, tendenziell kompakt (ca. 3-6 \
Minuten Sprechzeit, das sind grob 500-900 Woerter). Bei wenigen Eintraegen \
lieber kurz halten statt kuenstlich strecken.

Antworte NUR mit dem reinen Sprechtext, sonst nichts."""


def generiere_sprechtext(rohdaten: str) -> str:
    heute = date.today().strftime("%d.%m.%Y")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODELL,
        max_tokens=4096,
        system=SYSTEM_PROMPT.replace("{datum}", heute),
        messages=[{"role": "user", "content": rohdaten}],
    )
    # Nur Text-Bloecke rausfiltern - Sonnet kann zusaetzlich ThinkingBlocks
    # zurueckgeben, die keinen .text haben.
    text_bloecke = [b.text for b in response.content if b.type == "text"]
    return "\n".join(text_bloecke).strip()


def chunke_text(text: str, max_chars: int = 4500) -> list[str]:
    """
    Teilt Text in Stuecke unter max_chars auf (Google-Limit: 5000 Zeichen
    pro Anfrage, 4500 als Sicherheitspuffer), getrennt an Satzenden statt
    mitten im Wort. Im Normalfall (3-6 Min. Podcast) reicht ein einziges
    Stueck - das ist nur ein Sicherheitsnetz fuer besonders newsreiche Tage.
    """
    saetze = text.split(". ")
    chunks = []
    aktuell = ""
    for satz in saetze:
        satz = satz.strip()
        if not satz:
            continue
        kandidat = f"{aktuell} {satz}.".strip() if aktuell else f"{satz}."
        if len(kandidat) > max_chars and aktuell:
            chunks.append(aktuell)
            aktuell = f"{satz}."
        else:
            aktuell = kandidat
    if aktuell:
        chunks.append(aktuell)
    return chunks


def erzeuge_audio(text: str) -> bytes:
    credentials_info = json.loads(os.environ["GOOGLE_TTS_CREDENTIALS"])
    credentials = service_account.Credentials.from_service_account_info(credentials_info)
    client = texttospeech.TextToSpeechClient(credentials=credentials)

    voice = texttospeech.VoiceSelectionParams(language_code="de-DE", name=STIMME)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    audio_teile = []
    for chunk in chunke_text(text):
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_teile.append(response.audio_content)

    return b"".join(audio_teile)  # einfaches Aneinanderhaengen der MP3-Teile


def sende_telegram_audio(audio_bytes: bytes, titel: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendAudio",
        data={"chat_id": chat_id, "title": titel},
        files={"audio": ("podcast.mp3", audio_bytes, "audio/mpeg")},
        timeout=60,
    )
    response.raise_for_status()


def main():
    client = get_client()

    eintraege = hole_eintraege(client, tage=1, relevanz_filter=["Hoch", "Mittel"])
    print(f"{len(eintraege)} Eintraege (Hoch+Mittel) der letzten 24h gefunden.")

    if not eintraege:
        print("Keine Eintraege, kein Podcast generiert.")
        return

    gruppen = gruppiere_nach_kategorie(eintraege)
    rohdaten = formatiere_fuer_prompt(gruppen)

    sprechtext = generiere_sprechtext(rohdaten)
    print(f"Sprechtext generiert ({len(sprechtext)} Zeichen).")

    audio_bytes = erzeuge_audio(sprechtext)
    print(f"Audio erzeugt ({len(audio_bytes) / 1024:.0f} KB).")

    heute = date.today().strftime("%d.%m.%Y")
    sende_telegram_audio(audio_bytes, titel=f"KI-News-Podcast {heute}")

    print("Podcast per Telegram verschickt.")


if __name__ == "__main__":
    main()
