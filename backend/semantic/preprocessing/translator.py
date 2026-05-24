"""
Traduction automatique FR↔EN avec logique intelligente.
OPTIMISATIONS :
  - detect_language mis en cache via @lru_cache
  - Chargement MarianMT en thread daemon (non bloquant)
  - translate_en_to_fr mis en cache pour les textes courts répétitifs
"""
import logging
import re
import threading
from functools import lru_cache

_log = logging.getLogger(__name__)

_translator_fr_en = None
_translator_en_fr = None
_loaded_fr_en     = False
_loaded_en_fr     = False
_lock_fr_en       = threading.Lock()
_lock_en_fr       = threading.Lock()


# ── Préchargement en arrière-plan ─────────────────────────────────────────────
def preload_translators_background() -> None:
    """
    Lance le chargement des modèles MarianMT dans des threads daemons.
    À appeler au startup du serveur (FastAPI @app.on_event("startup")).
    """
    threading.Thread(target=_load_translator_en_fr, daemon=True, name="marian-en-fr").start()
    threading.Thread(target=_load_translator_fr_en, daemon=True, name="marian-fr-en").start()


# ── Traduction intelligente (sans modèle) ─────────────────────────────────────
def _simple_en_to_fr(text: str) -> str:
    """Traduction par patterns linguistiques, sans dictionnaire statique."""
    text_lower = text.lower().strip()

    morning_pat   = re.compile(r'\b(good|nice|beautiful)\s+(morning|day)\b', re.I)
    afternoon_pat = re.compile(r'\b(good|nice)\s+afternoon\b', re.I)
    evening_pat   = re.compile(r'\b(good|nice)\s+evening\b', re.I)

    if morning_pat.search(text_lower):   return 'bonjour'
    if afternoon_pat.search(text_lower): return 'bonjour'
    if evening_pat.search(text_lower):   return 'bonsoir'

    hello_pat  = re.compile(r'^(hello|hi|hey)(\s|$)', re.I)
    thanks_pat = re.compile(r'thank(s)?\s+(you|very\s+much)|thanks?\b', re.I)
    sorry_pat  = re.compile(r'\b(sorry|excuse\s+me|pardon)\b', re.I)
    please_pat = re.compile(r'\bplease\b', re.I)

    if hello_pat.match(text_lower):
        return 'bonjour' if len(text_lower) < 10 else 'salut'
    if thanks_pat.search(text_lower): return 'merci'
    if sorry_pat.search(text_lower):
        return 'désolé' if 'sorry' in text_lower else 'excusez-moi'
    if please_pat.search(text_lower): return "s'il vous plaît"

    if text_lower.startswith(('how', 'what', 'where', 'when', 'why', 'who')):
        question_map = {
            'how are you': 'comment allez-vous',
            'how is':      'comment est',
            'what is':     "qu'est-ce que",
            'where is':    'où est',
            'when is':     'quand est',
            'why':         'pourquoi',
            'who':         'qui',
        }
        for q_en, q_fr in question_map.items():
            if text_lower.startswith(q_en) or q_en in text_lower:
                return q_fr

    if text_lower.endswith('ing') and len(text_lower) > 4:
        return text_lower[:-3]

    number_words = {
        'one': 'un', 'two': 'deux', 'three': 'trois', 'four': 'quatre',
        'five': 'cinq', 'six': 'six', 'seven': 'sept', 'eight': 'huit',
        'nine': 'neuf', 'ten': 'dix', 'eleven': 'onze', 'twelve': 'douze',
        'thirteen': 'treize', 'fourteen': 'quatorze', 'fifteen': 'quinze',
        'sixteen': 'seize', 'seventeen': 'dix-sept', 'eighteen': 'dix-huit',
        'nineteen': 'dix-neuf', 'twenty': 'vingt', 'thirty': 'trente',
        'forty': 'quarante', 'fifty': 'cinquante', 'sixty': 'soixante',
        'seventy': 'soixante-dix', 'eighty': 'quatre-vingts', 'ninety': 'quatre-vingt-dix',
        'hundred': 'cent', 'thousand': 'mille', 'million': 'million',
    }
    for en, fr in number_words.items():
        if text_lower == en or f' {en} ' in f' {text_lower} ':
            return fr

    return text  # aucun pattern trouvé → retour original


# ── Chargement des modèles (thread-safe, lazy) ────────────────────────────────
def _load_translator_fr_en():
    global _translator_fr_en, _loaded_fr_en
    with _lock_fr_en:
        if _loaded_fr_en:
            return _translator_fr_en
        _loaded_fr_en = True
        try:
            from transformers import MarianMTModel, MarianTokenizer
            _log.info("Chargement traducteur FR→EN…")
            mn = "Helsinki-NLP/opus-mt-fr-en"
            _translator_fr_en = {
                "tokenizer": MarianTokenizer.from_pretrained(mn),
                "model":     MarianMTModel.from_pretrained(mn),
            }
            _log.info("Traducteur FR→EN prêt")
        except Exception as e:
            _log.warning(f"Traducteur FR→EN non disponible : {e}")
            _translator_fr_en = False
    return _translator_fr_en


def _load_translator_en_fr():
    global _translator_en_fr, _loaded_en_fr
    with _lock_en_fr:
        if _loaded_en_fr:
            return _translator_en_fr
        _loaded_en_fr = True
        try:
            from transformers import MarianMTModel, MarianTokenizer
            _log.info("Chargement traducteur EN→FR…")
            mn = "Helsinki-NLP/opus-mt-en-fr"
            _translator_en_fr = {
                "tokenizer": MarianTokenizer.from_pretrained(mn),
                "model":     MarianMTModel.from_pretrained(mn),
            }
            _log.info("Traducteur EN→FR prêt")
        except Exception as e:
            _log.warning(f"Traducteur EN→FR non disponible : {e}")
            _translator_en_fr = False
    return _translator_en_fr


# ── API publique ──────────────────────────────────────────────────────────────

def translate_fr_to_en(text: str) -> str:
    """Traduit un texte du français vers l'anglais."""
    if not text or len(text.strip()) < 2:
        return text
    t = _load_translator_fr_en()
    if not t:
        return text
    try:
        inputs  = t["tokenizer"](text, return_tensors="pt", truncation=True, max_length=512)
        outputs = t["model"].generate(**inputs, max_length=512, num_beams=4)
        return t["tokenizer"].decode(outputs[0], skip_special_tokens=True).strip()
    except Exception as e:
        _log.debug(f"Erreur traduction FR→EN : {e}")
        return text


@lru_cache(maxsize=4000)
def translate_en_to_fr(text: str) -> str:
    """
    Traduit un texte de l'anglais vers le français.
    Résultats mis en cache (@lru_cache) — les textes répétitifs ne font plus appel au modèle.
    """
    if not text or len(text.strip()) < 2:
        return text

    # 1. Traduction intelligente (rapide, sans modèle)
    smart = _simple_en_to_fr(text)
    if smart != text:
        _log.debug(f"Traduction intelligente EN→FR: '{text}' → '{smart}'")
        return smart

    # 2. Modèle MarianMT si disponible
    t = _load_translator_en_fr()
    if not t:
        return text
    try:
        inputs  = t["tokenizer"](text, return_tensors="pt", truncation=True, max_length=512)
        outputs = t["model"].generate(**inputs, max_length=512, num_beams=4)
        return t["tokenizer"].decode(outputs[0], skip_special_tokens=True).strip()
    except Exception as e:
        _log.debug(f"Erreur traduction EN→FR : {e}")
        return text


@lru_cache(maxsize=4000)
def detect_language(text: str) -> str:
    """
    Détecte la langue par analyse statistique des caractères.
    OPTIMISÉ : @lru_cache — appelée très fréquemment, résultat stable pour un texte donné.
    """
    if not text:
        return "en"

    total = len(text)
    if total == 0:
        return "en"

    # Ratio d'accents français
    french_accents = sum(1 for c in text if c in "éèêëàâîïôùûçœæÉÈÊËÀÂÎÏÔÙÛÇŒÆ")
    if french_accents / total > 0.02:
        return "fr"

    text_lower = text.lower()

    fr_bigrams = ['de', 'le', 'la', 'les', 'et', 'que', 'en', 'du', 'des', 'une', 'dans', 'pour']
    en_bigrams = ['the', 'and', 'for', 'are', 'was', 'with', 'this', 'that', 'from']

    fr_score = sum(1 for bg in fr_bigrams if bg in text_lower)
    en_score = sum(1 for bg in en_bigrams if bg in text_lower)

    return "fr" if fr_score > en_score else "en"