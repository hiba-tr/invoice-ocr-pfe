"""
Dictionnaire de synonymes intelligent - basé sur la similarité sémantique.
AUCUN dictionnaire statique - tout est calculé dynamiquement.
"""
import logging
import re
import unicodedata
from typing import Dict, List, Optional
import numpy as np

from ..embeddings.embedder import _get_model

_log = logging.getLogger(__name__)

# Cache pour les embeddings pré-calculés
_vocab_cache: Dict[int, Dict[str, np.ndarray]] = {}
SYNONYM_THRESHOLD = 0.70  # Seuil de similarité cosinus


def normalize_word(word: str) -> str:
    """Normalise un mot : sans accents, sans ponctuation, en minuscule."""
    word = word.lower().strip()
    # Supprimer les accents
    word = unicodedata.normalize('NFKD', word).encode('ASCII', 'ignore').decode('utf-8')
    # Supprimer la ponctuation
    word = re.sub(r'[^\w\s]', '', word)
    # Supprimer les chiffres en fin de mot (ex: "etap50" -> "etap")
    word = re.sub(r'\d+$', '', word)
    return word.strip()


def get_word_embedding(word: str, model) -> Optional[np.ndarray]:
    """Calcule l'embedding d'un mot individuel."""
    if not word or len(word) < 2:
        return None
    try:
        emb = model.encode([word], convert_to_numpy=True, normalize_embeddings=True)
        return emb[0].astype("float32")
    except Exception:
        return None


def precompute_vocab_embeddings(concession_id: int, words: List[str]) -> None:
    """
    Pré-calcule les embeddings du vocabulaire d'une concession.
    Ces embeddings servent de base pour la similarité sémantique.
    """
    if not words:
        return

    model = _get_model()
    if model is None:
        return

    # Normaliser et dédupliquer
    unique_words = {}
    for w in words:
        norm = normalize_word(w)
        if norm and norm not in unique_words:
            unique_words[norm] = w
    
    if not unique_words:
        return
    
    # Calculer les embeddings
    word_list = list(unique_words.keys())
    try:
        embeddings = model.encode(
            word_list,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
        )
        _vocab_cache[concession_id] = {
            word: emb.astype("float32") 
            for word, emb in zip(word_list, embeddings)
        }
        _log.info(f"Vocabulaire pré-calculé : {len(word_list)} mots (concession {concession_id})")
    except Exception as e:
        _log.error(f"Erreur précalcul embeddings : {e}")


def find_semantic_similarity(
    word: str, 
    vocab_cache: Dict[str, np.ndarray], 
    threshold: float = SYNONYM_THRESHOLD
) -> List[tuple]:
    """
    Trouve les mots sémantiquement similaires dans le vocabulaire.
    Utilise la similarité cosinus des embeddings.
    """
    if not vocab_cache or word not in vocab_cache:
        return []
    
    word_emb = vocab_cache[word]
    similarities = []
    
    for vocab_word, emb in vocab_cache.items():
        if vocab_word == word:
            continue
        
        # Calcul de la similarité cosinus
        sim = float(np.dot(word_emb, emb))
        if sim >= threshold:
            similarities.append((vocab_word, sim))
    
    # Trier par similarité décroissante
    similarities.sort(key=lambda x: -x[1])
    return similarities


def expand_synonyms(
    text: str,
    vocab_cache: Optional[Dict[str, np.ndarray]] = None,
    max_variants: int = 10,
) -> List[str]:
    """
    Retourne le texte original + toutes ses variantes synonymiques.
    Utilise UNIQUEMENT la similarité sémantique, pas de dictionnaire.
    """
    if not vocab_cache:
        return [text]
    
    # Normaliser le texte
    text_norm = normalize_word(text)
    if not text_norm or len(text_norm) < 3:
        return [text]
    
    # Chercher des mots similaires sémantiquement
    similar_words = find_semantic_similarity(text_norm, vocab_cache, threshold=SYNONYM_THRESHOLD)
    
    if not similar_words:
        return [text]
    
    # Générer les variantes
    variants = {text}
    
    # Ajouter les 5 meilleures similarités
    for similar_word, similarity in similar_words[:5]:
        if similarity > 0.85:  # Très similaire
            variants.add(similar_word)
        elif similarity > 0.75:  # Modérément similaire
            variants.add(similar_word)
    
    # Ajouter la forme normalisée si différente
    if text_norm != text.lower():
        variants.add(text_norm)
    
    # Ajouter la forme sans accents
    no_accent = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    if no_accent != text and no_accent != text_norm:
        variants.add(no_accent)
    
    # Limiter le nombre de variantes
    result = list(variants)[:max_variants]
    
    if len(result) > 1:
        _log.debug(f"Expansion sémantique de '{text}': {result[:3]}...")
    
    return result


def clear_cache() -> None:
    """Vide le cache des embeddings."""
    global _vocab_cache
    _vocab_cache.clear()
    _log.info("Cache des embeddings vidé")