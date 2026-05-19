"""
Moteur de matching sémantique 3 niveaux avec support des nombres.
"""
import logging
from typing import List
from enum import Enum

_log = logging.getLogger(__name__)

# ── Dépendances optionnelles ─────────────────────────────────────────────────
_FUZZY_AVAILABLE = False
try:
    from rapidfuzz import fuzz as _rfuzz, process as _rprocess
    _FUZZY_AVAILABLE = True
except ImportError:
    _log.warning("RapidFuzz non disponible — niveau fuzzy désactivé")

_EMBEDDING_AVAILABLE = False
try:
    from ..embeddings.embedder import search_embedding, EMBEDDING_AVAILABLE as _EMB
    _EMBEDDING_AVAILABLE = _EMB
except ImportError:
    _log.warning("Embedding non disponible — niveau embedding désactivé")


# ── Types ────────────────────────────────────────────────────────────────────
class MatchLevel(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    EMBEDDING = "embedding"
    NO_MATCH = "no_match"


class MatchResult:
    """Résultat d'un matching sémantique."""

    def __init__(
        self,
        matched: bool = False,
        item_id: int = None,
        item_label: str = None,
        score: float = 0.0,
        level: MatchLevel = MatchLevel.NO_MATCH,
        candidates: List[dict] = None,
    ):
        self.matched = matched
        self.item_id = item_id
        self.item_label = item_label
        self.score = score
        self.level = level
        self.candidates = candidates or []

    def __repr__(self) -> str:
        return f"MatchResult(matched={self.matched}, score={self.score:.4f}, level={self.level})"


class DBItem:
    """Représentation légère d'un item de la base de données."""

    def __init__(self, id_item: int, libelle_recherche: str, libelle_canonique: str):
        self.id_item = id_item
        self.libelle_recherche = libelle_recherche
        self.libelle_canonique = libelle_canonique


# ── Moteur ───────────────────────────────────────────────────────────────────
class MatchingEngine:
    """Moteur de matching sémantique 3 niveaux avec support des nombres."""

    def __init__(self, threshold_fuzzy: int = 85, threshold_embedding: float = 0.70):
        self.threshold_fuzzy = threshold_fuzzy
        self.threshold_embedding = threshold_embedding

    def match(
        self,
        query: str,
        items: List[DBItem],
        normalized_query: str = None,
        concession_index=None,
    ) -> MatchResult:
        """Match une requête contre une liste d'items."""
        if not query or not query.strip():
            return MatchResult()

        q = query.strip()
        q_lower = q.lower()
        q_norm = normalized_query or q_lower

        _log.debug(f"Matching : '{q_lower}' contre {len(items)} items")

        # ═══════════════════════════════════════════════════════
        # L1 — EXACT
        # ═══════════════════════════════════════════════════════
        for item in items:
            if item.libelle_canonique.strip().lower() == q_lower:
                _log.debug(f"  → EXACT canonique : {item.libelle_canonique}")
                return MatchResult(
                    matched=True,
                    item_id=item.id_item,
                    item_label=item.libelle_canonique,
                    score=1.0,
                    level=MatchLevel.EXACT,
                )
            if item.libelle_recherche == q_norm:
                _log.debug(f"  → EXACT recherche : {item.libelle_recherche}")
                return MatchResult(
                    matched=True,
                    item_id=item.id_item,
                    item_label=item.libelle_canonique,
                    score=1.0,
                    level=MatchLevel.EXACT,
                )

        # ═══════════════════════════════════════════════════════
        # L2 — FUZZY (avec support des nombres)
        # ═══════════════════════════════════════════════════════
        if _FUZZY_AVAILABLE and items:
            result = self._match_fuzzy(q_lower, items)
            if result.matched:
                _log.debug(f"  → FUZZY : {result.item_label} ({result.score:.2f})")
                return result

        # ═══════════════════════════════════════════════════════
        # L3 — EMBEDDING
        # ═══════════════════════════════════════════════════════
        if _EMBEDDING_AVAILABLE and concession_index is not None:
            result = self._match_embedding(q_norm, concession_index)
            if result.matched:
                _log.debug(f"  → EMBEDDING : {result.item_label} ({result.score:.2f})")
                return result

        _log.debug("  → NO MATCH")
        return MatchResult()

    def _match_fuzzy(self, query_lower: str, items: List[DBItem]) -> MatchResult:
        """Matching fuzzy avec RapidFuzz et support des nombres."""
        if not _FUZZY_AVAILABLE:
            return MatchResult()

        # Générer les variantes du nombre (ex: quinze → 15)
        from ..preprocessing.numbers import get_number_variants
        query_variants = [query_lower] + get_number_variants(query_lower)
        query_variants = list(set(query_variants))  # Dédupliquer

        # Construire un dictionnaire de recherche avec variantes des items
        choices = {}
        for item in items:
            choices[item.libelle_canonique] = item
            # Ajouter les variantes de l'item
            item_variants = get_number_variants(item.libelle_canonique)
            for variant in item_variants:
                if variant not in choices:
                    choices[variant] = item
            # Ajouter aussi les mots individuels
            for word in item.libelle_canonique.lower().split():
                if word not in choices:
                    choices[word] = item

        best_score = 0
        best_match = None
        best_item = None

        for variant in query_variants:
            try:
                results = _rprocess.extract(
                    variant,
                    list(choices.keys()),
                    scorer=_rfuzz.token_sort_ratio,
                    limit=5,
                )
                if results and results[0][1] > best_score:
                    best_score = results[0][1]
                    best_match = results[0][0]
                    best_item = choices[best_match]
            except Exception as e:
                _log.error(f"Erreur fuzzy pour variant '{variant}': {e}")
                continue

        if best_score >= self.threshold_fuzzy and best_item:
            candidates = []
            return MatchResult(
                matched=True,
                item_id=best_item.id_item,
                item_label=best_item.libelle_canonique,
                score=round(best_score / 100.0, 4),
                level=MatchLevel.FUZZY,
                candidates=candidates,
            )

        return MatchResult()

    def _match_embedding(self, query_norm: str, concession_index) -> MatchResult:
        """Matching par similarité cosinus (FAISS)."""
        if not _EMBEDDING_AVAILABLE:
            return MatchResult()

        try:
            candidates = search_embedding(query_norm, [], concession_index, top_k=5)
            if candidates:
                best = candidates[0]
                if best["score"] >= self.threshold_embedding:
                    return MatchResult(
                        matched=True,
                        item_id=best["item_id"],
                        item_label=best["label"],
                        score=round(best["score"], 4),
                        level=MatchLevel.EMBEDDING,
                        candidates=candidates,
                    )
        except Exception as e:
            _log.error(f"Erreur embedding : {e}")

        return MatchResult()