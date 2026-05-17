"""Normalisation de texte pour le matching sémantique."""
import re
import unicodedata

_UNICODE_MAP = {
    "é": "e", "è": "e", "ê": "e", "ë": "e", "à": "a", "â": "a", "ä": "a",
    "î": "i", "ï": "i", "ô": "o", "ö": "o", "ù": "u", "û": "u", "ü": "u",
    "ç": "c", "œ": "oe", "æ": "ae", "\u00a0": " ",
}

_ABBREVS = {
    "ytd": "year to date", "cme": "current month expenditure",
    "capex": "capital expenditure", "opex": "operating expenditure",
    "d&c": "drilling and completion", "w/o": "workover",
    "ta": "turnaround", "cpf": "central processing facility",
    "esdv": "emergency shutdown valve", "fgr": "flare gas recovery",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    for src, dst in _UNICODE_MAP.items():
        text = text.replace(src, dst)
    text = text.lower()
    for abbr, full in _ABBREVS.items():
        text = re.sub(r'\b' + re.escape(abbr) + r'\b', full, text)
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text