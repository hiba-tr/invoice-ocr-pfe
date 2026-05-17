"""Pipeline sémantique complet - Version moderne"""
import logging
from typing import List, Dict, Any

from .normalizer import normalize_text
from .translator import translate_fr_to_en, detect_language
from .synonyms import expand_synonyms
from .embedder import encode_with_variants, get_or_build_index, EMBEDDING_AVAILABLE
from .engine import MatchingEngine, DBItem, MatchResult

_log = logging.getLogger(__name__)


class SemanticPipeline:
    """
    Pipeline sémantique intelligent utilisant IA (embedding + re-ranking).
    """

    def __init__(self):
        self.engine = MatchingEngine(threshold_fuzzy=75, threshold_embedding=0.70)

    def process_item(self, text: str, db_items: List[DBItem], concession_id: int,
                     concession_index=None) -> Dict[str, Any]:
        
        # 1. Normalisation
        texte_normalise = normalize_text(text)

        # 2. Détection langue + Traduction
        langue = detect_language(text)
        texte_traduit = translate_fr_to_en(text) if langue == "fr" else text

        # 3. Variants synonymes
        variants = expand_synonyms(texte_normalise)

        # 4. Embedding
        embedding_bytes = None
        if EMBEDDING_AVAILABLE:
            emb = encode_with_variants(texte_normalise, variants)
            if emb is not None:
                embedding_bytes = emb.tobytes()

        # 5. Matching
        result: MatchResult = self.engine.match(
            query=text,
            items=db_items,
            concession_index=concession_index,
        )

        # 6. Décision intelligente
        if result.matched and result.score >= 0.88:
            action = "auto_match"
        elif result.matched and result.score >= 0.65:
            action = "needs_validation"
        else:
            action = "create_new"

        return {
            "texte_original": text,
            "texte_normalise": texte_normalise,
            "texte_traduit": texte_traduit,
            "langue_detectee": langue,
            "embedding": embedding_bytes,
            "action": action,
            "item_id": result.item_id if result.matched else None,
            "score": round(float(result.score), 4),
            "niveau": result.level.value if result.matched else None,
            "candidates": result.candidates[:5] if result.candidates else [],
        }

    def process_batch(self, texts: List[str], db_items: List[DBItem],
                      concession_id: int) -> List[Dict[str, Any]]:
        
        concession_index = None
        if EMBEDDING_AVAILABLE and db_items:
            _log.info(f"Construction index FAISS pour concession {concession_id}...")
            concession_index = get_or_build_index(
                concession_id=concession_id,
                item_ids=[i.id_item for i in db_items],
                item_texts=[i.libelle_recherche for i in db_items],
                item_labels=[i.libelle_canonique for i in db_items],
            )

        results = []
        for text in texts:
            result = self.process_item(text, db_items, concession_id, concession_index)
            results.append(result)

        # Statistiques
        auto = sum(1 for r in results if r["action"] == "auto_match")
        validation = sum(1 for r in results if r["action"] == "needs_validation")
        new_items = sum(1 for r in results if r["action"] == "create_new")

        _log.info(f"Pipeline terminé → {auto} auto-match | {validation} à valider | {new_items} nouveaux")

        return results