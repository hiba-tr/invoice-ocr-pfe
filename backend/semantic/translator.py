"""Traduction FR↔EN - Version optimisée avec cache"""
import logging

_log = logging.getLogger(__name__)

_translator_fr_en = None
_translator_loaded = False


def _load_translator():
    global _translator_fr_en, _translator_loaded
    if _translator_loaded:
        return _translator_fr_en
    
    _translator_loaded = True
    try:
        from transformers import MarianMTModel, MarianTokenizer
        _log.info("Chargement traducteur FR→EN (Helsinki-NLP)...")
        _translator_fr_en = {
            "tokenizer": MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-fr-en"),
            "model": MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-fr-en"),
        }
        _log.info("Traducteur FR→EN pret")
    except Exception as e:
        _log.warning(f"Traducteur non disponible: {e}")
        _translator_fr_en = False
    return _translator_fr_en


def translate_fr_to_en(text: str) -> str:
    """Traduit FR→EN avec fallback silencieux"""
    if not text or len(text.strip()) < 2:
        return text
    
    t = _load_translator()
    if t is False or t is None:
        return text
    
    try:
        inputs = t["tokenizer"](text, return_tensors="pt", truncation=True, max_length=512)
        outputs = t["model"].generate(**inputs, max_length=512, num_beams=4)
        return t["tokenizer"].decode(outputs[0], skip_special_tokens=True).strip()
    except Exception:
        return text


def detect_language(text: str) -> str:
    """Detection simple de la langue."""
    if not text:
        return "en"
    text_lower = text.lower()
    fr_chars = sum(1 for c in text_lower if c in "éèêëàâîïôùûçœæ")
    if fr_chars > 0:
        return "fr"
    fr_words = {"facture", "devis", "bon de commande", "avoir", "montant", "tva", "ht", "ttc"}
    words = set(text_lower.split())
    if words & fr_words:
        return "fr"
    return "en"