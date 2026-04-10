from sqlalchemy.orm import Session
from api import models_sql, schemas
from datetime import datetime
from typing import List, Dict, Any, Optional


def get_or_create_item(db: Session, nom_item: str) -> models_sql.Item:
    item = db.query(models_sql.Item).filter(models_sql.Item.nom_item == nom_item).first()
    if not item:
        item = models_sql.Item(nom_item=nom_item)
        db.add(item)
        db.flush()
    return item


def get_or_create_colonne(db: Session, nom_colonne: str) -> models_sql.Colonne:
    col = db.query(models_sql.Colonne).filter(models_sql.Colonne.nom_colonne == nom_colonne).first()
    if not col:
        col = models_sql.Colonne(nom_colonne=nom_colonne)
        db.add(col)
        db.flush()
    return col


def create_facture(db: Session, facture_data: schemas.FactureCreate) -> models_sql.Facture:
    db_facture = models_sql.Facture(
        nom_fichier=facture_data.nom_fichier,
        date_facture=facture_data.date_facture,
        concession=facture_data.concession,
        devise=facture_data.devise,
        client=facture_data.client,
        objet=facture_data.objet,
    )
    db.add(db_facture)
    db.flush()
    return db_facture


def create_fact_data(
    db: Session,
    id_facture: int,
    items_data: List[Dict[str, Any]],
) -> None:
    """
    Insère les données en évitant les doublons (id_item, id_colonne) par facture.
    """
    # Dictionnaire pour dédoublonner : (id_item, id_colonne) -> valeur
    unique_combos = {}
    for item_dict in items_data:
        description = item_dict.get("description", "").strip()
        if not description:
            continue
        item = get_or_create_item(db, description)
        for col_nom, valeur in item_dict.get("valeurs", {}).items():
            col_nom = col_nom.strip()
            if not col_nom:
                continue
            colonne = get_or_create_colonne(db, col_nom)
            key = (item.id_item, colonne.id_colonne)
            # Si la même combinaison apparaît plusieurs fois, on garde la valeur (non None de préférence)
            if key not in unique_combos or (valeur is not None and unique_combos[key] is None):
                unique_combos[key] = valeur

    # Insérer chaque combo s'il n'existe pas déjà dans la base pour cette facture
    for (id_item, id_colonne), valeur in unique_combos.items():
        existing = db.query(models_sql.FactData).filter(
            models_sql.FactData.id_facture == id_facture,
            models_sql.FactData.id_item == id_item,
            models_sql.FactData.id_colonne == id_colonne
        ).first()
        if not existing:
            fd = models_sql.FactData(
                id_facture=id_facture,
                id_item=id_item,
                id_colonne=id_colonne,
                valeur=str(valeur) if valeur is not None else None,
            )
            db.add(fd)
    db.commit()


def get_all_factures(db: Session) -> List[models_sql.Facture]:
    return db.query(models_sql.Facture).order_by(models_sql.Facture.id_facture.desc()).all()


def get_facture_by_id(db: Session, facture_id: int) -> Optional[models_sql.Facture]:
    return db.query(models_sql.Facture).filter(models_sql.Facture.id_facture == facture_id).first()


def get_fact_data_by_facture(db: Session, facture_id: int) -> List[models_sql.FactData]:
    return db.query(models_sql.FactData).filter(models_sql.FactData.id_facture == facture_id).all()


def get_all_items(db: Session) -> List[models_sql.Item]:
    return db.query(models_sql.Item).order_by(models_sql.Item.nom_item).all()


def get_all_colonnes(db: Session) -> List[models_sql.Colonne]:
    return db.query(models_sql.Colonne).order_by(models_sql.Colonne.nom_colonne).all()


def update_fact_data(
    db: Session,
    id_facture: int,
    id_item: int,
    id_colonne: int,
    nouvelle_valeur: float,
) -> Optional[models_sql.FactData]:
    fd = db.query(models_sql.FactData).filter(
        models_sql.FactData.id_facture == id_facture,
        models_sql.FactData.id_item == id_item,
        models_sql.FactData.id_colonne == id_colonne,
    ).first()
    if fd:
        audit = models_sql.AuditLog(
            table_name="fact_data",
            action="UPDATE",
            record_id=id_facture,
            old_value=str(fd.valeur),
            new_value=str(nouvelle_valeur),
            modified_by="user",
        )
        db.add(audit)
        fd.valeur = nouvelle_valeur
        fd.date_insertion = datetime.utcnow()
        db.commit()
        db.refresh(fd)
    return fd


def delete_fact_data(
    db: Session,
    id_facture: int,
    id_item: int,
    id_colonne: int,
) -> bool:
    fd = db.query(models_sql.FactData).filter(
        models_sql.FactData.id_facture == id_facture,
        models_sql.FactData.id_item == id_item,
        models_sql.FactData.id_colonne == id_colonne,
    ).first()
    if fd:
        audit = models_sql.AuditLog(
            table_name="fact_data",
            action="DELETE",
            record_id=id_facture,
            old_value=str(fd.valeur),
            new_value=None,
            modified_by="user",
        )
        db.add(audit)
        db.delete(fd)
        db.commit()
        return True
    return False