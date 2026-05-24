"""
Moteur de matching sémantique 3 niveaux avec support des nombres.
OPTIMISATIONS :
  - imports remontés au niveau module (plus de from … import … dans les méthodes)
  - choices dict mis en cache par concession_id (plus de reconstruction à chaque appel)
  - encode() sorti de la boucle items → 1 seul appel batch
  - _match_composed_text ne recharge plus translate/detect à chaque token
"""
import logging
from typing import List, Optional, Dict, Tuple
from enum import Enum
from functools import lru_cache
import hashlib

_log = logging.getLogger(__name__)

# ── Dépendances optionnelles — importées UNE SEULE FOIS au niveau module ──────
_FUZZY_AVAILABLE = False
_rprocess = None
_rfuzz    = None
try:
    from rapidfuzz import process as _rprocess, fuzz as _rfuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    _log.warning("RapidFuzz non disponible — niveau fuzzy désactivé")

_EMBEDDING_AVAILABLE = False
_search_embedding    = None
try:
    from ..embeddings.embedder import search_embedding as _search_embedding, EMBEDDING_AVAILABLE as _EMB
    _EMBEDDING_AVAILABLE = _EMB
except ImportError:
    _log.warning("Embedding non disponible — niveau embedding désactivé")

# Modules internes — également importés une seule fois
_get_number_variants = None
_translate_en_to_fr  = None
_detect_language     = None

def _load_helpers():
    """Charge les helpers internes une seule fois (lazy, thread-safe par le GIL)."""
    global _get_number_variants, _translate_en_to_fr, _detect_language
    if _get_number_variants is None:
        from ..preprocessing.numbers import get_number_variants
        _get_number_variants = get_number_variants
    if _translate_en_to_fr is None:
        from ..preprocessing.translator import translate_en_to_fr, detect_language
        _translate_en_to_fr = translate_en_to_fr
        _detect_language    = detect_language


# ── Types ────────────────────────────────────────────────────────────────────
class MatchLevel(str, Enum):
    EXACT       = "exact"
    FUZZY       = "fuzzy"
    EMBEDDING   = "embedding"
    TOKEN_MATCH = "token_match"
    NO_MATCH    = "no_match"


class MatchResult:
    """Résultat d'un matching sémantique."""

    def __init__(
        self,
        matched:    bool      = False,
        item_id:    int       = None,
        item_label: str       = None,
        score:      float     = 0.0,
        level:      MatchLevel = MatchLevel.NO_MATCH,
        candidates: List[dict] = None,
    ):
        self.matched    = matched
        self.item_id    = item_id
        self.item_label = item_label
        self.score      = score
        self.level      = level
        self.candidates = candidates or []

    def __repr__(self) -> str:
        return f"MatchResult(matched={self.matched}, score={self.score:.4f}, level={self.level})"


class DBItem:
    """Représentation légère d'un item de la base de données."""

    def __init__(self, id_item: int, libelle_recherche: str, libelle_canonique: str):
        self.id_item           = id_item
        self.libelle_recherche = libelle_recherche
        self.libelle_canonique = libelle_canonique


# ── Cache du dict choices (évite la reconstruction à chaque appel fuzzy) ─────
# Clé : hash des libelles + concession_id
_choices_cache: Dict[str, dict] = {}  # hash → choices
_choices_cache_max = 50


def _get_choices_key(items: List[DBItem]) -> str:
    raw = "".join(i.libelle_canonique for i in items[:100])
    return hashlib.md5(raw.encode()).hexdigest()


def _build_choices(items: List[DBItem]) -> dict:
    """Construit le dict {libelle/variant → DBItem} pour RapidFuzz."""
    _load_helpers()
    choices = {}
    for item in items:
        choices[item.libelle_canonique] = item
        # 🔥 CORRECTION: Convertir le tuple en liste avec list()
        for variant in list(_get_number_variants(item.libelle_canonique)):
            choices.setdefault(variant, item)
        for word in item.libelle_canonique.lower().split():
            choices.setdefault(word, item)
    return choices


def _get_or_build_choices(items: List[DBItem]) -> dict:
    if not items:
        return {}
    key = _get_choices_key(items)
    if key in _choices_cache:
        return _choices_cache[key]
    choices = _build_choices(items)
    if len(_choices_cache) >= _choices_cache_max:
        # Eviction simple : supprimer la moitié des entrées
        for k in list(_choices_cache.keys())[:_choices_cache_max // 2]:
            del _choices_cache[k]
    _choices_cache[key] = choices
    return choices


# ── Moteur ───────────────────────────────────────────────────────────────────
class MatchingEngine:
    """Moteur de matching sémantique 3 niveaux avec support des nombres."""

    def __init__(self, threshold_fuzzy: int = 75, threshold_embedding: float = 0.65):
        self.threshold_fuzzy     = threshold_fuzzy
        self.threshold_embedding = threshold_embedding
        _load_helpers()  # précharge les helpers une bonne fois

    # ─────────────────────────────────────────────────────────────────────────
    def _match_composed_text(self, query: str, items: List[DBItem]) -> MatchResult:
        """
        Match un texte composé en cherchant l'item qui contient le plus de tokens.
        La traduction et les imports ne sont plus refaits à chaque appel.
        """
        if not _FUZZY_AVAILABLE:
            return MatchResult()

        # Traduction complète si anglais (helpers déjà chargés)
        langue = _detect_language(query)
        if langue == 'en':
            translated = _translate_en_to_fr(query)
            if translated != query:
                _log.debug(f"Traduction complète: '{query}' → '{translated}'")
                query = translated

        tokens = query.lower().split()
        if len(tokens) <= 1:
            return MatchResult()

        best_item         = None
        best_score        = 0.0
        best_item_label   = None

        for item in items:
            item_lower     = item.libelle_canonique.lower()
            item_recherche = item.libelle_recherche.lower()
            matched_count  = 0
            token_scores   = []

            for token in tokens:
                # 🔥 CORRECTION: Convertir le tuple en liste
                variants = [token] + list(_get_number_variants(token))
                best_token_score  = 0.0

                for variant in variants:
                    if variant in item_lower or variant in item_recherche:
                        best_token_score = 1.0
                        break
                    if len(variant) > 2:
                        score = _rfuzz.token_sort_ratio(variant, item_lower) / 100.0
                        if score > best_token_score:
                            best_token_score = score * 0.85

                if best_token_score > 0.6:
                    matched_count += 1
                    token_scores.append(best_token_score)

            if matched_count > 0:
                token_ratio = matched_count / len(tokens)
                avg_score   = sum(token_scores) / len(token_scores) if token_scores else 0.7
                item_score  = (token_ratio * 0.75) + (avg_score * 0.2)

                if item_score > best_score:
                    best_score      = item_score
                    best_item       = item
                    best_item_label = item.libelle_canonique

        if best_item and best_score >= 0.65:
            return MatchResult(
                matched    = True,
                item_id    = best_item.id_item,
                item_label = best_item_label,
                score      = round(min(best_score, 0.92), 4),
                level      = MatchLevel.FUZZY,
            )
        return MatchResult()

    # ─────────────────────────────────────────────────────────────────────────
    def match(
        self,
        query:              str,
        items:              List[DBItem],
        normalized_query:   str = None,
        concession_index    = None,
        variants_composees: Optional[List[str]] = None,
    ) -> MatchResult:
        """Match une requête contre une liste d'items (3 niveaux)."""
        if not query or not query.strip():
            return MatchResult()

        q       = query.strip()
        q_lower = q.lower()
        q_norm  = normalized_query or q_lower

        _log.debug(f"Matching : '{q_lower}' contre {len(items)} items")

        # ── L1 — EXACT ───────────────────────────────────────────────────────
        for item in items:
            if item.libelle_canonique.strip().lower() == q_lower:
                return MatchResult(True, item.id_item, item.libelle_canonique, 1.0, MatchLevel.EXACT)
            if item.libelle_recherche == q_norm:
                return MatchResult(True, item.id_item, item.libelle_canonique, 1.0, MatchLevel.EXACT)

        # ── L1.5 — TEXTE COMPOSÉ ─────────────────────────────────────────────
        if len(q_lower.split()) > 1:
            result = self._match_composed_text(q_lower, items)
            if result.matched:
                _log.debug(f"  → COMPOSED: {result.item_label} ({result.score:.2f})")
                return result

        # ── L2 — FUZZY ───────────────────────────────────────────────────────
        if _FUZZY_AVAILABLE and items:
            result = self._match_fuzzy(q_lower, items)
            if result.matched:
                _log.debug(f"  → FUZZY: {result.item_label} ({result.score:.2f})")
                return result

        # ── L3 — EMBEDDING ───────────────────────────────────────────────────
        if _EMBEDDING_AVAILABLE and concession_index is not None:
            result = self._match_embedding(q_norm, concession_index)
            if result.matched:
                _log.debug(f"  → EMBEDDING: {result.item_label} ({result.score:.2f})")
                return result

        _log.debug("  → NO MATCH")
        return MatchResult()

    # ─────────────────────────────────────────────────────────────────────────
    def _match_token_by_token(self, query: str, items: List[DBItem]) -> MatchResult:
        """Match token par token avec support des fautes de frappe."""
        if not _FUZZY_AVAILABLE:
            return MatchResult()

        tokens = query.lower().split()
        if len(tokens) <= 1:
            return MatchResult()

        item_scores: Dict[int, dict] = {}

        for token in tokens:
            # 🔥 CORRECTION: Convertir le tuple en liste
            token_variants = [token] + list(_get_number_variants(token))
            best_token_score = 0.0
            best_token_item  = None

            for variant in token_variants:
                for item in items:
                    item_lower = item.libelle_canonique.lower()

                    if variant in item_lower or variant in item.libelle_recherche.lower():
                        if 1.0 > best_token_score:
                            best_token_score = 1.0
                            best_token_item  = item
                        continue

                    if len(variant) > 2 and len(item_lower) > 2:
                        for item_word in (item_lower.split() + item.libelle_recherche.lower().split()):
                            if len(item_word) > 2:
                                fs = _rfuzz.ratio(variant, item_word) / 100.0
                                if fs > 0.75 and fs > best_token_score:
                                    best_token_score = fs * 0.9
                                    best_token_item  = item

                    elif len(variant) >= 3:
                        if item_lower.startswith(variant):
                            ms = len(variant) / max(len(item_lower), 1) * 0.85
                            if ms > best_token_score:
                                best_token_score = ms
                                best_token_item  = item

            if best_token_item:
                sid = best_token_item.id_item
                if sid not in item_scores:
                    item_scores[sid] = {"item": best_token_item, "tokens": set(), "scores": []}
                item_scores[sid]["tokens"].add(token)
                item_scores[sid]["scores"].append(best_token_score)

        if not item_scores:
            return MatchResult()

        best_id  = max(item_scores, key=lambda x: (
            len(item_scores[x]["tokens"]),
            sum(item_scores[x]["scores"]) / len(item_scores[x]["scores"]) if item_scores[x]["scores"] else 0,
        ))
        best     = item_scores[best_id]
        t_ratio  = len(best["tokens"]) / len(tokens)
        avg      = sum(best["scores"]) / len(best["scores"]) if best["scores"] else 0
        final    = min((t_ratio * 0.7) + (avg * 0.3), 0.95)

        if final >= 0.5:
            return MatchResult(
                matched    = True,
                item_id    = best["item"].id_item,
                item_label = best["item"].libelle_canonique,
                score      = round(final, 4),
                level      = MatchLevel.TOKEN_MATCH,
            )
        return MatchResult()

    # ─────────────────────────────────────────────────────────────────────────
    def _match_fuzzy(self, query_lower: str, items: List[DBItem]) -> MatchResult:
        """
        Matching fuzzy avec support nombres, fautes, troncatures.
        OPTIMISÉ : choices dict mis en cache, encode() sorti de la boucle.
        """
        if not _FUZZY_AVAILABLE:
            return MatchResult()

        query_clean = query_lower

        # Cas puits : "WAHA #3" → chercher le nom de base
        if '#' in query_lower:
            base = query_lower.split('#')[0].strip()
            if base and len(base) > 2:
                for item in items:
                    if base in item.libelle_canonique.lower():
                        return MatchResult(True, item.id_item, item.libelle_canonique, 0.85, MatchLevel.FUZZY)

        # Cas & → et
        if '&' in query_lower:
            qv = query_lower.replace('&', 'et')
            for item in items:
                if qv in item.libelle_canonique.lower():
                    return MatchResult(True, item.id_item, item.libelle_canonique, 0.85, MatchLevel.FUZZY)

        # 🔥 CORRECTION: Convertir le tuple en liste avec list()
        query_variants = [query_clean] + list(_get_number_variants(query_clean))
        query_variants = list(set(query_variants))
        
        tokens = query_lower.split()

        # Mot court / troncature
        if len(tokens) == 1 and len(query_lower) >= 3:
            translated = _translate_en_to_fr(query_lower)
            if translated != query_lower:
                for item in items:
                    if translated in item.libelle_canonique.lower() or translated in item.libelle_recherche.lower():
                        return MatchResult(True, item.id_item, item.libelle_canonique, 0.95, MatchLevel.FUZZY)

            for item in items:
                il = item.libelle_canonique.lower()
                if il.startswith(query_lower):
                    score = len(query_lower) / len(il) * 0.9
                    if score >= 0.6:
                        return MatchResult(True, item.id_item, item.libelle_canonique, round(score, 4), MatchLevel.FUZZY)

        # Matching sémantique batch (1 seul appel encode pour TOUS les items)
        if len(tokens) == 1 and len(query_lower) >= 3:
            try:
                from ..embeddings.embedder import _get_model, encode
                import numpy as np

                model = _get_model()
                if model is not None:
                    all_texts  = [query_lower] + [item.libelle_canonique for item in items]
                    all_embs   = encode(all_texts)
                    if all_embs is not None:
                        query_emb  = all_embs[0]
                        item_embs  = all_embs[1:]
                        sims       = item_embs @ query_emb
                        best_idx   = int(np.argmax(sims))
                        best_sim   = float(sims[best_idx])
                        if best_sim >= 0.70:
                            best_item = items[best_idx]
                            return MatchResult(True, best_item.id_item, best_item.libelle_canonique,
                                               round(best_sim, 4), MatchLevel.EMBEDDING)
            except Exception as e:
                _log.debug(f"Erreur matching sémantique batch: {e}")

        # ── Matching RapidFuzz avec choices mis en cache ──────────────────────
        choices    = _get_or_build_choices(items)
        best_score = 0
        best_item  = None

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
                    best_item  = choices[results[0][0]]
            except Exception as e:
                _log.error(f"Erreur fuzzy pour variant '{variant}': {e}")

        # Fallback substring
        if best_score < self.threshold_fuzzy and len(tokens) == 1 and len(query_lower) >= 3:
            for item in items:
                il = item.libelle_canonique.lower()
                if query_lower in il:
                    score = len(query_lower) / len(il) * 0.8
                    if score > best_score / 100.0:
                        best_score = score * 100
                        best_item  = item

        if best_score >= self.threshold_fuzzy and best_item:
            return MatchResult(
                matched    = True,
                item_id    = best_item.id_item,
                item_label = best_item.libelle_canonique,
                score      = round(best_score / 100.0, 4),
                level      = MatchLevel.FUZZY,
            )

        return MatchResult()

    # ─────────────────────────────────────────────────────────────────────────
    def _match_embedding(self, query_norm: str, concession_index) -> MatchResult:
        """Matching par similarité cosinus (FAISS)."""
        if not _EMBEDDING_AVAILABLE or _search_embedding is None:
            return MatchResult()

        try:
            candidates = _search_embedding(query_norm, [], concession_index, top_k=5)
            if candidates:
                best = candidates[0]
                if best["score"] >= self.threshold_embedding:
                    return MatchResult(
                        matched    = True,
                        item_id    = best["item_id"],
                        item_label = best["label"],
                        score      = round(best["score"], 4),
                        level      = MatchLevel.EMBEDDING,
                        candidates = candidates,
                    )
        except Exception as e:
            _log.error(f"Erreur embedding : {e}")

        return MatchResult()