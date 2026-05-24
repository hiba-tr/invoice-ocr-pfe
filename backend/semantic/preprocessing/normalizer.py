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
    Version améliorée qui préserve les informations importantes.
    """
    if not text:
        return ""

    # 1. Normalisation Unicode (suppression des accents)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # 2. Minuscules
    text = text.lower()

    # 3. Préserver les caractères importants (#, &, etc.)
    # Ne pas supprimer #, &, /, -
    # Remplacer seulement la ponctuation excessive
    text = re.sub(r"[.,;:!?\"'`´]", " ", text)
    
    # 4. Expansion des abréviations
    for abbr, full in sorted(_ABBREVS.items(), key=lambda x: -len(x[0])):
        text = re.sub(r'\b' + re.escape(abbr) + r'\b', full, text)

    # 5. Nettoyer les espaces multiples
    text = re.sub(r"\s+", " ", text).strip()

    return text