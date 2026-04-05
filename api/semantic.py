"""
Traitement sémantique hybride pour la correspondance d'items de facture.

Stratégie en 3 niveaux (du plus rapide au plus précis) :
  1. Correspondance exacte normalisée  → confiance 1.0
  2. Fuzzy matching (rapidfuzz)        → confiance proportionnelle au score
  3. Embedding dense + FAISS           → confiance = cosine similarity

Le cache FAISS est reconstruit à la demande et invalidé explicitement
après tout ajout/suppression d'items en base.
"""

import re
import threading
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple

# rapidfuzz remplace fuzzywuzzy (plus rapide, même API, pas de dépendance Levenshtein C)
from rapidfuzz import fuzz as rfuzz

from api import models_sql

# ── Modèle d'embedding ────────────────────────────────────────────────────────
# all-MiniLM-L6-v2 : bon compromis vitesse/qualité pour textes courts
_MODEL_NAME = "all-MiniLM-L6-v2"
_model: Optional[SentenceTransformer] = None
_model_lock = threading.Lock()
DIMENSION = 384


def _get_model() -> SentenceTransformer:
    """Chargement paresseux et thread-safe du modèle."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer(_MODEL_NAME)
    return _model


# ── Cache FAISS (état global protégé par un verrou) ───────────────────────────
_cache_lock = threading.Lock()
_faiss_index: Optional[faiss.IndexFlatIP] = None
_item_ids: List[int] = []
_item_texts: List[str] = []
_cache_valid: bool = False


def invalidate_cache() -> None:
    """Appeler après tout ajout ou suppression d'items en base."""
    global _cache_valid
    with _cache_lock:
        _cache_valid = False


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── Embedding ─────────────────────────────────────────────────────────────────

def _get_embedding(text: str) -> np.ndarray:
    """Retourne un vecteur L2-normalisé (float32)."""
    emb = _get_model().encode(text, convert_to_numpy=True).astype('float32')
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


# ── Construction de l'index FAISS ─────────────────────────────────────────────

def _rebuild_index(db: Session) -> None:
    global _faiss_index, _item_ids, _item_texts, _cache_valid
    items = db.query(models_sql.Item).all()
    if not items:
        _faiss_index = None
        _item_ids = []
        _item_texts = []
        _cache_valid = True
        return

    vectors, ids, texts = [], [], []
    for item in items:
        emb = _get_embedding(item.nom_item)
        vectors.append(emb)
        ids.append(item.id_item)
        texts.append(normalize_text(item.nom_item))

    matrix = np.array(vectors, dtype='float32')
    index = faiss.IndexFlatIP(DIMENSION)  # produit scalaire = cosine car vecteurs normalisés
    index.add(matrix)

    _faiss_index = index
    _item_ids = ids
    _item_texts = texts
    _cache_valid = True


def _ensure_index(db: Session) -> None:
    global _cache_valid
    with _cache_lock:
        if not _cache_valid:
            _rebuild_index(db)


# ── Recherche principale ──────────────────────────────────────────────────────

def find_similar_item(
    db: Session,
    description: str,
    threshold_exact: float = 1.0,
    threshold_fuzzy: int = 82,
    threshold_embedding: float = 0.72,
) -> Optional[Tuple[int, float]]:
    """
    Retourne (id_item, confiance) du meilleur match, ou None.

    Niveaux :
      1. Exact normalisé  (confiance = 1.0)
      2. Fuzzy rapidfuzz  (confiance = score/100, seuil 82)
      3. Embedding FAISS  (confiance = cosine similarity, seuil 0.72)
    """
    if not description or not description.strip():
        return None

    norm_desc = normalize_text(description)
    all_items = db.query(models_sql.Item).all()

    # ── Niveau 1 : correspondance exacte après normalisation ──────────────────
    for item in all_items:
        if normalize_text(item.nom_item) == norm_desc:
            return (item.id_item, 1.0)

    # ── Niveau 2 : fuzzy matching ──────────────────────────────────────────────
    best_fuzzy_id: Optional[int] = None
    best_fuzzy_score: int = 0

    for item in all_items:
        norm_item = normalize_text(item.nom_item)
        # token_sort_ratio gère les mots dans un ordre différent
        score = rfuzz.token_sort_ratio(norm_desc, norm_item)
        if score > best_fuzzy_score:
            best_fuzzy_score = score
            best_fuzzy_id = item.id_item

    if best_fuzzy_id and best_fuzzy_score >= threshold_fuzzy:
        confidence = round(best_fuzzy_score / 100.0, 4)
        return (best_fuzzy_id, confidence)

    # ── Niveau 3 : embedding dense ────────────────────────────────────────────
    _ensure_index(db)

    with _cache_lock:
        if _faiss_index is None or _faiss_index.ntotal == 0:
            return None

        emb = _get_embedding(description).reshape(1, -1)
        scores, indices = _faiss_index.search(emb, 1)
        best_score = float(scores[0][0])
        best_idx = int(indices[0][0])

    if best_score >= threshold_embedding and best_idx < len(_item_ids):
        return (_item_ids[best_idx], round(best_score, 4))

    return None


# ── Traitement en lot ─────────────────────────────────────────────────────────

def suggest_items_batch(
    db: Session,
    descriptions: List[str],
) -> List[Dict[str, Any]]:
    """
    Pour chaque description, retourne la meilleure suggestion avec son score réel.
    """
    _ensure_index(db)  # un seul rebuild pour tout le batch
    results = []

    for desc in descriptions:
        match = find_similar_item(db, desc)
        if match:
            item_id, confidence = match
            item = db.query(models_sql.Item).filter(models_sql.Item.id_item == item_id).first()
            results.append({
                "nouvelle_description": desc,
                "item_existant_id": item_id,
                "nom_item_existant": item.nom_item if item else None,
                "confiance": confidence,
            })
        else:
            results.append({
                "nouvelle_description": desc,
                "item_existant_id": None,
                "nom_item_existant": None,
                "confiance": None,
            })

    return results