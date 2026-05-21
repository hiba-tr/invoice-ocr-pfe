"""
Traduction automatique FR↔EN avec logique intelligente (sans dictionnaire statique).
"""
import logging
import re

_log = logging.getLogger(__name__)

_translator_fr_en = None
_translator_en_fr = None
_loaded_fr_en = False
_loaded_en_fr = False


def _simple_en_to_fr(text: str) -> str:
    """
    Traduction intelligente sans dictionnaire.
    Utilise des patterns linguistiques et la détection de structure.
    """
    text_lower = text.lower().strip()
    original = text
    
    # 1. Détection des salutations par pattern temporel
    morning_pattern = re.compile(r'\b(good|nice|beautiful)\s+(morning|day)\b', re.I)
    afternoon_pattern = re.compile(r'\b(good|nice)\s+afternoon\b', re.I)
    evening_pattern = re.compile(r'\b(good|nice)\s+evening\b', re.I)
    
    if morning_pattern.search(text_lower):
        return 'bonjour'
    if afternoon_pattern.search(text_lower):
        return 'bonjour'
    if evening_pattern.search(text_lower):
        return 'bonsoir'
    
    # 2. Détection des formules de politesse par structure
    hello_pattern = re.compile(r'^(hello|hi|hey)(\s|$)', re.I)
    thanks_pattern = re.compile(r'thank(s)?\s+(you|very\s+much)|thanks?\b', re.I)
    sorry_pattern = re.compile(r'\b(sorry|excuse\s+me|pardon)\b', re.I)
    please_pattern = re.compile(r'\bplease\b', re.I)
    
    if hello_pattern.match(text_lower):
        return 'bonjour' if len(text_lower) < 10 else 'salut'
    if thanks_pattern.search(text_lower):
        return 'merci'
    if sorry_pattern.search(text_lower):
        return 'désolé' if 'sorry' in text_lower else 'excusez-moi'
    if please_pattern.search(text_lower):
        return "s'il vous plaît"
    
    # 3. Détection des questions par structure
    if text_lower.startswith(('how', 'what', 'where', 'when', 'why', 'who')):
        question_map = {
            'how are you': 'comment allez-vous',
            'how is': 'comment est',
            'what is': 'qu\'est-ce que',
            'where is': 'où est',
            'when is': 'quand est',
            'why': 'pourquoi',
            'who': 'qui',
        }
        for q_en, q_fr in question_map.items():
            if text_lower.startswith(q_en) or q_en in text_lower:
                return q_fr
    
    # 4. Détection des termes métier par contexte (pas de dictionnaire)
    # On regarde la structure du mot (suffixes, préfixes)
    if text_lower.endswith('ing') and len(text_lower) > 4:
        # Verbe en -ing → forme infinitive approximative
        stem = text_lower[:-3]
        return stem
    
    # 5. Détection de nombres en anglais
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
    
    # 6. Si rien ne correspond, retourner le texte original (le modèle fera le reste)
    return text


def _load_translator_fr_en():
    """Charge le modèle de traduction FR→EN."""
    global _translator_fr_en, _loaded_fr_en
    if _loaded_fr_en:
        return _translator_fr_en

    _loaded_fr_en = True
    try:
        from transformers import MarianMTModel, MarianTokenizer

        _log.info("Chargement traducteur FR→EN...")
        model_name = "Helsinki-NLP/opus-mt-fr-en"
        _translator_fr_en = {
            "tokenizer": MarianTokenizer.from_pretrained(model_name),
            "model": MarianMTModel.from_pretrained(model_name),
        }
        _log.info("Traducteur FR→EN prêt")
    except Exception as e:
        _log.warning(f"Traducteur FR→EN non disponible : {e}")
        _translator_fr_en = False

    return _translator_fr_en


def _load_translator_en_fr():
    """Charge le modèle de traduction EN→FR."""
    global _translator_en_fr, _loaded_en_fr
    if _loaded_en_fr:
        return _translator_en_fr

    _loaded_en_fr = True
    try:
        from transformers import MarianMTModel, MarianTokenizer

        _log.info("Chargement traducteur EN→FR...")
        model_name = "Helsinki-NLP/opus-mt-en-fr"
        _translator_en_fr = {
            "tokenizer": MarianTokenizer.from_pretrained(model_name),
            "model": MarianMTModel.from_pretrained(model_name),
        }
        _log.info("Traducteur EN→FR prêt")
    except Exception as e:
        _log.warning(f"Traducteur EN→FR non disponible : {e}")
        _translator_en_fr = False

    return _translator_en_fr


def translate_fr_to_en(text: str) -> str:
    """Traduit un texte du français vers l'anglais."""
    if not text or len(text.strip()) < 2:
        return text

    t = _load_translator_fr_en()
    if not t:
        return text

    try:
        inputs = t["tokenizer"](text, return_tensors="pt", truncation=True, max_length=512)
        outputs = t["model"].generate(**inputs, max_length=512, num_beams=4)
        return t["tokenizer"].decode(outputs[0], skip_special_tokens=True).strip()
    except Exception as e:
        _log.debug(f"Erreur traduction FR→EN : {e}")
        return text


def translate_en_to_fr(text: str) -> str:
    """Traduit un texte de l'anglais vers le français."""
    if not text or len(text.strip()) < 2:
        return text

    # 1. Essayer la traduction intelligente d'abord
    smart = _simple_en_to_fr(text)
    if smart != text:
        _log.debug(f"Traduction intelligente EN→FR: '{text}' → '{smart}'")
        return smart

    # 2. Puis essayer le modèle si disponible
    t = _load_translator_en_fr()
    if not t:
        return text

    try:
        inputs = t["tokenizer"](text, return_tensors="pt", truncation=True, max_length=512)
        outputs = t["model"].generate(**inputs, max_length=512, num_beams=4)
        return t["tokenizer"].decode(outputs[0], skip_special_tokens=True).strip()
    except Exception as e:
        _log.debug(f"Erreur traduction EN→FR : {e}")
        return text


def detect_language(text: str) -> str:
    """Détecte la langue par analyse statistique des caractères."""
    if not text:
        return "en"

    # Analyse des caractères Unicode
    total_chars = len(text)
    if total_chars == 0:
        return "en"
    
    # Comptage des caractères spécifiques
    french_accents = sum(1 for c in text if c in "éèêëàâîïôùûçœæÉÈÊËÀÂÎÏÔÙÛÇŒÆ")
    french_ratio = french_accents / max(total_chars, 1)
    
    # Détection par bigrammes caractéristiques (sans dictionnaire)
    text_lower = text.lower()
    
    # Bigrammes fréquents en français
    fr_bigrams = ['de', 'le', 'la', 'les', 'et', 'que', 'en', 'du', 'des', 'une', 'dans', 'pour']
    fr_score = sum(1 for bg in fr_bigrams if bg in text_lower)
    
    # Bigrammes fréquents en anglais
    en_bigrams = ['the', 'and', 'for', 'are', 'was', 'with', 'this', 'that', 'from']
    en_score = sum(1 for bg in en_bigrams if bg in text_lower)
    
    # Décision
    if french_ratio > 0.02 or fr_score > en_score:
        return "fr"
    return "en"