"""Gestion des embeddings - Modele BGE-M3 avec fallback robuste"""
import logging
import threading
import numpy as np
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)

_FAISS_AVAILABLE = False
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _log.warning("FAISS non disponible")

EMBEDDING_AVAILABLE = _FAISS_AVAILABLE

MODEL_NAME = "BAAI/bge-m3"
DIMENSION = 1024
# Alternatives légères si trop lent :
# MODEL_NAME = "intfloat/multilingual-e5-small"
# MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None
_model_lock = threading.Lock()
_reranker = None
_reranker_lock = threading.Lock()
_index_cache: Dict[int, dict] = {}
_cache_lock = threading.Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model
    
    with _model_lock:
        if _model is not None:
            return _model
        
        # Tentative 1: OpenVINO (Intel)
        try:
            from optimum.intel import OVSentenceTransformer
            _log.info(f"Chargement OpenVINO: {MODEL_NAME}")
            _model = OVSentenceTransformer(MODEL_NAME, device="AUTO", compile=True)
            _log.info("Modele OpenVINO pret")
            return _model
        except Exception as e:
            _log.info(f"OpenVINO non disponible: {e}")
        c
        # Tentative 2: ONNX Runtime
        try:
            from optimum.onnxruntime import ORTSentenceTransformer
            _log.info(f"Chargement ONNX: {MODEL_NAME}")
            _model = ORTSentenceTransformer(MODEL_NAME)
            _log.info("Modele ONNX pret")
            return _model
        except Exception as e:
            _log.info(f"ONNX non disponible: {e}")
        
        # Tentative 3: SentenceTransformer standard
        try:
            from sentence_transformers import SentenceTransformer
            _log.info(f"Chargement standard: {MODEL_NAME}")
            _model = SentenceTransformer(MODEL_NAME)
            _log.info("Modele standard pret")
            return _model
        except Exception as e:
            _log.error(f"Aucun moteur disponible: {e}")
            _model = None
            return None


def _get_reranker():
    """Re-rank avec CrossEncoder (chargé une seule fois)."""
    global _reranker
    if _reranker is not None:
        return _reranker
    
    with _reranker_lock:
        if _reranker is not None:
            return _reranker
        try:
            from sentence_transformers import CrossEncoder
            _log.info("Chargement CrossEncoder re-ranker...")
            _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            _log.info("Re-ranker pret")
            return _reranker
        except Exception as e:
            _log.warning(f"Re-ranker non disponible: {e}")
            _reranker = False
            return None


def encode(texts: List[str]) -> Optional[np.ndarray]:
    model = _get_model()
    if model is None:
        return None
    try:
        embs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embs.astype("float32")
    except Exception as e:
        _log.error(f"Erreur encodage: {e}")
        return None


def encode_with_variants(text: str, variants: List[str]) -> Optional[np.ndarray]:
    all_texts = [text] + variants[:6]
    embs = encode(all_texts)
    if embs is None or len(embs) == 0:
        return None
    avg = np.mean(embs, axis=0)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg.astype("float32")


def build_faiss_index(item_ids: List[int], item_texts: List[str], item_labels: List[str]) -> Optional[dict]:
    if not EMBEDDING_AVAILABLE or not item_ids:
        return None
    
    _log.info(f"Construction index FAISS: {len(item_ids)} items...")
    vectors = []
    for text in item_texts:
        emb = encode([text])
        if emb is not None and len(emb) > 0:
            vectors.append(emb[0])
        else:
            vectors.append(np.zeros(DIMENSION, dtype="float32"))
    
    matrix = np.array(vectors, dtype="float32")
    index = faiss.IndexFlatIP(DIMENSION)
    index.add(matrix)
    _log.info(f"Index FAISS construit: {index.ntotal} vecteurs")
    
    return {"index": index, "ids": item_ids, "texts": item_texts, "labels": item_labels}


def get_or_build_index(concession_id: int, item_ids: List[int], item_texts: List[str], item_labels: List[str]) -> Optional[dict]:
    with _cache_lock:
        if concession_id in _index_cache:
            return _index_cache[concession_id]
    
    idx = build_faiss_index(item_ids, item_texts, item_labels)
    with _cache_lock:
        _index_cache[concession_id] = idx
    return idx


def search_embedding(query: str, variants: List[str], index_obj: dict, top_k: int = 5) -> List[dict]:
    if not EMBEDDING_AVAILABLE or index_obj is None:
        return []
    
    emb = encode_with_variants(query, variants)
    if emb is None:
        return []
    
    query_vec = emb.reshape(1, -1).astype("float32")
    k = min(top_k, len(index_obj["ids"]))
    scores, indices = index_obj["index"].search(query_vec, k)
    
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
    
    # Re-ranking avec CrossEncoder (chargé une fois)
    if candidates:
        reranker = _get_reranker()
        if reranker:
            try:
                pairs = [[query, c["label"]] for c in candidates]
                rerank_scores = reranker.predict(pairs, show_progress_bar=False)
                for i, sc in enumerate(rerank_scores):
                    candidates[i]["rerank_score"] = float(sc)
                candidates.sort(key=lambda x: x.get("rerank_score", x["score"]), reverse=True)
            except Exception:
                pass
    
    return candidates


def invalidate_cache(concession_id: int = None):
    global _index_cache
    with _cache_lock:
        if concession_id:
            _index_cache.pop(concession_id, None)
            _log.info(f"Cache invalide pour concession {concession_id}")
        else:
            _index_cache.clear()
            _log.info("Cache global invalide")