"""Moteur de matching sémantique 4 niveaux - Version améliorée"""
import logging
from typing import List
from enum import Enum

from .normalizer import normalize_text
from .synonyms import expand_synonyms
from .embedder import search_embedding, EMBEDDING_AVAILABLE

_log = logging.getLogger(__name__)

_FUZZY_AVAILABLE = False
try:
    from rapidfuzz import fuzz as _rfuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    pass


class MatchLevel(str, Enum):
    EXACT = "exact"
    SYNONYM = "synonym"
    FUZZY = "fuzzy"
    EMBEDDING = "embedding"
    NO_MATCH = "no_match"


class MatchResult:
    def __init__(self, matched=False, item_id=None, item_label=None, score=0.0,
                 level=MatchLevel.NO_MATCH, candidates=None):
        self.matched = matched
        self.item_id = item_id
        self.item_label = item_label
        self.score = score
        self.level = level
        self.candidates = candidates or []


class DBItem:
    def __init__(self, id_item: int, libelle_recherche: str, libelle_canonique: str):
        self.id_item = id_item
        self.libelle_recherche = libelle_recherche
        self.libelle_canonique = libelle_canonique


class MatchingEngine:
    def __init__(self, threshold_fuzzy: int = 75, threshold_embedding: float = 0.70):
        self.threshold_fuzzy = threshold_fuzzy
        self.threshold_embedding = threshold_embedding

    def match(self, query: str, items: List[DBItem], concession_index=None,
              context_boost: float = 0.0) -> MatchResult:
        if not query or not query.strip():
            return MatchResult()

        norm_query = normalize_text(query)
        query_variants = expand_synonyms(norm_query)

        # L1 — Exact
        for item in items:
            if item.libelle_recherche == norm_query:
                return MatchResult(matched=True, item_id=item.id_item,
                                   item_label=item.libelle_canonique, score=1.0,
                                   level=MatchLevel.EXACT)

        # L2 — Synonymes
        query_set = set(query_variants)
        for item in items:
            item_set = set(expand_synonyms(item.libelle_recherche))
            if query_set & item_set:
                return MatchResult(matched=True, item_id=item.id_item,
                                   item_label=item.libelle_canonique, score=0.95,
                                   level=MatchLevel.SYNONYM)

        # L3 — Fuzzy
        if _FUZZY_AVAILABLE:
            best_score, best_item = 0, None
            for item in items:
                for qv in query_variants[:6]:
                    for iv in expand_synonyms(item.libelle_recherche)[:6]:
                        score = max(
                            _rfuzz.token_sort_ratio(qv, iv),
                            _rfuzz.token_set_ratio(qv, iv),
                            _rfuzz.partial_ratio(qv, iv),
                        )
                        if score > best_score:
                            best_score, best_item = score, item
            if best_item and best_score >= self.threshold_fuzzy:
                conf = min(best_score / 100.0 + context_boost, 0.99)
                return MatchResult(matched=True, item_id=best_item.id_item,
                                   item_label=best_item.libelle_canonique,
                                   score=conf, level=MatchLevel.FUZZY)

        # L4 — Embedding + Re-ranking
        if EMBEDDING_AVAILABLE and concession_index:
            candidates = search_embedding(norm_query, query_variants, concession_index, top_k=5)
            if candidates:
                # Re-ranking (amélioration importante)
                try:
                    from sentence_transformers import CrossEncoder
                    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")
                    pairs = [[norm_query, cand["label"]] for cand in candidates]
                    rerank_scores = reranker.predict(pairs)
                    for i, sc in enumerate(rerank_scores):
                        candidates[i]["rerank_score"] = float(sc)
                    candidates.sort(key=lambda x: x.get("rerank_score", x["score"]), reverse=True)
                except Exception:
                    pass

                best = candidates[0]
                if best["score"] >= self.threshold_embedding:
                    conf = min(best["score"] + context_boost, 0.99)
                    return MatchResult(matched=True, item_id=best["item_id"],
                                       item_label=best["label"], score=conf,
                                       level=MatchLevel.EMBEDDING, candidates=candidates)

        return MatchResult()