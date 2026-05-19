"""
Normalisation de texte pour le matching sémantique.
Gère le français, l'anglais, les abréviations techniques et le nettoyage OCR.
"""
import re
import unicodedata
from functools import lru_cache

# ── Abréviations techniques ─────────────────────────────────────────────────
_ABBREVS = {
    "ytd": "year to date",
    "cme": "current month expenditure",
    "capex": "capital expenditure",
    "opex": "operating expenditure",
    "d&c": "drilling and completion",
    "w/o": "workover",
    "ta": "turnaround",
    "cpf": "central processing facility",
    "esdv": "emergency shutdown valve",
    "fgr": "flare gas recovery",
    "etap": "etap",
    "omv": "omv",
    "ht": "hors taxe",
    "ttc": "toutes taxes comprises",
    "tva": "taxe valeur ajoutee",
    "pu": "prix unitaire",
    "mo": "main oeuvre",
    "hse": "health safety environment",
    "pi": "production information",
    "dcs": "distributed control system",
    "g&a": "general and administration",
}


@lru_cache(maxsize=5000)
def normalize_text(text: str) -> str:
    """
    Normalise un texte pour le matching sémantique.

    Étapes :
    1. Découpage camelCase → mots séparés
    2. Normalisation Unicode NFKD (suppression des accents)
    3. Minuscules
    4. Expansion des abréviations techniques
    5. Suppression de la ponctuation
    6. Compression des espaces

    Args:
        text: Texte brut (peut contenir des accents, majuscules, etc.)

    Returns:
        Texte normalisé (minuscules, sans accents, sans ponctuation)

    Examples:
        >>> normalize_text("CurrentMonthBalance")
        "current month balance"
        >>> normalize_text("ÉTAP share @50%")
        "etap share 50"
        >>> normalize_text("D&C")
        "drilling and completion"
    """
    if not text:
        return ""

    # 1. CamelCase → mots séparés
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)

    # 2. Normalisation Unicode (suppression des accents)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # 3. Minuscules
    text = text.lower()

    # 4. Expansion des abréviations (les plus longues d'abord)
    for abbr, full in sorted(_ABBREVS.items(), key=lambda x: -len(x[0])):
        text = re.sub(r'\b' + re.escape(abbr) + r'\b', full, text)

    # 5. Suppression ponctuation (garde les espaces et tirets)
    text = re.sub(r"[^\w\s\-]", " ", text)

    # 6. Compression des espaces
    text = re.sub(r"\s+", " ", text).strip()

    return text