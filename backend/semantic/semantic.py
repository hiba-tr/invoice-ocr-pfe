"""
Traitement sémantique hybride – Version adaptée à la nouvelle base (concession, libelle_recherche).
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
from backend.api import models_sql
# ─────────────────────────────────────────────────────────────────────────────
# Modèle & cache FAISS (par concession)
# ─────────────────────────────────────────────────────────────────────────────

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: Optional[SentenceTransformer] = None
_model_lock = threading.Lock()
DIMENSION = 384

# Cache par concession : dict[id_concession] -> (faiss_index, item_ids, item_texts)
_cache_by_concession: Dict[int, Tuple[faiss.IndexFlatIP, List[int], List[str]]] = {}
_cache_lock = threading.Lock()

# Synonymes (inchangé, votre dictionnaire reste valide)
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


_SYNONYM_INDEX: Dict[str, Set[str]] = {}
for _group in SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYM_INDEX[_word] = _group


def invalidate_cache(concession_id: Optional[int] = None) -> None:
    """Invalide le cache d'une concession ou de toutes."""
    global _cache_by_concession
    with _cache_lock:
        if concession_id is not None:
            _cache_by_concession.pop(concession_id, None)
        else:
            _cache_by_concession.clear()


def normalize_text(text: str) -> str:
    """Normalise un texte pour la recherche (minuscule, sans accent, sans ponctuation)."""
    if not text:
        return ""
    text = text.lower().strip()
    for src, dst in [("é","e"),("è","e"),("ê","e"),("ë","e"),("à","a"),("â","a"),
                     ("î","i"),("ï","i"),("ô","o"),("ù","u"),("û","u"),("ü","u"),
                     ("ç","c"),("œ","oe"),("æ","ae")]:
        text = text.replace(src, dst)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def expand_with_synonyms(text: str) -> List[str]:
    """Retourne le texte original + toutes les variantes via synonymes."""
    norm = normalize_text(text)
    tokens = norm.split()
    expansions: Set[str] = {norm}

    for i, token in enumerate(tokens):
        if token in _SYNONYM_INDEX:
            for syn in _SYNONYM_INDEX[token]:
                new_tokens = tokens[:i] + [syn] + tokens[i+1:]
                expansions.add(" ".join(new_tokens))

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
    variants = expand_with_synonyms(text)
    embeddings = [_get_embedding(v) for v in variants[:8]]
    avg = np.mean(embeddings, axis=0).astype("float32")
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm
    return avg


def _build_index_for_concession(db: Session, id_concession: int) -> Tuple[faiss.IndexFlatIP, List[int], List[str]]:
    """Construit l'index FAISS pour une concession donnée."""
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession
    ).all()
    if not items:
        return None, [], []

    vectors, ids, texts = [], [], []
    for item in items:
        # Utiliser libelle_recherche (déjà normalisé) pour l'indexation
        emb = _get_embedding_expanded(item.libelle_recherche)
        vectors.append(emb)
        ids.append(item.id_item)
        texts.append(item.libelle_recherche)

    matrix = np.array(vectors, dtype="float32")
    index = faiss.IndexFlatIP(DIMENSION)
    index.add(matrix)
    return index, ids, texts


def _ensure_index(db: Session, id_concession: int) -> Tuple[faiss.IndexFlatIP, List[int], List[str]]:
    """Retourne l'index FAISS pour la concession, le reconstruit si nécessaire."""
    with _cache_lock:
        if id_concession not in _cache_by_concession:
            index, ids, texts = _build_index_for_concession(db, id_concession)
            _cache_by_concession[id_concession] = (index, ids, texts)
        return _cache_by_concession[id_concession]


def _fuzzy_with_synonyms(
    norm_desc: str,
    items: List[models_sql.Item],
    threshold: int,
) -> Optional[Tuple[int, float]]:
    """Fuzzy matching enrichi par synonymes sur une liste d'items."""
    desc_variants = expand_with_synonyms(norm_desc)
    best_id: Optional[int] = None
    best_score: int = 0

    for item in items:
        norm_item = item.libelle_recherche  # déjà normalisé
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
    id_concession: int,
    threshold_fuzzy: int = 72,
    threshold_embedding: float = 0.68,
) -> Optional[Tuple[int, float]]:
    """
    Recherche un item similaire dans la concession donnée.
    Retourne (id_item, confiance) ou None.
    """
    if not description or not description.strip():
        return None

    norm_desc = normalize_text(description)
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession
    ).all()
    if not items:
        return None

    # Niveau 1 : correspondance exacte sur libelle_recherche
    for item in items:
        if item.libelle_recherche == norm_desc:
            return (item.id_item, 1.0)

    # Niveau 2 : synonymes
    desc_variants = set(expand_with_synonyms(norm_desc))
    for item in items:
        item_variants = set(expand_with_synonyms(item.libelle_recherche))
        if desc_variants & item_variants:
            return (item.id_item, 0.95)

    # Niveau 3 : fuzzy avec synonymes
    match = _fuzzy_with_synonyms(norm_desc, items, threshold=threshold_fuzzy)
    if match:
        return match

    # Niveau 4 : embedding
    index, item_ids, _ = _ensure_index(db, id_concession)
    if index is None or index.ntotal == 0:
        return None

    emb = _get_embedding_expanded(description).reshape(1, -1)
    scores, indices = index.search(emb, 3)
    best_score = float(scores[0][0])
    best_idx = int(indices[0][0])
    second_score = float(scores[0][1]) if len(scores[0]) > 1 else 0.0

    if best_score >= threshold_embedding and (best_score - second_score) > 0.10:
        if best_idx < len(item_ids):
            return (item_ids[best_idx], round(best_score, 4))

    return None


def find_similar_colonne(
    db: Session,
    libelle: str,
    id_concession: int,
    threshold_fuzzy: int = 72,
    threshold_embedding: float = 0.68,
) -> Optional[Tuple[int, float]]:
    """
    Recherche une colonne similaire dans la concession donnée.
    Retourne (id_colonne, confiance) ou None.
    """
    if not libelle or not libelle.strip():
        return None

    norm_lib = normalize_text(libelle)
    colonnes = db.query(models_sql.Colonne).filter(
        models_sql.Colonne.id_concession == id_concession
    ).all()
    if not colonnes:
        return None

    # Niveau 1 : exact
    for col in colonnes:
        if col.libelle_recherche == norm_lib:
            return (col.id_colonne, 1.0)

    # Niveau 2 : synonymes
    desc_variants = set(expand_with_synonyms(norm_lib))
    for col in colonnes:
        col_variants = set(expand_with_synonyms(col.libelle_recherche))
        if desc_variants & col_variants:
            return (col.id_colonne, 0.95)

    # Niveau 3 : fuzzy avec synonymes (réutilise la même logique que pour les items)
    # On peut créer une version allégée ou appeler une fonction générique
    best_id: Optional[int] = None
    best_score: int = 0
    for col in colonnes:
        col_variants = expand_with_synonyms(col.libelle_recherche)
        for cand_desc in desc_variants:
            for cand_item in col_variants:
                score = max(
                    rfuzz.token_sort_ratio(cand_desc, cand_item),
                    rfuzz.partial_ratio(cand_desc, cand_item),
                    rfuzz.token_set_ratio(cand_desc, cand_item),
                )
                if score > best_score:
                    best_score = score
                    best_id = col.id_colonne
    if best_id and best_score >= threshold_fuzzy:
        return (best_id, round(best_score / 100.0, 4))

    # Niveau 4 : embedding (on pourrait aussi créer un index pour les colonnes,
    # mais pour simplifier on s'arrête au fuzzy pour les colonnes)
    return None


def suggest_items_batch(
    db: Session,
    descriptions: List[str],
    id_concession: int,
) -> List[Dict[str, Any]]:
    """Suggère des items existants pour une liste de descriptions (dans une concession)."""
    results = []
    for desc in descriptions:
        match = find_similar_item(db, desc, id_concession)
        if match:
            item_id, confidence = match
            item = db.query(models_sql.Item).get(item_id)
            results.append({
                "nouvelle_description": desc,
                "item_existant_id": item_id,
                "libelle_canonique": item.libelle_canonique if item else None,
                "confiance": confidence,
            })
        else:
            results.append({
                "nouvelle_description": desc,
                "item_existant_id": None,
                "libelle_canonique": None,
                "confiance": None,
            })
    return results