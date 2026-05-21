"""
Pipeline sémantique complet - Version finale utilisant Intelligent Corrector
"""

import logging
import re
from functools import lru_cache
from typing import List, Dict, Any

from ..preprocessing.normalizer import normalize_text
from ..preprocessing.translator import translate_en_to_fr, detect_language
from ..preprocessing.numbers import get_number_variants, words_to_number
from ..knowledge.synonyms import expand_synonyms, _vocab_cache, precompute_vocab_embeddings
from ..embeddings.embedder import encode_with_variants, get_or_build_index, EMBEDDING_AVAILABLE
from .engine import MatchingEngine, DBItem
from .intelligent_corrector import universal_corrector   # ← Import du correcteur universel

_log = logging.getLogger(__name__)

# ── Dépendances optionnelles ─────────────────────────────────────────────────
_FUZZY_AVAILABLE = False
try:
    from rapidfuzz import fuzz as _rfuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    pass

# ── Patterns ─────────────────────────────────────────────────────────────────
_DOC_REF_RE = re.compile(
    r'(devis|facture|avoir|bl|bc|br|bon)\s*(n[°o]?\.?\s*)[\w\-/]+|'
    r'\b[a-zA-Z]{1,4}[/\-]\d{3,}|'
    r'n[°o]\.?\s*\d',
    re.IGNORECASE,
)


def _is_doc_reference(text: str) -> bool:
    return bool(_DOC_REF_RE.search(text))


@lru_cache(maxsize=1000)
def _is_number(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip()
    if re.search(r'\d\s*[/:]\s*\d', t):
        return False
    cleaned = re.sub(r'[\s\u00a0]', '', t)
    cleaned = re.sub(r"[()%€$£\-+]", '', cleaned)
    patterns = [r'\d{1,3}(\.\d{3})*(,\d+)?', r'\d{1,3}(,\d{3})*(\.\d+)?', r'\d+([.,]\d+)?']
    return any(re.fullmatch(p, cleaned) for p in patterns)


def _is_ocr_noise(text: str) -> bool:
    if not text or len(text) < 2:
        return True
    if any(c in text for c in '=|+*#@!<>?\\[]{}'):
        return True
    letters = [c for c in text.lower() if c.isalpha()]
    if letters and len(letters) > 4 and sum(1 for c in letters if c in 'aeiouy') == 0:
        return True
    return False


def _classify(text: str) -> str:
    if not text or not text.strip():
        return 'empty'
    if _is_doc_reference(text):
        return 'doc_ref'
    if _is_number(text):
        return 'number'
    if _is_ocr_noise(text):
        return 'noise'
    return 'text'


def decompose_texte_compose(text: str) -> List[str]:
    if not text:
        return [text]
    tokens = text.strip().split()
    variants = [text] + tokens
    for i in range(len(tokens)):
        for length in [2, 3]:
            if i + length <= len(tokens):
                variants.append(" ".join(tokens[i:i+length]))
    return sorted(list(set(variants)), key=len, reverse=True)


# ═══════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class SemanticPipeline:
    def __init__(self):
        self.engine = MatchingEngine(threshold_fuzzy=78, threshold_embedding=0.65)

    def process_item(
        self,
        text: str,
        db_items: List[DBItem],
        concession_id: int,
        concession_index=None,
    ) -> Dict[str, Any]:
        
        text_type = _classify(text)

        base = {
            "texte_original": text,
            "texte_corrige": text,
            "texte_normalise": text,
            "texte_traduit": text,
            "langue_detectee": "unknown",
            "embedding": None,
            "action": "skip",
            "item_id": None,
            "score": 0.0,
            "niveau": None,
            "candidates": [],
            "text_type": text_type,
        }

        if text_type in ('empty', 'noise'):
            base["reason"] = "bruit OCR" if text_type == 'noise' else "vide"
            return base
        if text_type == 'doc_ref':
            base["reason"] = "référence document"
            base["langue_detectee"] = "ref"
            return base

        # ====================== CAS NOMBRE ======================
        if text_type == 'number':
            variants = get_number_variants(text)
            for item in db_items:
                if set(variants) & set(get_number_variants(item.libelle_canonique)):
                    base.update({
                        "action": "high_confidence",
                        "item_id": item.id_item,
                        "score": 1.0,
                        "niveau": "exact",
                    })
                    return base
            base["action"] = "create_new"
            return base

        # ====================== CAS TEXTE (INTELLIGENT) ======================
        # Utilisation du correcteur universel
        texte_corrige = universal_corrector.correct_text(text, db_items, concession_id)
        base["texte_corrige"] = texte_corrige

        texte_normalise = normalize_text(texte_corrige)
        base["texte_normalise"] = texte_normalise

        # Langue + Traduction supplémentaire si besoin
        langue = detect_language(text)
        base["langue_detectee"] = langue

        if langue == 'en':
            texte_traduit = translate_en_to_fr(texte_normalise)
            if texte_traduit != texte_normalise:
                texte_normalise = texte_traduit
                base["texte_traduit"] = texte_traduit

        # Nombre en lettres
        numeric_value = words_to_number(texte_normalise)
        if numeric_value is not None:
            texte_normalise = str(numeric_value)
            base["texte_normalise"] = texte_normalise

        # Variantes sémantiques + Embedding
        variantes_composees = decompose_texte_compose(texte_normalise)
        vocab_cache = _vocab_cache.get(concession_id)
        variants = expand_synonyms(texte_normalise, vocab_cache=vocab_cache)

        if EMBEDDING_AVAILABLE:
            emb = encode_with_variants(texte_normalise, variants)
            if emb is not None:
                base["embedding"] = emb.tobytes()

        # Matching final
        result = self.engine.match(
            query=text,
            items=db_items,
            normalized_query=texte_normalise,
            concession_index=concession_index,
            variants_composees=variantes_composees,
        )

        # Décision
        if result.matched and result.score >= 0.88:
            action = "high_confidence"
        elif result.matched and result.score >= 0.60:
            action = "needs_validation"
        else:
            action = "create_new"

        base.update({
            "action": action,
            "item_id": result.item_id if result.matched else None,
            "score": result.score,
            "niveau": result.level.value if result.matched else None,
            "candidates": result.candidates[:5] if result.candidates else [],
        })

        return base

    def process_batch(
        self,
        texts: List[str],
        db_items: List[DBItem],
        concession_id: int,
    ) -> List[Dict[str, Any]]:
        
        if db_items and concession_id not in _vocab_cache:
            all_words = [w for item in db_items for w in item.libelle_recherche.split()]
            precompute_vocab_embeddings(concession_id, all_words)

        concession_index = None
        if EMBEDDING_AVAILABLE and db_items:
            concession_index = get_or_build_index(
                concession_id=concession_id,
                item_ids=[i.id_item for i in db_items],
                item_texts=[i.libelle_recherche for i in db_items],
                item_labels=[i.libelle_canonique for i in db_items],
            )

        return [self.process_item(t, db_items, concession_id, concession_index) for t in texts]