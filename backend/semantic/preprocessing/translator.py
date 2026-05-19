"""
Traduction automatique FR↔EN avec Helsinki-NLP (gratuit, local, open-source).
"""
import logging

_log = logging.getLogger(__name__)

_translator_fr_en = None
_translator_en_fr = None
_loaded_fr_en = False
_loaded_en_fr = False


def _load_translator_fr_en():
    """Charge le modèle de traduction FR→EN (lazy loading)."""
    global _translator_fr_en, _loaded_fr_en
    if _loaded_fr_en:
        return _translator_fr_en

    _loaded_fr_en = True
    try:
        from transformers import MarianMTModel, MarianTokenizer

        _log.info("Chargement traducteur FR→EN (Helsinki-NLP/opus-mt-fr-en)...")
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
    """Charge le modèle de traduction EN→FR (lazy loading)."""
    global _translator_en_fr, _loaded_en_fr
    if _loaded_en_fr:
        return _translator_en_fr

    _loaded_en_fr = True
    try:
        from transformers import MarianMTModel, MarianTokenizer

        _log.info("Chargement traducteur EN→FR (Helsinki-NLP/opus-mt-en-fr)...")
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
    """Détecte la langue d'un texte (français ou anglais)."""
    if not text:
        return "en"

    text_lower = text.lower()

    # Caractères accentués → français
    if any(c in text_lower for c in "éèêëàâîïôùûçœæ"):
        return "fr"

    # Mots-clés français
    fr_words = {"facture", "devis", "bon de commande", "avoir", "montant", "tva", "ht", "ttc", "début", "fin", "quinze", "trente", "cinquante"}
    words = set(text_lower.split())
    if words & fr_words:
        return "fr"

    return "en"