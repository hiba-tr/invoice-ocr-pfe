"""
Conversion nombres chiffres ↔ mots pour le matching sémantique.
Permet de matcher "15" avec "quinze", "1250" avec "mille deux cent cinquante".
"""
import re
import logging

_log = logging.getLogger(__name__)

_HAS_NUM2WORDS = False
try:
    from num2words import num2words
    _HAS_NUM2WORDS = True
except ImportError:
    _log.warning("num2words non installé → conversion chiffres/mots désactivée")


def number_to_words(n) -> str:
    """
    Convertit un nombre en mots (français).
    """
    if not _HAS_NUM2WORDS:
        return str(n)

    try:
        return num2words(int(n) if float(n) == int(n) else float(n), lang="fr")
    except Exception:
        return str(n)


def words_to_number(text: str):
    """
    Convertit un nombre en lettres vers un nombre.
    """
    if not _HAS_NUM2WORDS:
        return None

    t = text.strip().lower()

    # Cache généré une seule fois (0 à 10 000 + grands nombres)
    if not hasattr(words_to_number, "_cache"):
        words_to_number._cache = {}
        for i in range(10_001):
            words_to_number._cache[num2words(i, lang="fr")] = i
        for i in [50_000, 100_000, 500_000, 1_000_000]:
            words_to_number._cache[num2words(i, lang="fr")] = i

    return words_to_number._cache.get(t)


def get_number_variants(text: str) -> list:
    """
    Retourne toutes les variantes d'un nombre (chiffres + mots).
    """
    t = text.strip().lower()
    variants = [t]

    if not _HAS_NUM2WORDS:
        return variants

    # Cas 1 : chiffre → mot
    if re.fullmatch(r"\d+(\.\d+)?", t):
        n = float(t) if "." in t else int(t)
        w = number_to_words(n)
        if w != t:
            variants.append(w)
        return variants

    # Cas 2 : mot → chiffre
    n = words_to_number(t)
    if n is not None:
        variants.append(str(n))

    return variants