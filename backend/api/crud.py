from sqlalchemy.orm import Session
from backend.api import models_sql, schemas
from datetime import datetime
from typing import List, Optional, Tuple
from backend.semantic.normalizer import normalize_text
import uuid


# ------------------------------------------------------------------------------
# 1. CONCESSIONS
# ------------------------------------------------------------------------------
def get_or_create_concession(db: Session, nom: str) -> models_sql.Concession:
    nom_norm = normalize_text(nom).upper()
    concession = db.query(models_sql.Concession).filter(
        models_sql.Concession.nom_normalise == nom_norm
    ).first()
    if not concession:
        concession = models_sql.Concession(nom=nom.strip(), nom_normalise=nom_norm)
        db.add(concession)
        db.flush()
    return concession


# ------------------------------------------------------------------------------
# 2. ITEMS
# ------------------------------------------------------------------------------
def get_or_create_item(db: Session, id_concession: int, libelle_canonique: str) -> Tuple[models_sql.Item, bool]:
    item = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        models_sql.Item.libelle_canonique == libelle_canonique.strip()
    ).first()
    if item:
        item.date_derniere_util = datetime.utcnow()
        db.flush()
        return item, False

    libelle_recherche = normalize_text(libelle_canonique)
    item = models_sql.Item(
        id_concession=id_concession,
        libelle_canonique=libelle_canonique.strip(),
        libelle_recherche=libelle_recherche,
        statut="actif",
        date_creation=datetime.utcnow(),
        date_derniere_util=datetime.utcnow(),
    )
    db.add(item)
    db.flush()
    return item, True


def merge_items(db: Session, source_id: int, target_id: int) -> bool:
    source = db.query(models_sql.Item).get(source_id)
    target = db.query(models_sql.Item).get(target_id)
    if not source or not target:
        return False
    lignes = db.query(models_sql.LigneFacture).filter(models_sql.LigneFacture.id_item == source_id).all()
    for ligne in lignes:
        ligne.id_item = target_id
    source.statut = "fusionne"
    source.fusionne_avec = target_id
    db.commit()
    return True


def create_item_manuel(db: Session, libelle: str, id_concession: Optional[int] = None) -> models_sql.Item:
    item = models_sql.Item(
        id_concession=id_concession,
        libelle_canonique=libelle.strip(),
        libelle_recherche=normalize_text(libelle),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_items(db: Session, item_ids: List[int]) -> Tuple[int, List[int]]:
    refused, deleted = [], 0
    for iid in item_ids:
        usage = db.query(models_sql.LigneFacture).filter(models_sql.LigneFacture.id_item == iid).count()
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


# ------------------------------------------------------------------------------
# 3. COLONNES
# ------------------------------------------------------------------------------
def get_or_create_colonne(db: Session, id_concession: int, libelle_canonique: str) -> models_sql.Colonne:
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


def create_colonne_manuel(db: Session, libelle: str, id_concession: Optional[int] = None) -> models_sql.Colonne:
    colonne = models_sql.Colonne(
        id_concession=id_concession,
        libelle_canonique=libelle.strip(),
        libelle_recherche=normalize_text(libelle),
    )
    db.add(colonne)
    db.commit()
    db.refresh(colonne)
    return colonne


def get_all_colonnes(db: Session) -> List[models_sql.Colonne]:
    return db.query(models_sql.Colonne).order_by(models_sql.Colonne.libelle_canonique).all()


# ------------------------------------------------------------------------------
# 4. FACTURES
# ------------------------------------------------------------------------------
def create_facture(db: Session, facture_data: schemas.FactureCreate) -> models_sql.Facture:
    if not facture_data.numero_facture:
        facture_data.numero_facture = f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
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


def create_lignes_facture(db: Session, id_facture: int, items_data: List[schemas.LigneFacturePayload],
                          id_concession: int, matches: Optional[List[dict]] = None) -> None:
    match_map = {m["description"]: m for m in matches} if matches else {}
    for item_dict in items_data:
        description = item_dict.description.strip()
        if not description:
            continue
        match_info = match_map.get(description, {})
        if match_info.get("item_id"):
            item = db.query(models_sql.Item).get(match_info["item_id"])
            if item:
                item.date_derniere_util = datetime.utcnow()
            else:
                item, _ = get_or_create_item(db, id_concession, description)
        else:
            item, _ = get_or_create_item(db, id_concession, description)

        ligne = models_sql.LigneFacture(
            id_facture=id_facture, id_item=item.id_item,
            confiance=match_info.get("confiance", 1.0),
            auto_match=match_info.get("auto_match", "1"),
        )
        db.add(ligne)
        db.flush()

        for col_nom, valeur_brute in item_dict.valeurs.items():
            col_nom = col_nom.strip()
            if not col_nom or valeur_brute is None:
                continue
            val_str = str(valeur_brute).strip()
            if not val_str:
                continue
            colonne = get_or_create_colonne(db, id_concession, col_nom)
            valeur_ligne = models_sql.ValeurLigne(id_ligne=ligne.id_ligne, id_colonne=colonne.id_colonne, valeur_brute=val_str)
            db.add(valeur_ligne)
    db.commit()


def get_all_factures(db: Session) -> List[models_sql.Facture]:
    return db.query(models_sql.Facture).order_by(models_sql.Facture.id_facture.desc()).all()


def get_facture_by_id(db: Session, facture_id: int) -> Optional[models_sql.Facture]:
    return db.query(models_sql.Facture).filter(models_sql.Facture.id_facture == facture_id).first()


def get_fact_data_by_facture(db: Session, facture_id: int) -> List[dict]:
    lignes = db.query(models_sql.LigneFacture).filter(models_sql.LigneFacture.id_facture == facture_id).all()
    result = []
    for ligne in lignes:
        item = db.query(models_sql.Item).get(ligne.id_item)
        valeurs = db.query(models_sql.ValeurLigne).filter(models_sql.ValeurLigne.id_ligne == ligne.id_ligne).all()
        result.append({
            "id_ligne": ligne.id_ligne,
            "item": item.libelle_canonique if item else None,
            "auto_match": ligne.auto_match,
            "confiance": ligne.confiance,
            "valeurs": [{"colonne": db.query(models_sql.Colonne).get(v.id_colonne).libelle_canonique, "valeur_brute": v.valeur_brute} for v in valeurs]
        })
    return result


def delete_facture(db: Session, facture_id: int) -> bool:
    facture = db.query(models_sql.Facture).get(facture_id)
    if facture:
        db.delete(facture)
        db.commit()
        return True
    return False
