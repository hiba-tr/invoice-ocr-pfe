"""
Gestion de l'index FAISS pour la recherche par similarité cosinus.

Responsabilités :
- Construire un index FAISS par concession
- Mettre en cache les index avec TTL (10 minutes)
- Rechercher les k plus proches voisins
- Invalider le cache

Dépendances :
- embeddings.embedder : pour encode(), encode_with_variants(), build_faiss_index()
"""
import logging
import time
from typing import Dict, List, Optional

from .embedder import (
    encode_with_variants,
    build_faiss_index,
    EMBEDDING_AVAILABLE,
)

_log = logging.getLogger(__name__)

# ── Cache des index FAISS par concession ─────────────────────────────────────
# Structure : {concession_id: (index_dict, timestamp)}
_index_cache: Dict[int, tuple] = {}
_cache_lock = None  # Sera initialisé dans _get_cache_lock()


def _get_cache_lock():
    """Retourne un lock thread-safe pour le cache (lazy init)."""
    global _cache_lock
    if _cache_lock is None:
        import threading
        _cache_lock = threading.Lock()
    return _cache_lock


# ═══════════════════════════════════════════════════════════════
# API PUBLIQUE
# ═══════════════════════════════════════════════════════════════

def get_or_build_index(
    concession_id: int,
    item_ids: List[int],
    item_texts: List[str],
    item_labels: List[str],
) -> Optional[dict]:
    """
    Retourne l'index FAISS pour une concession (avec cache TTL).

    - Si l'index existe dans le cache et a moins de 10 minutes → retour immédiat
    - Sinon → construction de l'index, stockage en cache, retour
    - Nettoie automatiquement les entrées de plus d'1 heure

    Args:
        concession_id : ID de la concession
        item_ids      : Liste des IDs des items
        item_texts    : Liste des libellés normalisés (libelle_recherche)
        item_labels   : Liste des libellés canoniques

    Returns:
        Dictionnaire contenant l'index FAISS, ou None si embedding indisponible

    Example:
        >>> idx = get_or_build_index(1, [1,2], ["bonjour","salut"], ["Bonjour","Salut"])
        >>> idx["ids"]
        [1, 2]
    """
    if not EMBEDDING_AVAILABLE:
        _log.warning("Embedding non disponible — index FAISS non construit")
        return None

    lock = _get_cache_lock()
    now = time.time()

    # Vérifier le cache
    with lock:
        if concession_id in _index_cache:
            idx, timestamp = _index_cache[concession_id]
            if now - timestamp < 600:  # 10 minutes
                _log.debug(f"Cache hit : concession {concession_id}")
                return idx

    # Construire l'index
    _log.info(f"Construction index FAISS pour concession {concession_id}...")
    idx = build_faiss_index(item_ids, item_texts, item_labels)

    # Stocker dans le cache
    with lock:
        _index_cache[concession_id] = (idx, now)

        # Nettoyer les entrées de plus d'1 heure
        old_keys = [k for k, v in _index_cache.items() if now - v[1] > 3600]
        for k in old_keys:
            del _index_cache[k]
            _log.debug(f"Cache nettoyé : concession {k}")

    return idx


def search_embedding(
    query: str,
    variants: List[str],
    index_obj: dict,
    top_k: int = 5,
) -> List[dict]:
    """
    Recherche les k items les plus similaires par similarité cosinus.

    Args:
        query     : Texte de la requête (normalisé)
        variants  : Variantes synonymiques du texte
        index_obj : Index FAISS (obtenu via get_or_build_index)
        top_k     : Nombre de résultats à retourner

    Returns:
        Liste de dictionnaires triés par score décroissant :
        [{"item_id": int, "label": str, "score": float, "rank": int}, ...]

    Example:
        >>> idx = get_or_build_index(...)
        >>> results = search_embedding("bonjour", [], idx, top_k=3)
        >>> results[0]["label"]
        "Bonjour"
        >>> results[0]["score"]
        0.95
    """
    if not EMBEDDING_AVAILABLE or index_obj is None:
        return []

    # Encoder la requête avec ses variantes
    emb = encode_with_variants(query, variants)
    if emb is None:
        _log.warning("Encodage échoué pour la recherche embedding")
        return []

    # Rechercher les k plus proches voisins
    query_vec = emb.reshape(1, -1).astype("float32")
    k = min(top_k, len(index_obj["ids"]))
    scores, indices = index_obj["index"].search(query_vec, k)

    # Formater les résultats
    candidates = []
    for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
        if idx < 0 or idx >= len(index_obj["ids"]):
            continue
        candidates.append({
            "item_id": index_obj["ids"][idx],
            "label": index_obj["labels"][idx],
            "score": float(score),
            "rank": rank,
        })

    return candidates


def invalidate_cache(concession_id: Optional[int] = None) -> None:
    """
    Invalide le cache FAISS.

    Args:
        concession_id : ID de la concession à invalider.
                       Si None → vide tout le cache.

    Example:
        >>> invalidate_cache(1)    # Invalide seulement la concession 1
        >>> invalidate_cache()     # Invalide tout le cache
    """
    global _index_cache
    lock = _get_cache_lock()

    with lock:
        if concession_id is not None:
            removed = _index_cache.pop(concession_id, None)
            if removed:
                _log.info(f"Cache invalidé : concession {concession_id}")
        else:
            count = len(_index_cache)
            _index_cache.clear()
            _log.info(f"Cache global invalidé ({count} entrées supprimées)")


def get_cache_stats() -> Dict[str, int]:
    """
    Retourne les statistiques du cache.

    Returns:
        {"1": 150, "2": 89}  → concession 1 : 150 items, concession 2 : 89 items

    Example:
        >>> get_cache_stats()
        {"1": 150}
    """
    lock = _get_cache_lock()
    with lock:
        return {
            str(cid): len(idx["ids"]) if idx else 0
            for cid, (idx, _) in _index_cache.items()
        }