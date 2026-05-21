"""
Moteur de matching sémantique 3 niveaux avec support des nombres.
"""
import logging
from typing import List, Optional
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
    TOKEN_MATCH = "token_match"
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

    def _match_composed_text(self, query: str, items: List[DBItem]) -> MatchResult:
        """
        Match un texte composé en cherchant l'item qui contient le PLUS de tokens.
        Ex: "bonjour 12" → cherche un item contenant "bonjour"
        Ex: "good mornin" → traduit d'abord en "bonjour" puis cherche
        """
        if not _FUZZY_AVAILABLE:
            return MatchResult()
        
        from ..preprocessing.numbers import get_number_variants
        from ..preprocessing.translator import translate_en_to_fr, detect_language
        from rapidfuzz import fuzz as _rfuzz
        
        # 🔥 Étape 1 : Traduire la requête complète si elle est en anglais
        langue = detect_language(query)
        query_original = query
        if langue == 'en':
            translated_query = translate_en_to_fr(query)
            if translated_query != query:
                _log.debug(f"Traduction complète: '{query}' → '{translated_query}'")
                query = translated_query
        
        tokens = query.lower().split()
        if len(tokens) <= 1:
            return MatchResult()
        
        best_item = None
        best_score = 0.0
        best_matched_count = 0
        best_item_label = None
        
        for item in items:
            item_lower = item.libelle_canonique.lower()
            item_recherche = item.libelle_recherche.lower()
            matched_count = 0
            token_scores = []
            
            for token in tokens:
                variants = [token] + get_number_variants(token)
                best_token_score = 0
                
                for variant in variants:
                    # Match exact
                    if variant in item_lower or variant in item_recherche:
                        best_token_score = 1.0
                        break
                    
                    # Fuzzy
                    if len(variant) > 2:
                        score = _rfuzz.token_sort_ratio(variant, item_lower) / 100.0
                        if score > best_token_score:
                            best_token_score = score * 0.85
                
                if best_token_score > 0.6:
                    matched_count += 1
                    token_scores.append(best_token_score)
            
            if matched_count > 0:
                token_ratio = matched_count / len(tokens)
                avg_score = sum(token_scores) / len(token_scores) if token_scores else 0.7
                
                item_score = (token_ratio * 0.75) + (avg_score * 0.2)
                
                if item_score > best_score:
                    best_score = item_score
                    best_matched_count = matched_count
                    best_item = item
                    best_item_label = item.libelle_canonique
        
        if best_item and best_score >= 0.65:
            final_score = min(best_score, 0.92)
            return MatchResult(
                matched=True,
                item_id=best_item.id_item,
                item_label=best_item_label,
                score=round(final_score, 4),
                level=MatchLevel.FUZZY,
            )
        
        return MatchResult()

    def match(
        self,
        query: str,
        items: List[DBItem],
        normalized_query: str = None,
        concession_index=None,
        variants_composees: Optional[List[str]] = None,
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
        # L1.5 — TEXTE COMPOSÉ (match partiel sur tokens)
        # ═══════════════════════════════════════════════════════
        if len(q_lower.split()) > 1:
            result = self._match_composed_text(q_lower, items)
            if result.matched:
                _log.debug(f"  → COMPOSED MATCH: {result.item_label} ({result.score:.2f})")
                return result

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

    def _match_token_by_token(self, query: str, items: List[DBItem]) -> MatchResult:
        """Match un texte en décomposant en tokens avec support des fautes de frappe."""
        if not _FUZZY_AVAILABLE:
            return MatchResult()
        
        from ..preprocessing.numbers import get_number_variants
        from rapidfuzz import fuzz as _rfuzz
        
        tokens = query.lower().split()
        if len(tokens) <= 1:
            return MatchResult()
        
        item_scores = {}
        
        for token in tokens:
            token_variants = [token] + get_number_variants(token)
            best_token_score = 0
            best_token_item = None
            
            for variant in token_variants:
                for item in items:
                    if variant in item.libelle_canonique.lower() or variant in item.libelle_recherche.lower():
                        match_score = 1.0
                        if match_score > best_token_score:
                            best_token_score = match_score
                            best_token_item = item
                    
                    elif len(variant) > 2 and len(item.libelle_canonique.lower()) > 2:
                        item_words = item.libelle_canonique.lower().split() + item.libelle_recherche.lower().split()
                        for item_word in item_words:
                            if len(item_word) > 2:
                                fuzzy_score = _rfuzz.ratio(variant, item_word) / 100.0
                                if fuzzy_score > 0.75 and fuzzy_score > best_token_score:
                                    best_token_score = fuzzy_score * 0.9
                                    best_token_item = item
                    
                    elif len(variant) >= 3:
                        item_lower = item.libelle_canonique.lower()
                        if item_lower.startswith(variant) or variant.startswith(item_lower[:len(variant)]):
                            match_score = len(variant) / max(len(item_lower), 1) * 0.85
                            if match_score > best_token_score:
                                best_token_score = match_score
                                best_token_item = item
            
            if best_token_item:
                if best_token_item.id_item not in item_scores:
                    item_scores[best_token_item.id_item] = {
                        "item": best_token_item, 
                        "tokens": set(), 
                        "scores": []
                    }
                item_scores[best_token_item.id_item]["tokens"].add(token)
                item_scores[best_token_item.id_item]["scores"].append(best_token_score)
        
        if not item_scores:
            return MatchResult()
        
        best_item_id = max(item_scores.keys(), key=lambda x: (
            len(item_scores[x]["tokens"]),
            sum(item_scores[x]["scores"]) / len(item_scores[x]["scores"]) if item_scores[x]["scores"] else 0
        ))
        best = item_scores[best_item_id]
        
        token_ratio = len(best["tokens"]) / len(tokens)
        avg_score = sum(best["scores"]) / len(best["scores"]) if best["scores"] else 0
        final_score = (token_ratio * 0.7) + (avg_score * 0.3)
        final_score = min(final_score, 0.95)
        
        if final_score >= 0.5:
            _log.debug(f"Token match: {query} → {best['item'].libelle_canonique} (ratio={token_ratio:.2f}, score={final_score:.2f})")
            return MatchResult(
                matched=True,
                item_id=best["item"].id_item,
                item_label=best["item"].libelle_canonique,
                score=round(final_score, 4),
                level=MatchLevel.TOKEN_MATCH,
            )
        
        return MatchResult()

    def _match_fuzzy(self, query_lower: str, items: List[DBItem]) -> MatchResult:
        """Matching fuzzy avec support des nombres, fautes de frappe et troncatures."""
        if not _FUZZY_AVAILABLE:
            return MatchResult()

        from ..preprocessing.numbers import get_number_variants
        from ..preprocessing.translator import translate_en_to_fr
        from rapidfuzz import fuzz as _rfuzz
        
        query_variants = [query_lower] + get_number_variants(query_lower)
        query_variants = list(set(query_variants))
        
        tokens = query_lower.split()
        
        # 2. Cas particulier : mot court ou troncature
        if len(tokens) == 1 and len(query_lower) >= 3:
            translated = translate_en_to_fr(query_lower)
            if translated != query_lower:
                for item in items:
                    if translated in item.libelle_canonique.lower() or translated in item.libelle_recherche.lower():
                        return MatchResult(
                            matched=True,
                            item_id=item.id_item,
                            item_label=item.libelle_canonique,
                            score=0.95,
                            level=MatchLevel.FUZZY,
                        )
            
            for item in items:
                item_lower = item.libelle_canonique.lower()
                if item_lower.startswith(query_lower):
                    score = len(query_lower) / len(item_lower) * 0.9
                    if score >= 0.6:
                        return MatchResult(
                            matched=True,
                            item_id=item.id_item,
                            item_label=item.libelle_canonique,
                            score=round(score, 4),
                            level=MatchLevel.FUZZY,
                        )
        
        # 3. Matching sémantique pour les mots inconnus
        if len(tokens) == 1 and len(query_lower) >= 3:
            try:
                from ..embeddings.embedder import _get_model, encode
                import numpy as np
                
                model = _get_model()
                if model is not None:
                    query_emb = encode([query_lower])
                    if query_emb is not None:
                        best_semantic_score = 0
                        best_semantic_item = None
                        
                        for item in items:
                            item_emb = encode([item.libelle_canonique])
                            if item_emb is not None:
                                sim = float(np.dot(query_emb[0], item_emb[0]))
                                if sim > best_semantic_score:
                                    best_semantic_score = sim
                                    best_semantic_item = item
                        
                        if best_semantic_score >= 0.70:
                            return MatchResult(
                                matched=True,
                                item_id=best_semantic_item.id_item,
                                item_label=best_semantic_item.libelle_canonique,
                                score=round(best_semantic_score, 4),
                                level=MatchLevel.EMBEDDING,
                            )
            except Exception as e:
                _log.debug(f"Erreur matching sémantique: {e}")
        
        # 4. Matching normal avec RapidFuzz
        choices = {}
        for item in items:
            choices[item.libelle_canonique] = item
            item_variants = get_number_variants(item.libelle_canonique)
            for variant in item_variants:
                if variant not in choices:
                    choices[variant] = item
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

        # 5. Fallback
        if best_score < self.threshold_fuzzy and len(tokens) == 1 and len(query_lower) >= 3:
            for item in items:
                item_lower = item.libelle_canonique.lower()
                if query_lower in item_lower:
                    score = len(query_lower) / len(item_lower) * 0.8
                    if score > best_score / 100.0:
                        best_score = score * 100
                        best_item = item

        if best_score >= self.threshold_fuzzy and best_item:
            normalized_score = best_score / 100.0
            return MatchResult(
                matched=True,
                item_id=best_item.id_item,
                item_label=best_item.libelle_canonique,
                score=round(normalized_score, 4),
                level=MatchLevel.FUZZY,
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