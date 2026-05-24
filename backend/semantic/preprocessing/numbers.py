"""
Conversion nombres chiffres ↔ mots pour le matching sémantique.
OPTIMISATIONS :
  - Cache words_to_number construit UNE SEULE FOIS au niveau module (thread daemon)
  - get_number_variants mis en cache via @lru_cache
"""
import re
import logging
import threading
from functools import lru_cache

_log = logging.getLogger(__name__)

_HAS_NUM2WORDS = False
try:
    from num2words import num2words
    _HAS_NUM2WORDS = True
except ImportError:
    _log.warning("num2words non installé → conversion chiffres/mots désactivée")

# ── Cache module-level (construit une seule fois, en arrière-plan) ────────────
_words_cache: dict = {}
_cache_ready  = threading.Event()
_cache_lock   = threading.Lock()

def _build_words_cache() -> None:
    """
    Construit le dictionnaire mot→nombre en arrière-plan.
    Ne bloque pas le démarrage du serveur.
    """
    if not _HAS_NUM2WORDS:
        _cache_ready.set()
        return
    tmp = {}
    try:
        for i in range(10_001):
            tmp[num2words(i, lang="fr")] = i
        for i in [50_000, 100_000, 500_000, 1_000_000]:
            tmp[num2words(i, lang="fr")] = i
        with _cache_lock:
            _words_cache.update(tmp)
        _log.info(f"Cache words_to_number prêt ({len(tmp)} entrées)")
    except Exception as e:
        _log.error(f"Erreur construction cache words_to_number : {e}")
    finally:
        _cache_ready.set()

# Lance la construction en thread daemon — ne bloque pas l'import
_t = threading.Thread(target=_build_words_cache, daemon=True, name="num2words-cache")
_t.start()


# ─────────────────────────────────────────────────────────────────────────────

def number_to_words(n) -> str:
    """Convertit un nombre en mots (français)."""
    if not _HAS_NUM2WORDS:
        return str(n)
    try:
        return num2words(int(n) if float(n) == int(n) else float(n), lang="fr")
    except Exception:
        return str(n)


def words_to_number(text: str):
    """
    Convertit un nombre en lettres vers un entier.
    Utilise le cache module-level (construit une seule fois).
    Ne bloque pas si le cache n'est pas encore prêt : retourne None.
    """
    if not _HAS_NUM2WORDS or not _cache_ready.is_set():
        return None
    return _words_cache.get(text.strip().lower())


@lru_cache(maxsize=4000)
def get_number_variants(text: str) -> list:  # ← retourne une liste au lieu d'un tuple
    """
    Retourne les variantes d'un nombre (chiffres ↔ mots) sous forme de liste.
    """
    t = text.strip().lower()
    variants = [t]

    if not _HAS_NUM2WORDS:
        return variants

    if re.fullmatch(r"\d+(\.\d+)?", t):
        n = float(t) if "." in t else int(t)
        w = number_to_words(n)
        if w != t:
            variants.append(w)
        return variants

    n = words_to_number(t)
    if n is not None:
        variants.append(str(n))

    return variants