"""
Correcteur Sémantique Universel
- Traduction intelligente
- Correction fautes de frappe
- Similarité sémantique (embeddings + fuzzy)
- Aucun dictionnaire statique lourd
"""

import logging
from typing import List

from ..preprocessing.normalizer import normalize_text
from ..preprocessing.translator import translate_en_to_fr, detect_language
from ..embeddings.embedder import _get_model, encode
from ..knowledge.synonyms import normalize_word
import numpy as np

_log = logging.getLogger(__name__)

_FUZZY_AVAILABLE = False
try:
    from rapidfuzz import fuzz as _rfuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    pass


class UniversalSemanticCorrector:
    """Correcteur universel intelligent - un seul fichier pour tout gérer."""

    def __init__(self):
        self.model = None

    def _get_model(self):
        if self.model is None:
            self.model = _get_model()
        return self.model

    def correct_text(self, text: str, db_items: List, concession_id: int = None) -> str:
        """
        Correction universelle complète : traduction + fautes + sémantique
        """
        if not text or len(text.strip()) < 2:
            return text

        original = text.strip()
        langue = detect_language(original)

        # 1. Traduction si anglais
        if langue == 'en':
            translated = translate_en_to_fr(original)
            if translated != original:
                _log.debug(f"Traduction : '{original}' → '{translated}'")
                original = translated

        # 2. Normalisation
        normalized = normalize_text(original)

        # 3. Correction par token (fautes + sémantique)
        tokens = normalized.split()
        corrected_tokens = []

        for token in tokens:
            if len(token) < 2:
                corrected_tokens.append(token)
                continue
            
            corrected = self._correct_single_token(token, db_items)
            corrected_tokens.append(corrected)

        result = " ".join(corrected_tokens)
        
        if result != normalize_text(original):
            _log.info(f"Correction universelle : '{original}' → '{result}'")
        
        return result

    def _correct_single_token(self, token: str, db_items: List) -> str:
        """Correction intelligente d'un seul token."""
        if not db_items or not _FUZZY_AVAILABLE:
            return token

        norm_token = normalize_word(token).lower()
        best_score = 0.0
        best_match = token

        try:
            token_emb = encode([norm_token])
        except:
            token_emb = None

        for item in db_items:
            item_norm = normalize_text(item.libelle_canonique).lower()
            
            # 🔥 CORRECTION: Convertir item_norm.split() qui est une liste
            words = item_norm.split()
            for word in words:
                if len(word) < 2:
                    continue
                
                word_norm = normalize_word(word)

                fuzzy_score = _rfuzz.token_sort_ratio(norm_token, word_norm) / 100.0
                partial_score = _rfuzz.partial_ratio(norm_token, word_norm) / 100.0
                score = max(fuzzy_score, partial_score)

                if token_emb is not None:
                    try:
                        word_emb = encode([word_norm])
                        if word_emb is not None:
                            emb_sim = float(np.dot(token_emb[0], word_emb[0]))
                            score = (score * 0.65) + (emb_sim * 0.35)
                    except:
                        pass

                if score > best_score and score >= 0.72:
                    best_score = score
                    best_match = word

        if best_score >= 0.75:
            return best_match
        return token


# Instance unique (à importer partout)
universal_corrector = UniversalSemanticCorrector()