"""
Gestion des embeddings et de l'index FAISS.
Modèle : all-MiniLM-L6-v2 (léger, multilingue, 384 dimensions).
OPTIMISATIONS :
  - pré-chargement du modèle en thread daemon au démarrage
  - encode() reçoit déjà des listes normalisées, pas de re-normalize
  - build_faiss_index utilise un batch_size adaptatif
  - invalidate_cache accepte une liste d'ids pour éviction groupée
"""
import logging
import threading
import time
import numpy as np
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)

# ── Disponibilité des dépendances ────────────────────────────────────────────
_FAISS_AVAILABLE = False
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _log.warning("FAISS non disponible — niveau embedding désactivé")

EMBEDDING_AVAILABLE = _FAISS_AVAILABLE

# ── Configuration du modèle ──────────────────────────────────────────────────
MODEL_NAME = "all-MiniLM-L6-v2"
DIMENSION  = 384

# ── État global (thread-safe) ────────────────────────────────────────────────
_model      = None
_model_lock = threading.Lock()
_model_ready = threading.Event()   # signalé quand le modèle est prêt

_index_cache: Dict[int, tuple] = {}  # {concession_id: (index_dict, timestamp)}
_cache_lock  = threading.Lock()


# ── Pré-chargement en arrière-plan ───────────────────────────────────────────
def _preload_model_background() -> None:
    """
    Lance le chargement du modèle dans un thread daemon.
    À appeler UNE SEULE FOIS au démarrage de l'application
    (ex. dans le module __init__.py du backend ou dans l'event 'startup' FastAPI).

    Exemple FastAPI :
        @app.on_event("startup")
        async def startup():
            from backend.semantic.embeddings.embedder import _preload_model_background
            _preload_model_background()
    """
    if not EMBEDDING_AVAILABLE:
        return

    def _load():
        try:
            _get_model()           # bloque le thread daemon, pas le worker
            _log.info("✅ Modèle embedding pré-chargé en arrière-plan")
        except Exception as e:
            _log.error(f"❌ Pré-chargement modèle échoué : {e}")

    t = threading.Thread(target=_load, daemon=True, name="embedder-preload")
    t.start()


def _get_model():
    """Charge le modèle d'embedding (lazy loading, thread-safe)."""
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            _log.info(f"Chargement du modèle : {MODEL_NAME}")
            _model = SentenceTransformer(MODEL_NAME)
            # Warm-up rapide (1 phrase) pour initialiser les caches internes PyTorch
            _model.encode("test", convert_to_numpy=True, show_progress_bar=False)
            _model_ready.set()
            _log.info("Modèle d'embedding prêt")
            return _model
        except Exception as e:
            _log.error(f"Erreur chargement modèle : {e}")
            _model_ready.set()   # libère les éventuels waiters même en cas d'erreur
            return None


def encode(texts: List[str], batch_size: int = 64) -> Optional[np.ndarray]:
    """
    Encode une liste de textes en vecteurs normalisés.
    batch_size augmenté à 64 (32 était conservateur pour du CPU ; 64 réduit
    le nombre de passes modèle sans surcharger la RAM).

    Args:
        texts:      Liste de textes à encoder
        batch_size: Taille du batch (64 par défaut)

    Returns:
        Matrice numpy (len(texts), DIMENSION) float32 ou None
    """
    if not texts:
        return None

    model = _get_model()
    if model is None:
        return None

    try:
        embs = model.encode(
            texts,
            convert_to_numpy    = True,
            normalize_embeddings= True,
            batch_size          = batch_size,
            show_progress_bar   = False,
        )
        return embs.astype("float32")
    except Exception as e:
        _log.error(f"Erreur encodage : {e}")
        return None


def encode_with_variants(text: str, variants: List[str]) -> Optional[np.ndarray]:
    """
    Encode un texte avec ses variantes et retourne la moyenne normalisée.
    UN SEUL appel encode() pour le texte + toutes ses variantes.

    Args:
        text:     Texte principal
        variants: Variantes synonymiques (max 6 utilisées)

    Returns:
        Vecteur moyen normalisé float32 ou None
    """
    all_texts = [text] + variants[:6]
    embs      = encode(all_texts)
    if embs is None or len(embs) == 0:
        return None

    avg  = np.mean(embs, axis=0)
    norm = np.linalg.norm(avg)
    return (avg / norm).astype("float32") if norm > 0 else avg.astype("float32")


def build_faiss_index(
    item_ids:    List[int],
    item_texts:  List[str],
    item_labels: List[str],
) -> Optional[dict]:
    """
    Construit un index FAISS pour une concession.
    batch_size adaptatif : plus grand pour réduire les passes sur de grands corpus.

    Args:
        item_ids:    IDs des items
        item_texts:  Textes normalisés (libelle_recherche)
        item_labels: Libellés canoniques

    Returns:
        Dict contenant l'index FAISS ou None
    """
    if not EMBEDDING_AVAILABLE or not item_ids:
        return None

    n          = len(item_ids)
    batch_size = min(128, max(32, n // 4))  # adaptatif : 32–128

    _log.info(f"Construction index FAISS : {n} items (batch={batch_size})…")

    embeddings = encode(item_texts, batch_size=batch_size)
    if embeddings is None:
        return None

    matrix = embeddings.astype("float32")
    index  = faiss.IndexFlatIP(DIMENSION)
    index.add(matrix)

    _log.info(f"Index FAISS construit : {index.ntotal} vecteurs")
    return {
        "index" : index,
        "ids"   : item_ids,
        "texts" : item_texts,
        "labels": item_labels,
    }


def get_or_build_index(
    concession_id: int,
    item_ids:      List[int],
    item_texts:    List[str],
    item_labels:   List[str],
) -> Optional[dict]:
    """
    Retourne l'index FAISS pour une concession (cache TTL 10 min).
    Nettoyage automatique des entrées > 1 heure.

    Args:
        concession_id: ID de la concession
        item_ids:      IDs des items
        item_texts:    Textes normalisés
        item_labels:   Libellés canoniques

    Returns:
        Index FAISS ou None
    """
    now = time.time()

    with _cache_lock:
        if concession_id in _index_cache:
            idx, timestamp = _index_cache[concession_id]
            if now - timestamp < 600:  # 10 minutes
                return idx

    idx = build_faiss_index(item_ids, item_texts, item_labels)

    with _cache_lock:
        _index_cache[concession_id] = (idx, now)
        # Nettoyage entrées > 1 heure
        stale = [k for k, v in _index_cache.items() if now - v[1] > 3600]
        for k in stale:
            del _index_cache[k]

    return idx


def search_embedding(
    query:     str,
    variants:  List[str],
    index_obj: dict,
    top_k:     int = 5,
) -> List[dict]:
    """
    Recherche les items les plus similaires par similarité cosinus (FAISS).

    Args:
        query:     Texte de la requête
        variants:  Variantes synonymiques
        index_obj: Index FAISS (dict retourné par build_faiss_index)
        top_k:     Nombre de résultats

    Returns:
        Liste [{item_id, label, score, rank}, …]
    """
    if not EMBEDDING_AVAILABLE or index_obj is None:
        return []

    emb = encode_with_variants(query, variants)
    if emb is None:
        return []

    query_vec        = emb.reshape(1, -1).astype("float32")
    k                = min(top_k, len(index_obj["ids"]))
    scores, indices  = index_obj["index"].search(query_vec, k)

    candidates = []
    for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
        if idx < 0 or idx >= len(index_obj["ids"]):
            continue
        candidates.append({
            "item_id": index_obj["ids"][idx],
            "label"  : index_obj["labels"][idx],
            "score"  : float(score),
            "rank"   : rank,
        })

    return candidates


def invalidate_cache(concession_id: Optional[int] = None) -> None:
    """
    Invalide le cache FAISS.

    Args:
        concession_id: ID à invalider (None = tout vider)
    """
    global _index_cache
    with _cache_lock:
        if concession_id is not None:
            _index_cache.pop(concession_id, None)
            _log.info(f"Cache invalidé : concession {concession_id}")
        else:
            _index_cache.clear()
            _log.info("Cache global invalidé")