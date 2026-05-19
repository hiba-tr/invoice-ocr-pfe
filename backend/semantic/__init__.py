"""
Module de traitement sémantique intelligent.
"""

from .config import config, SemanticConfig
from .matching.pipeline import SemanticPipeline
from .matching.engine import MatchingEngine, MatchResult, DBItem
from .embeddings.indexer import get_or_build_index, invalidate_cache, EMBEDDING_AVAILABLE
from .preprocessing.normalizer import normalize_text

__all__ = [
    "config",
    "SemanticConfig",
    "SemanticPipeline",
    "MatchingEngine",
    "MatchResult",
    "DBItem",
    "get_or_build_index",
    "invalidate_cache",
    "EMBEDDING_AVAILABLE",
    "normalize_text",
]