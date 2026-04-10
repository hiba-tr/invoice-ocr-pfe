"""
Traitement sémantique hybride – Version avec détection de synonymes.
Stratégie : exact → synonymes → fuzzy+synonymes → embedding+synonymes
"""
import re
import threading
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple, Set

from rapidfuzz import fuzz as rfuzz
from api import models_sql

# ─────────────────────────────────────────────────────────────────────────────
# Modèle & cache FAISS
# ─────────────────────────────────────────────────────────────────────────────

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: Optional[SentenceTransformer] = None
_model_lock = threading.Lock()
DIMENSION = 384

_cache_lock = threading.Lock()
_faiss_index: Optional[faiss.IndexFlatIP] = None
_item_ids: List[int] = []
_item_texts: List[str] = []
_cache_valid: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Dictionnaire de synonymes métier (FR/EN/abréviations)
# Chaque groupe = termes qui désignent la même réalité
# ─────────────────────────────────────────────────────────────────────────────

SYNONYM_GROUPS: List[Set[str]] = [
    # Documents / Facturation
    {"facture", "invoice", "bill", "fac", "fact"},
    {"devis", "quotation", "quote", "offre", "estimation", "proforma"},
    {"bon de commande", "purchase order", "po", "commande", "order"},
    {"avoir", "credit note", "note de credit", "remboursement"},
    {"recu", "receipt", "quittance"},

    # Articles / Produits
    {"article", "item", "produit", "product", "bien"},
    {"service", "prestation", "mission", "intervention"},
    {"fourniture", "supply", "materiel", "matiere", "material"},
    {"piece", "composant", "component", "part"},
    {"equipement", "equipment", "appareil", "device", "machine"},

    # Quantités / Unités
    {"quantite", "quantity", "qte", "qty", "nombre", "nb"},
    {"unite", "unit", "u", "pcs", "ea"},
    {"heure", "hour", "h", "hr", "hrs"},
    {"jour", "day", "j", "days"},
    {"mois", "month", "mo"},
    {"forfait", "flat rate", "lump sum", "global"},
    {"litre", "liter", "l", "lt"},
    {"kilogramme", "kg", "kilo", "kilogram"},
    {"metre", "meter", "m"},

    # Prix / Montants
    {"prix unitaire", "unit price", "pu", "pu ht", "tarif", "rate", "cout unitaire"},
    {"montant", "amount", "valeur", "value", "somme"},
    {"total ht", "sous total", "subtotal", "montant ht", "ht"},
    {"total ttc", "ttc", "montant ttc", "net a payer", "grand total"},
    {"tva", "vat", "taxe", "tax", "impot", "montant tva"},
    {"remise", "discount", "reduction", "rabais"},
    {"acompte", "avance", "deposit", "advance"},

    # Travaux généraux
    {"installation", "install", "mise en place", "setup", "montage"},
    {"maintenance", "entretien", "maint", "revision"},
    {"reparation", "repair", "fix", "depannage"},
    {"inspection", "controle", "control", "check", "verification"},
    {"nettoyage", "cleaning", "clean", "lavage"},
    {"remplacement", "replacement", "replace", "changement"},
    {"transport", "livraison", "delivery", "shipping", "fret", "freight"},
    {"location", "rental", "rent", "loyer"},
    {"main oeuvre", "labor", "labour", "mo", "manoeuvre", "workforce"},
    {"soudure", "welding", "soudage"},
    {"peinture", "painting", "paint", "coating"},

    # Personnel
    {"ingenieur", "engineer", "ing"},
    {"technicien", "technician", "tech"},
    {"operateur", "operator"},
    {"superviseur", "supervisor", "chef"},
    {"consultant", "conseil", "advisor"},
    {"salaire", "salary", "wage", "remuneration"},
    {"formation", "training"},

    # Pétrolier / Énergie (contexte WAHA/OMV)
    {"puits", "well", "wells"},
    {"forage", "drilling", "drill", "sondage"},
    {"stimulation", "acidification"},
    {"completion", "completion"},
    {"production", "prod"},
    {"pipeline", "conduite", "tuyauterie", "pipe"},
    {"valve", "vanne", "soupape"},
    {"compresseur", "compressor"},
    {"separateur", "separator"},
    {"reservoir", "tank", "cuve"},
    {"pompe", "pump"},
    {"generateur", "generator", "groupe electrogene"},
    {"electricite", "electricity", "electric", "elec"},
    {"rotation", "rotating", "rotatif"},
    {"overhaul", "revision generale", "grand entretien"},

    # Informatique
    {"logiciel", "software", "programme", "application", "app"},
    {"materiel informatique", "hardware", "ordinateur", "computer"},
    {"licence", "license", "abonnement", "subscription"},
    {"serveur", "server"},
    {"reseau", "network", "net"},
    {"sauvegarde", "backup"},

    # Bâtiment
    {"construction", "building", "batiment"},
    {"renovation", "rehabilitation"},
    {"beton", "concrete"},
    {"acier", "steel"},
]

# Index inversé : mot/phrase normalisé → ensemble de synonymes
_SYNONYM_INDEX: Dict[str, Set[str]] = {}
for _group in SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYM_INDEX[_word] = _group


def invalidate_cache() -> None:
    global _cache_valid
    with _cache_lock:
        _cache_valid = False


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    # Supprimer accents courants
    for src, dst in [("é","e"),("è","e"),("ê","e"),("ë","e"),("à","a"),("â","a"),
                     ("î","i"),("ï","i"),("ô","o"),("ù","u"),("û","u"),("ü","u"),
                     ("ç","c"),("œ","oe"),("æ","ae")]:
        text = text.replace(src, dst)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def expand_with_synonyms(text: str) -> List[str]:
    """
    Retourne le texte original + toutes les variantes via synonymes.
    Ex : "drilling cost" → ["drilling cost", "forage cost", "sondage cost", ...]
    """
    norm = normalize_text(text)
    tokens = norm.split()
    expansions: Set[str] = {norm}

    # Synonymes mot par mot
    for i, token in enumerate(tokens):
        if token in _SYNONYM_INDEX:
            for syn in _SYNONYM_INDEX[token]:
                new_tokens = tokens[:i] + [syn] + tokens[i+1:]
                expansions.add(" ".join(new_tokens))

    # Synonymes sur des bigrammes / trigrammes
    for n in (2, 3):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i+n])
            if phrase in _SYNONYM_INDEX:
                for syn in _SYNONYM_INDEX[phrase]:
                    new_tokens = tokens[:i] + [syn] + tokens[i+n:]
                    expansions.add(" ".join(new_tokens))

    return list(expansions)


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _get_embedding(text: str) -> np.ndarray:
    emb = _get_model().encode(text, convert_to_numpy=True).astype("float32")
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def _get_embedding_expanded(text: str) -> np.ndarray:
    """
    Embedding moyen du texte + ses variantes synonymiques.
    Rend le vecteur robuste aux différences de vocabulaire.
    """
    variants = expand_with_synonyms(text)
    embeddings = [_get_embedding(v) for v in variants[:8]]
    avg = np.mean(embeddings, axis=0).astype("float32")
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg


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
        emb = _get_embedding_expanded(item.nom_item)  # Index enrichi par synonymes
        vectors.append(emb)
        ids.append(item.id_item)
        texts.append(normalize_text(item.nom_item))

    matrix = np.array(vectors, dtype="float32")
    index = faiss.IndexFlatIP(DIMENSION)
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


def _fuzzy_with_synonyms(
    norm_desc: str,
    all_items,
    threshold: int,
) -> Optional[Tuple[int, float]]:
    """
    Fuzzy matching enrichi : compare toutes les variantes synonymiques
    de la description avec toutes les variantes synonymiques de chaque item.
    """
    desc_variants = expand_with_synonyms(norm_desc)
    best_id: Optional[int] = None
    best_score: int = 0

    for item in all_items:
        norm_item = normalize_text(item.nom_item)
        item_variants = expand_with_synonyms(norm_item)
        for cand_desc in desc_variants:
            for cand_item in item_variants:
                score = max(
                    rfuzz.token_sort_ratio(cand_desc, cand_item),
                    rfuzz.partial_ratio(cand_desc, cand_item),
                    rfuzz.token_set_ratio(cand_desc, cand_item),
                )
                if score > best_score:
                    best_score = score
                    best_id = item.id_item

    if best_id and best_score >= threshold:
        return (best_id, round(best_score / 100.0, 4))
    return None


def find_similar_item(
    db: Session,
    description: str,
    threshold_fuzzy: int = 72,
    threshold_embedding: float = 0.68,
) -> Optional[Tuple[int, float]]:
    if not description or not description.strip():
        return None

    norm_desc = normalize_text(description)
    all_items = db.query(models_sql.Item).all()
    if not all_items:
        return None

    # ── Niveau 1 : Correspondance exacte ─────────────────────────────────────
    for item in all_items:
        if normalize_text(item.nom_item) == norm_desc:
            return (item.id_item, 1.0)

    # ── Niveau 2 : Match exact via synonymes ──────────────────────────────────
    # Ex : "drilling" dans la description, "forage" dans la base → match
    desc_variants = set(expand_with_synonyms(norm_desc))
    for item in all_items:
        norm_item = normalize_text(item.nom_item)
        item_variants = set(expand_with_synonyms(norm_item))
        common = (desc_variants & item_variants) - {norm_desc, norm_item}
        if common:
            return (item.id_item, 0.95)

    # ── Niveau 3 : Fuzzy avec synonymes ──────────────────────────────────────
    match = _fuzzy_with_synonyms(norm_desc, all_items, threshold=threshold_fuzzy)
    if match:
        return match

    # ── Niveau 4 : Embedding étendu aux synonymes ─────────────────────────────
    _ensure_index(db)
    with _cache_lock:
        if _faiss_index is None or _faiss_index.ntotal == 0:
            return None

        emb = _get_embedding_expanded(description).reshape(1, -1)
        scores, indices = _faiss_index.search(emb, 3)
        best_score = float(scores[0][0])
        best_idx = int(indices[0][0])
        second_score = float(scores[0][1]) if len(scores[0]) > 1 else 0.0

        # Seuil assoupli car embeddings déjà enrichis
        if best_score >= threshold_embedding and (best_score - second_score) > 0.10:
            if best_idx < len(_item_ids):
                return (_item_ids[best_idx], round(best_score, 4))

    return None


def suggest_items_batch(
    db: Session,
    descriptions: List[str],
) -> List[Dict[str, Any]]:
    _ensure_index(db)
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