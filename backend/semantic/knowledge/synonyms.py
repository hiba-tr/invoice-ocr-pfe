"""
Dictionnaire de synonymes intelligent - basé sur la similarité sémantique.
AUCUN dictionnaire statique - tout est calculé dynamiquement.
OPTIMISATIONS :
  - precompute_vocab_embeddings : 1 seul appel model.encode() (batch complet)
  - find_semantic_similarity : calcul matriciel vectorisé (vocab_matrix @ word_emb)
    au lieu d'une boucle np.dot() mot par mot → O(n) → O(1) numpy
  - _vocab_matrix_cache : matrice pré-assemblée par concession pour éviter
    la reconstruction à chaque recherche
"""
import logging
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
import numpy as np

from ..embeddings.embedder import _get_model

_log = logging.getLogger(__name__)

# ── Caches ────────────────────────────────────────────────────────────────────
# {concession_id: {word: embedding}}
_vocab_cache: Dict[int, Dict[str, np.ndarray]] = {}

# {concession_id: (matrix, words_list)} — matrice pré-assemblée pour numpy
_vocab_matrix_cache: Dict[int, Tuple[np.ndarray, List[str]]] = {}

SYNONYM_THRESHOLD = 0.70


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_word(word: str) -> str:
    """Normalise un mot : sans accents, sans ponctuation, en minuscule."""
    word = word.lower().strip()
    word = unicodedata.normalize('NFKD', word).encode('ASCII', 'ignore').decode('utf-8')
    word = re.sub(r'[^\w\s]', '', word)
    word = re.sub(r'\d+$', '', word)
    return word.strip()


def get_word_embedding(word: str, model) -> Optional[np.ndarray]:
    """Calcule l'embedding d'un mot individuel (usage ponctuel uniquement)."""
    if not word or len(word) < 2:
        return None
    try:
        emb = model.encode([word], convert_to_numpy=True, normalize_embeddings=True)
        return emb[0].astype("float32")
    except Exception:
        return None


# ── Pré-calcul du vocabulaire ─────────────────────────────────────────────────

def precompute_vocab_embeddings(concession_id: int, words: List[str]) -> None:
    """
    Pré-calcule les embeddings du vocabulaire d'une concession.
    OPTIMISÉ : UN SEUL appel model.encode() pour toute la liste,
    puis assemblage immédiat de la matrice numpy pour les recherches vectorisées.
    """
    if not words:
        return

    model = _get_model()
    if model is None:
        return

    # Normaliser et dédupliquer
    unique_words: Dict[str, str] = {}
    for w in words:
        norm = normalize_word(w)
        if norm and norm not in unique_words:
            unique_words[norm] = w

    if not unique_words:
        return

    word_list = list(unique_words.keys())

    try:
        # ── UN SEUL appel batch (était N appels individuels) ──────────────────
        embeddings = model.encode(
            word_list,
            convert_to_numpy     = True,
            normalize_embeddings = True,
            batch_size           = 64,      # augmenté de 32 → 64
            show_progress_bar    = False,
        )

        word_emb_map = {
            word: emb.astype("float32")
            for word, emb in zip(word_list, embeddings)
        }
        _vocab_cache[concession_id] = word_emb_map

        # ── Pré-assembler la matrice (shape: n_words × dim) ──────────────────
        # Permet une recherche O(1) numpy au lieu d'une boucle O(n)
        matrix = np.stack(list(word_emb_map.values()), axis=0)  # (n, 384)
        _vocab_matrix_cache[concession_id] = (matrix, word_list)

        _log.info(
            f"Vocabulaire pré-calculé : {len(word_list)} mots "
            f"(concession {concession_id})"
        )
    except Exception as e:
        _log.error(f"Erreur précalcul embeddings : {e}")


# ── Recherche de similarité vectorisée ───────────────────────────────────────

def find_semantic_similarity(
    word:        str,
    vocab_cache: Dict[str, np.ndarray],
    threshold:   float = SYNONYM_THRESHOLD,
    concession_id: int = -1,
) -> List[tuple]:
    """
    Trouve les mots sémantiquement similaires dans le vocabulaire.
    OPTIMISÉ : produit matriciel vectorisé (matrice_vocab @ word_emb)
    au lieu d'une boucle np.dot() mot par mot.

    Args:
        word:          Mot cible (doit être dans vocab_cache)
        vocab_cache:   {mot: embedding}
        threshold:     Seuil cosinus minimum
        concession_id: Si fourni, utilise la matrice pré-calculée

    Returns:
        Liste triée [(mot, score), …] par score décroissant
    """
    if not vocab_cache or word not in vocab_cache:
        return []

    word_emb = vocab_cache[word]  # shape (384,)

    # ── Chemin rapide : matrice pré-calculée disponible ──────────────────────
    if concession_id >= 0 and concession_id in _vocab_matrix_cache:
        matrix, words_list = _vocab_matrix_cache[concession_id]
        # Un seul produit matriciel → toutes les similarités en 1 opération
        sims = matrix @ word_emb                     # shape (n,)
        mask = sims >= threshold
        indices = np.where(mask)[0]
        result = [
            (words_list[i], float(sims[i]))
            for i in indices
            if words_list[i] != word
        ]
        result.sort(key=lambda x: -x[1])
        return result

    # ── Chemin lent (fallback si matrice non dispo) ───────────────────────────
    similarities = []
    for vocab_word, emb in vocab_cache.items():
        if vocab_word == word:
            continue
        sim = float(np.dot(word_emb, emb))
        if sim >= threshold:
            similarities.append((vocab_word, sim))
    similarities.sort(key=lambda x: -x[1])
    return similarities


# ── Expansion sémantique ──────────────────────────────────────────────────────

def expand_synonyms(
    text:          str,
    vocab_cache:   Optional[Dict[str, np.ndarray]] = None,
    max_variants:  int = 10,
    concession_id: int = -1,
) -> List[str]:
    """
    Retourne le texte original + toutes ses variantes synonymiques.
    Utilise UNIQUEMENT la similarité sémantique, pas de dictionnaire.
    """
    if not vocab_cache:
        return [text]

    text_norm = normalize_word(text)
    if not text_norm or len(text_norm) < 3:
        return [text]

    similar_words = find_semantic_similarity(
        text_norm, vocab_cache,
        threshold=SYNONYM_THRESHOLD,
        concession_id=concession_id,
    )

    if not similar_words:
        return [text]

    variants = {text}
    for similar_word, similarity in similar_words[:5]:
        if similarity > 0.75:
            variants.add(similar_word)

    if text_norm != text.lower():
        variants.add(text_norm)

    no_accent = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    if no_accent != text and no_accent != text_norm:
        variants.add(no_accent)

    result = list(variants)[:max_variants]

    if len(result) > 1:
        _log.debug(f"Expansion sémantique de '{text}': {result[:3]}…")

    return result


def clear_cache() -> None:
    """Vide les caches des embeddings et des matrices."""
    global _vocab_cache, _vocab_matrix_cache
    _vocab_cache.clear()
    _vocab_matrix_cache.clear()
    _log.info("Cache des embeddings vidé")