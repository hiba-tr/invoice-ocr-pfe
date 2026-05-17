"""
Module de traitement semantique intelligent.
Pipeline complet : normalisation → traduction → synonymes → embedding → matching.
"""

from .pipeline import SemanticPipeline
from .engine import MatchingEngine, MatchResult, DBItem
from .embedder import get_or_build_index, invalidate_cache, EMBEDDING_AVAILABLE
from .normalizer import normalize_text

__all__ = [
    "SemanticPipeline",
    "MatchingEngine",
    "MatchResult",
    "DBItem",
    "get_or_build_index",
    "invalidate_cache",
    "EMBEDDING_AVAILABLE",
    "normalize_text",
]