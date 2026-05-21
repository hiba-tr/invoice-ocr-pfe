from sqlalchemy.orm import Session
from backend.api import models_sql, schemas
from datetime import datetime
from typing import List, Optional, Tuple
from backend.semantic.preprocessing.normalizer import normalize_text
import uuid
import logging

_log = logging.getLogger(__name__)

STATUT_ACTIF = "actif"


# ═══════════════════════════════════════════════════════════════
# 1. CONCESSIONS
# ═══════════════════════════════════════════════════════════════

def get_or_create_concession(db: Session, nom: str) -> models_sql.Concession:
    """Recherche une concession par son nom normalisé ; la crée si absente."""
    nom_norm = normalize_text(nom).upper()
    concession = db.query(models_sql.Concession).filter(
        models_sql.Concession.nom_normalise == nom_norm
    ).first()
    if not concession:
        concession = models_sql.Concession(nom=nom.strip(), nom_normalise=nom_norm)
        db.add(concession)
        db.flush()
    return concession


# ═══════════════════════════════════════════════════════════════
# 2. ITEMS
# ═══════════════════════════════════════════════════════════════

def get_or_create_item(
    db: Session,
    id_concession: int,
    libelle_canonique: str
) -> Tuple[models_sql.Item, bool]:
    """
    Recherche un item par libellé canonique pour une concession donnée.
    Retourne (item, créé). Met à jour libelle_recherche si dérivé.
    """
    item = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        models_sql.Item.libelle_canonique == libelle_canonique.strip()
    ).first()
    if item:
        item.date_derniere_util = datetime.utcnow()
        refreshed = normalize_text(libelle_canonique)
        if item.libelle_recherche != refreshed:
            item.libelle_recherche = refreshed
        db.flush()
        return item, False

    libelle_recherche = normalize_text(libelle_canonique)
    item = models_sql.Item(
        id_concession=id_concession,
        libelle_canonique=libelle_canonique.strip(),
        libelle_recherche=libelle_recherche,
        statut=STATUT_ACTIF,
        date_creation=datetime.utcnow(),
        date_derniere_util=datetime.utcnow(),
    )
    db.add(item)
    db.flush()
    return item, True


def merge_items(db: Session, source_id: int, target_id: int) -> bool:
    """Fusionne deux items en réattribuant les lignes."""
    source = db.query(models_sql.Item).get(source_id)
    target = db.query(models_sql.Item).get(target_id)
    if not source or not target:
        return False
    for ligne in db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_item == source_id
    ).all():
        ligne.id_item = target_id
    source.statut = "fusionne"
    source.fusionne_avec = target_id
    db.commit()
    return True


def create_item_manuel(
    db: Session, libelle: str, id_concession: Optional[int] = None
) -> models_sql.Item:
    """Création manuelle d'un item."""
    item = models_sql.Item(
        id_concession=id_concession,
        libelle_canonique=libelle.strip(),
        libelle_recherche=normalize_text(libelle),
        statut=STATUT_ACTIF,
        date_creation=datetime.utcnow(),
        date_derniere_util=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item_id: int, new_libelle: str) -> Optional[models_sql.Item]:
    """Mise à jour du libellé d'un item."""
    item = db.query(models_sql.Item).get(item_id)
    if item:
        item.libelle_canonique = new_libelle.strip()
        item.libelle_recherche = normalize_text(new_libelle)
        db.commit()
        db.refresh(item)
    return item


def delete_items(db: Session, item_ids: List[int]) -> Tuple[int, List[int]]:
    """Supprime les items non utilisés ; retourne (nb_supprimés, ids_refusés)."""
    refused, deleted = [], 0
    for iid in item_ids:
        usage = db.query(models_sql.LigneFacture).filter(
            models_sql.LigneFacture.id_item == iid
        ).count()
        if usage > 0:
            refused.append(iid)
            continue
        item = db.query(models_sql.Item).get(iid)
        if item:
            db.delete(item)
            deleted += 1
    db.commit()
    return deleted, refused


def get_all_items(db: Session) -> List[models_sql.Item]:
    return db.query(models_sql.Item).order_by(models_sql.Item.libelle_canonique).all()


def get_items_for_matching(db: Session, id_concession: int) -> List[models_sql.Item]:
    """Retourne les items actifs d'une concession pour le matching sémantique."""
    return (
        db.query(models_sql.Item)
        .filter(
            models_sql.Item.id_concession == id_concession,
            models_sql.Item.statut == STATUT_ACTIF,
        )
        .order_by(models_sql.Item.libelle_canonique)
        .all()
    )


def get_item_usage_count(db: Session, item_id: int) -> int:
    return db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_item == item_id
    ).count()


# ═══════════════════════════════════════════════════════════════
# 3. COLONNES
# ═══════════════════════════════════════════════════════════════

def get_or_create_colonne(
    db: Session,
    id_concession: int,
    libelle_canonique: str
) -> models_sql.Colonne:
    """Recherche ou crée une colonne pour une concession donnée."""
    colonne = db.query(models_sql.Colonne).filter(
        models_sql.Colonne.id_concession == id_concession,
        models_sql.Colonne.libelle_canonique == libelle_canonique.strip()
    ).first()
    if not colonne:
        colonne = models_sql.Colonne(
            id_concession=id_concession,
            libelle_canonique=libelle_canonique.strip(),
            libelle_recherche=normalize_text(libelle_canonique),
        )
        db.add(colonne)
        db.flush()
    return colonne


def create_colonne_manuel(
    db: Session, libelle: str, id_concession: Optional[int] = None
) -> models_sql.Colonne:
    """Création manuelle d'une colonne."""
    colonne = models_sql.Colonne(
        id_concession=id_concession,
        libelle_canonique=libelle.strip(),
        libelle_recherche=normalize_text(libelle),
    )
    db.add(colonne)
    db.commit()
    db.refresh(colonne)
    return colonne


def update_colonne(db: Session, colonne_id: int, new_libelle: str) -> Optional[models_sql.Colonne]:
    """Mise à jour du libellé d'une colonne."""
    colonne = db.query(models_sql.Colonne).get(colonne_id)
    if colonne:
        colonne.libelle_canonique = new_libelle.strip()
        colonne.libelle_recherche = normalize_text(new_libelle)
        db.commit()
        db.refresh(colonne)
    return colonne


def delete_colonnes(db: Session, colonne_ids: List[int]) -> Tuple[int, List[int]]:
    """Supprime les colonnes non utilisées ; retourne (nb_supprimées, ids_refusés)."""
    refused, deleted = [], 0
    for cid in colonne_ids:
        usage = db.query(models_sql.ValeurLigne).filter(
            models_sql.ValeurLigne.id_colonne == cid
        ).count()
        if usage > 0:
            refused.append(cid)
            continue
        col = db.query(models_sql.Colonne).get(cid)
        if col:
            db.delete(col)
            deleted += 1
    db.commit()
    return deleted, refused


def get_all_colonnes(db: Session) -> List[models_sql.Colonne]:
    return db.query(models_sql.Colonne).order_by(models_sql.Colonne.libelle_canonique).all()


def get_colonne_usage_count(db: Session, colonne_id: int) -> int:
    return db.query(models_sql.ValeurLigne).filter(
        models_sql.ValeurLigne.id_colonne == colonne_id
    ).count()


# ═══════════════════════════════════════════════════════════════
# 4. FACTURES
# ═══════════════════════════════════════════════════════════════

def create_facture(db: Session, facture_data: schemas.FactureCreate) -> models_sql.Facture:
    """Création d'une facture ; génère un numéro automatique si absent."""
    if not facture_data.numero_facture:
        facture_data.numero_facture = (
            f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
    db_facture = models_sql.Facture(
        id_concession=facture_data.id_concession,
        numero_facture=facture_data.numero_facture,
        date_facture=facture_data.date_facture,
        devise=facture_data.devise or "EUR",
        fichier_source=facture_data.fichier_source,
        statut=facture_data.statut or "traite",
        total_montant=facture_data.total_montant,
        fournisseur=facture_data.fournisseur,
    )
    db.add(db_facture)
    db.flush()
    return db_facture


def _ensure_default_section(db: Session, id_facture: int) -> int:
    """Crée une section par défaut (index 0) si aucune n'existe. Retourne l'id_section."""
    existing = db.query(models_sql.SectionFacture).filter(
        models_sql.SectionFacture.id_facture == id_facture,
        models_sql.SectionFacture.section_index == 0,
    ).first()
    if existing:
        return existing.id_section
    section = models_sql.SectionFacture(
        id_facture=id_facture,
        section_index=0,
        titre="Section 1",
    )
    db.add(section)
    db.flush()
    return section.id_section


def _create_section_and_lines(
    db: Session,
    id_facture: int,
    section_index: int,
    section: schemas.SectionPayload,
    id_concession: int,
    matches: Optional[List[dict]] = None,
) -> models_sql.SectionFacture:
    """Crée une section, enregistre ses colonnes dans section_colonne, puis ses lignes."""
    section_db = models_sql.SectionFacture(
        id_facture=id_facture,
        section_index=section_index,
        titre=section.titre or f"Section {section_index + 1}",
    )
    db.add(section_db)
    db.flush()

    for col_payload in section.colonnes:
        col_db = get_or_create_colonne(db, id_concession, col_payload.header)
        db.add(models_sql.SectionColonne(
            id_section=section_db.id_section,
            id_colonne=col_db.id_colonne,
            ordre=col_payload.ordre,
        ))

    _insert_lignes(
        db,
        id_facture=id_facture,
        id_section=section_db.id_section,
        id_concession=id_concession,
        items_data=section.items_data,
        matches=matches,
    )
    return section_db


def create_lignes_facture(
    db: Session,
    id_facture: int,
    id_concession: int,
    matches: Optional[List[dict]] = None,
    items_data: Optional[List[schemas.LigneFacturePayload]] = None,
    sections: Optional[List[schemas.SectionPayload]] = None,
) -> None:
    """
    Point d'entrée principal pour créer les lignes d'une facture.
    - Mode sections : crée chaque section avec ses colonnes et ses lignes.
    - Mode plat    : crée une section par défaut et y rattache toutes les lignes.
    """
    if sections:
        for idx, section in enumerate(sections):
            _create_section_and_lines(db, id_facture, idx, section, id_concession, matches)
        db.commit()
        return

    if not items_data:
        return

    id_section = _ensure_default_section(db, id_facture)
    _insert_lignes(
        db,
        id_facture=id_facture,
        id_section=id_section,
        id_concession=id_concession,
        items_data=items_data,
        matches=matches,
    )
    db.commit()


def _insert_lignes(
    db: Session,
    id_facture: int,
    id_section: int,
    id_concession: int,
    items_data: List,
    matches: Optional[List[dict]] = None,
) -> None:
    """
    Insère les lignes et leurs valeurs dans une section donnée.
    Gère les décisions sémantiques (link / new / skip) portées par chaque item
    ou, à défaut, l'ancien mécanisme via la liste matches.
    """
    match_map = {m["description"]: m for m in matches} if matches else {}

    for item_obj in items_data:
        # Compatibilité objet Pydantic ou dict
        if hasattr(item_obj, "description"):
            description = (item_obj.description or "").strip()
            valeurs = getattr(item_obj, "valeurs", {})
            decision = getattr(item_obj, "semantic_decision", None)
            target_id = getattr(item_obj, "semantic_target_id", None)
            auto = getattr(item_obj, "semantic_auto", "0")
        else:
            description = item_obj.get("description", "").strip()
            valeurs = item_obj.get("valeurs", {})
            decision = None
            target_id = None
            auto = "0"

        if not description:
            continue

        # Résolution de la décision sémantique
        if decision is None:
            match_info = match_map.get(description, {})
            if match_info.get("item_id"):
                decision = "link"
                target_id = match_info["item_id"]
                auto = match_info.get("auto_match", "0")
            else:
                decision = "new"

        if decision == "skip":
            continue

        # Résolution de l'item
        if decision == "link" and target_id:
            item = db.query(models_sql.Item).get(target_id)
            if item:
                item.date_derniere_util = datetime.utcnow()
                confiance = 1.0
            else:
                item, _ = get_or_create_item(db, id_concession, description)
                confiance = 0.0
        else:
            item, _ = get_or_create_item(db, id_concession, description)
            confiance = 0.0

        ligne = models_sql.LigneFacture(
            id_facture=id_facture,
            id_item=item.id_item,
            id_section=id_section,
            confiance=confiance,
            auto_match=auto,
        )
        db.add(ligne)
        db.flush()

        for col_nom, valeur_brute in valeurs.items():
            col_nom = col_nom.strip() if col_nom else ""
            if not col_nom or valeur_brute is None:
                continue
            val_str = str(valeur_brute).strip()
            if not val_str:
                continue

            colonne = get_or_create_colonne(db, id_concession, col_nom)

            valeur_numerique = None
            try:
                clean_val = val_str.replace(" ", "").replace(",", ".").replace("€", "").strip()
                if clean_val:
                    valeur_numerique = float(clean_val)
            except (ValueError, TypeError):
                pass

            db.add(models_sql.ValeurLigne(
                id_ligne=ligne.id_ligne,
                id_colonne=colonne.id_colonne,
                valeur_brute=val_str,
                valeur_numerique=valeur_numerique,
            ))


def get_all_factures(db: Session) -> List[models_sql.Facture]:
    return db.query(models_sql.Facture).order_by(models_sql.Facture.id_facture.desc()).all()


def get_facture_by_id(db: Session, facture_id: int) -> Optional[models_sql.Facture]:
    return db.query(models_sql.Facture).filter(
        models_sql.Facture.id_facture == facture_id
    ).first()


def get_fact_data_by_facture(db: Session, facture_id: int) -> List[dict]:
    """Retourne les lignes d'une facture avec item, valeurs, confiance et id_section."""
    lignes = db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_facture == facture_id
    ).all()
    result = []
    for ligne in lignes:
        item = db.query(models_sql.Item).get(ligne.id_item)
        valeurs = db.query(models_sql.ValeurLigne).filter(
            models_sql.ValeurLigne.id_ligne == ligne.id_ligne
        ).all()
        result.append({
            "id_ligne": ligne.id_ligne,
            "item": item.libelle_canonique if item else None,
            "auto_match": ligne.auto_match,
            "confiance": ligne.confiance,
            "id_section": ligne.id_section,
            "valeurs": [
                {
                    "colonne": db.query(models_sql.Colonne).get(v.id_colonne).libelle_canonique,
                    "valeur_brute": v.valeur_brute,
                }
                for v in valeurs
            ],
        })
    return result


def delete_facture(db: Session, facture_id: int) -> bool:
    """
    Suppression d'une facture. Nettoie explicitement lignes et valeurs
    avant suppression pour éviter les surprises de cascade.
    """
    facture = db.query(models_sql.Facture).get(facture_id)
    if not facture:
        return False
    for ligne in db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_facture == facture_id
    ).all():
        db.query(models_sql.ValeurLigne).filter(
            models_sql.ValeurLigne.id_ligne == ligne.id_ligne
        ).delete()
        db.delete(ligne)
    db.delete(facture)
    db.commit()
    return True


# ═══════════════════════════════════════════════════════════════
# 5. VALEURS
# ═══════════════════════════════════════════════════════════════

def update_valeur_ligne(
    db: Session,
    id_ligne: int,
    id_colonne: int,
    nouvelle_valeur_brute: str,
) -> Optional[models_sql.ValeurLigne]:
    vl = db.query(models_sql.ValeurLigne).filter(
        models_sql.ValeurLigne.id_ligne == id_ligne,
        models_sql.ValeurLigne.id_colonne == id_colonne,
    ).first()
    if vl:
        vl.valeur_brute = nouvelle_valeur_brute
        db.commit()
        db.refresh(vl)
    return vl


def delete_valeur_ligne(db: Session, id_ligne: int, id_colonne: int) -> bool:
    vl = db.query(models_sql.ValeurLigne).filter(
        models_sql.ValeurLigne.id_ligne == id_ligne,
        models_sql.ValeurLigne.id_colonne == id_colonne,
    ).first()
    if vl:
        db.delete(vl)
        db.commit()
        return True
    return False