"""
utils.py - Kleine Hilfsfunktionen, die von mehreren Modulen gebraucht werden.
"""

import json


def parse_json_antwort(text: str):
    """
    Robust gegen den Fall, dass Claude die Antwort trotz Anweisung doch in
    ```-Markdown-Fences packt. Wird sowohl fuer die Artikel-Bewertung als
    auch fuer die Websuche-Ergebnisse genutzt.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)
