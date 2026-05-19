"""
Pipeline sémantique complet avec classification intelligente.
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


# ═══════════════════════════════════════════════════════════════
# FONCTIONS DE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def _is_doc_reference(text: str) -> bool:
    """Détecte une référence de document (devis, facture, BL...)."""
    return bool(_DOC_REF_RE.search(text))


@lru_cache(maxsize=1000)
def _is_number(text: str) -> bool:
    """Détecte si un texte est un nombre/montant."""
    if not text or not text.strip():
        return False

    t = text.strip()

    if re.search(r'\d\s*/\s*\d', t) or re.search(r'\d\s*:\s*\d', t):
        return False

    cleaned = re.sub(r'[\s\u00a0]', '', t)
    cleaned = re.sub(r"[()%€$£\-+]", '', cleaned)

    if re.fullmatch(r'\d{1,3}(\.\d{3})*(,\d+)?', cleaned):
        return True
    if re.fullmatch(r'\d{1,3}(,\d{3})*(\.\d+)?', cleaned):
        return True
    if re.fullmatch(r'\d+([.,]\d+)?', cleaned):
        return True

    digit_count = sum(1 for c in cleaned if c.isdigit() or c in '.,')
    return len(cleaned) > 0 and digit_count / len(cleaned) > 0.75


def _is_ocr_noise(text: str) -> bool:
    """Détecte le bruit OCR."""
    if not text or len(text) < 2:
        return True
    if any(c in text for c in '=|+*#@!<>?\\[]{}'):
        return True

    letters = [c for c in text.lower() if c.isalpha()]
    if letters and len(letters) > 4:
        if sum(1 for c in letters if c in 'aeiouy') == 0:
            return True

    return False


def _classify(text: str) -> str:
    """Classifie le texte extrait."""
    if not text or not text.strip():
        return 'empty'
    if _is_doc_reference(text):
        return 'doc_ref'
    if _is_number(text):
        return 'number'
    if _is_ocr_noise(text):
        return 'noise'
    return 'text'


# ═══════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class SemanticPipeline:
    """Pipeline sémantique intelligent avec classification."""

    def __init__(self):
        self.engine = MatchingEngine(threshold_fuzzy=85, threshold_embedding=0.70)

    def process_item(
        self,
        text: str,
        db_items: List[DBItem],
        concession_id: int,
        concession_index=None,
    ) -> Dict[str, Any]:
        """Traite un item extrait et retourne le résultat du matching."""
        text_type = _classify(text)

        _log.debug(
            f"process_item : '{text}' → type={text_type}, "
            f"items={len(db_items)}, index={concession_index is not None}"
        )

        base = {
            "texte_original": text,
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

        # ── CAS 1 : Vide ou bruit → ignorer ─────────────────────────────────
        if text_type in ('empty', 'noise'):
            base["reason"] = "bruit OCR" if text_type == 'noise' else "vide"
            return base

        # ── CAS 2 : Référence document → ignorer ────────────────────────────
        if text_type == 'doc_ref':
            base["reason"] = "référence document"
            base["langue_detectee"] = "ref"
            return base

        # ── CAS 3 : Nombre → matching EXACT + FUZZY avec variantes ──────────
        if text_type == 'number':
            variants = get_number_variants(text)
            _log.debug(f"Nombre '{text}' → variants : {variants}")

            # Chercher un match exact
            for item in db_items:
                item_variants = get_number_variants(item.libelle_canonique)
                if set(variants) & set(item_variants):
                    base.update({
                        "action": "high_confidence",
                        "item_id": item.id_item,
                        "score": 1.0,
                        "niveau": "exact",
                        "reason": "nombre identique (chiffre/mot)",
                        "langue_detectee": "number",
                    })
                    return base

            # Chercher en fuzzy
            if _FUZZY_AVAILABLE:
                for variant in variants:
                    for item in db_items:
                        item_variants = get_number_variants(item.libelle_canonique)
                        for iv in item_variants:
                            score = _rfuzz.token_sort_ratio(variant, iv)
                            if score >= 85:
                                base.update({
                                    "action": "needs_validation",
                                    "item_id": item.id_item,
                                    "score": round(score / 100.0, 4),
                                    "niveau": "fuzzy",
                                    "reason": "nombre similaire (fuzzy)",
                                    "langue_detectee": "number",
                                })
                                return base

            base["action"] = "create_new"
            base["reason"] = "nouveau nombre"
            return base

        # ── CAS 4 : Texte normal → pipeline complet ─────────────────────────
        texte_normalise = normalize_text(text)
        
        # Traduction EN→FR si nécessaire
        langue = detect_language(text)
        base["langue_detectee"] = langue
        
        if langue == 'en':
            texte_traduit = translate_en_to_fr(texte_normalise)
            if texte_traduit != texte_normalise:
                _log.debug(f"Traduction EN→FR: '{texte_normalise}' → '{texte_traduit}'")
                texte_normalise = texte_traduit
                base["texte_traduit"] = texte_traduit
        
        base["texte_normalise"] = texte_normalise

        # Vérifier si le texte est un nombre en lettres
        numeric_value = words_to_number(texte_normalise)
        if numeric_value is not None:
            _log.debug(f"Nombre en lettres détecté: '{texte_normalise}' → {numeric_value}")
            # Ajouter une variante numérique
            texte_normalise = str(numeric_value)
            base["texte_normalise"] = texte_normalise

        # Synonymes avec vocabulaire pré-calculé
        vocab_cache = _vocab_cache.get(concession_id)
        variants = expand_synonyms(texte_normalise, vocab_cache=vocab_cache)

        # Embedding
        if EMBEDDING_AVAILABLE:
            emb = encode_with_variants(texte_normalise, variants)
            if emb is not None:
                base["embedding"] = emb.tobytes()

        # Matching
        result = self.engine.match(
            query=text,
            items=db_items,
            normalized_query=texte_normalise,
            concession_index=concession_index,
        )

        _log.debug(
            f"  → result : matched={result.matched}, "
            f"score={result.score:.4f}, level={result.level}"
        )

        # Décision
        if result.matched and result.score >= 0.95:
            action = "high_confidence"
        elif result.matched and result.score >= 0.70:
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
        """Traite un lot de textes."""
        _log.info(
            f"process_batch : {len(texts)} textes, "
            f"{len(db_items)} items, concession={concession_id}"
        )

        if db_items and concession_id not in _vocab_cache:
            all_words = []
            for item in db_items:
                all_words.extend(item.libelle_recherche.split())
            precompute_vocab_embeddings(concession_id, all_words)

        concession_index = None
        if EMBEDDING_AVAILABLE and db_items:
            concession_index = get_or_build_index(
                concession_id=concession_id,
                item_ids=[i.id_item for i in db_items],
                item_texts=[i.libelle_recherche for i in db_items],
                item_labels=[i.libelle_canonique for i in db_items],
            )

        results = [
            self.process_item(t, db_items, concession_id, concession_index)
            for t in texts
        ]

        stats = {
            "exact": sum(1 for r in results if r.get("niveau") == "exact"),
            "fuzzy": sum(1 for r in results if r.get("niveau") == "fuzzy"),
            "embedding": sum(1 for r in results if r.get("niveau") == "embedding"),
            "high_confidence": sum(1 for r in results if r["action"] == "high_confidence"),
            "needs_validation": sum(1 for r in results if r["action"] == "needs_validation"),
            "create_new": sum(1 for r in results if r["action"] == "create_new"),
            "skip": sum(1 for r in results if r["action"] == "skip"),
        }
        _log.info(f"Pipeline stats : {stats}")

        return results