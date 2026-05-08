from sqlalchemy.orm import Session
from backend.api import models_sql, schemas
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from backend.semantic.semantic import normalize_text

# ------------------------------------------------------------------------------
# 1. GESTION DES CONCESSIONS
# ------------------------------------------------------------------------------
def get_or_create_concession(db: Session, nom: str) -> models_sql.Concession:
    """Recherche une concession par son nom normalisé ; la crée si absente."""
    nom_norm = normalize_text(nom).upper()
    concession = db.query(models_sql.Concession).filter(
        models_sql.Concession.nom_normalise == nom_norm
    ).first()
    if not concession:
        concession = models_sql.Concession(
            nom=nom,
            nom_normalise=nom_norm
        )
        db.add(concession)
        db.flush()
    return concession


# ------------------------------------------------------------------------------
# 2. GESTION DES ITEMS (liés à une concession)
# ------------------------------------------------------------------------------
def get_or_create_item(
    db: Session,
    id_concession: int,
    libelle_canonique: str
) -> models_sql.Item:
    """Recherche un item par libellé canonique pour une concession donnée."""
    item = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        models_sql.Item.libelle_canonique == libelle_canonique
    ).first()
    if not item:
        libelle_recherche = normalize_text(libelle_canonique)
        item = models_sql.Item(
            id_concession=id_concession,
            libelle_canonique=libelle_canonique,
            libelle_recherche=libelle_recherche
        )
        db.add(item)
        db.flush()
    return item


# ------------------------------------------------------------------------------
# 3. GESTION DES COLONNES (liées à une concession)
# ------------------------------------------------------------------------------
def get_or_create_colonne(
    db: Session,
    id_concession: int,
    libelle_canonique: str
) -> models_sql.Colonne:
    """Recherche une colonne par libellé canonique pour une concession donnée."""
    colonne = db.query(models_sql.Colonne).filter(
        models_sql.Colonne.id_concession == id_concession,
        models_sql.Colonne.libelle_canonique == libelle_canonique
    ).first()
    if not colonne:
        libelle_recherche = normalize_text(libelle_canonique)
        colonne = models_sql.Colonne(
            id_concession=id_concession,
            libelle_canonique=libelle_canonique,
            libelle_recherche=libelle_recherche
        )
        db.add(colonne)
        db.flush()
    return colonne


# ------------------------------------------------------------------------------
# 4. CRÉATION D'UNE FACTURE (avec concession)
# ------------------------------------------------------------------------------
import uuid

def create_facture(
    db: Session,
    facture_data: schemas.FactureCreate
) -> models_sql.Facture:
    """Crée une facture dans la base, génère un numéro automatique si absent."""
    # Si le numéro de facture est vide ou None, générer un identifiant unique
    if not facture_data.numero_facture:
        # Exemple : AUTO_20260422_143052_abc123
        facture_data.numero_facture = f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    db_facture = models_sql.Facture(
        id_concession=facture_data.id_concession,
        numero_facture=facture_data.numero_facture,
        date_facture=facture_data.date_facture,
        devise=facture_data.devise,
        fichier_source=facture_data.fichier_source,
        valide=facture_data.valide or "0",
        total_montant=facture_data.total_montant,
    )
    db.add(db_facture)
    db.flush()
    return db_facture

def create_lignes_facture(
    db: Session,
    id_facture: int,
    items_data: List[schemas.LigneFacturePayload],
    id_concession: int,
) -> None:
    for item_dict in items_data:
        description = item_dict.description.strip()
        if not description:
            continue

        # 1. Récupérer ou créer l'item pour cette concession
        item = get_or_create_item(db, id_concession, description)

        # 2. Créer la ligne de facture
        ligne = models_sql.LigneFacture(
            id_facture=id_facture,
            id_item=item.id_item
        )
        db.add(ligne)
        db.flush()  # Pour obtenir id_ligne

        # 3. Insérer les valeurs brutes pour chaque colonne
        for col_nom, valeur_brute in item_dict.valeurs.items():
            col_nom = col_nom.strip()
            # Ignorer les colonnes sans nom ou les valeurs nulles/vides
            if not col_nom:
                continue
            if valeur_brute is None:
                continue
            # Convertir en chaîne et vérifier si elle est vide après nettoyage
            val_str = str(valeur_brute).strip()
            if val_str == "":
                continue  # Ne pas insérer de valeur vide

            colonne = get_or_create_colonne(db, id_concession, col_nom)
            valeur_ligne = models_sql.ValeurLigne(
                id_ligne=ligne.id_ligne,
                id_colonne=colonne.id_colonne,
                valeur_brute=val_str
            )
            db.add(valeur_ligne)

    db.commit()

# ------------------------------------------------------------------------------
# 6. FONCTIONS DE LECTURE (adaptées aux nouveaux modèles)
# ------------------------------------------------------------------------------
def get_all_factures(db: Session) -> List[models_sql.Facture]:
    return db.query(models_sql.Facture).order_by(models_sql.Facture.id_facture.desc()).all()


def get_facture_by_id(db: Session, facture_id: int) -> Optional[models_sql.Facture]:
    return db.query(models_sql.Facture).filter(models_sql.Facture.id_facture == facture_id).first()


def get_fact_data_by_facture(db: Session, facture_id: int):
    """
    Retourne les lignes et valeurs d'une facture.
    (Remplacera l'ancienne fonction qui renvoyait FactData)
    """
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
            "valeurs": [
                {
                    "colonne": db.query(models_sql.Colonne).get(v.id_colonne).libelle_canonique,
                    "valeur_brute": v.valeur_brute
                }
                for v in valeurs
            ]
        })
    return result


def get_all_items(db: Session) -> List[models_sql.Item]:
    return db.query(models_sql.Item).order_by(models_sql.Item.libelle_canonique).all()


def get_all_colonnes(db: Session) -> List[models_sql.Colonne]:
    return db.query(models_sql.Colonne).order_by(models_sql.Colonne.libelle_canonique).all()


# ------------------------------------------------------------------------------
# 7. MISE À JOUR / SUPPRESSION DE VALEURS (si besoin)
# ------------------------------------------------------------------------------
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
        # Audit possible
        vl.valeur_brute = nouvelle_valeur_brute
        db.commit()
        db.refresh(vl)
    return vl


def delete_valeur_ligne(
    db: Session,
    id_ligne: int,
    id_colonne: int,
) -> bool:
    vl = db.query(models_sql.ValeurLigne).filter(
        models_sql.ValeurLigne.id_ligne == id_ligne,
        models_sql.ValeurLigne.id_colonne == id_colonne,
    ).first()
    if vl:
        db.delete(vl)
        db.commit()
        return True
    return False


#ajouter pour dashboard
# ---------- Items ----------
def delete_items(db: Session, item_ids: List[int]) -> Tuple[int, List[int]]:
    """
    Supprime des items s'ils ne sont pas utilisés.
    Retourne (nombre_supprimés, liste_des_ids_refusés_car_utilisés)
    """
    refused = []
    deleted = 0
    for iid in item_ids:
        # Vérifier si l'item est référencé dans une ligne de facture
        usage_count = db.query(models_sql.LigneFacture).filter(
            models_sql.LigneFacture.id_item == iid
        ).count()
        if usage_count > 0:
            refused.append(iid)
            continue
        item = db.query(models_sql.Item).get(iid)
        if item:
            db.delete(item)
            deleted += 1
    db.commit()
    return deleted, refused

# ---------- Colonnes ----------
def delete_colonnes(db: Session, colonne_ids: List[int]) -> Tuple[int, List[int]]:
    refused = []
    deleted = 0
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

# ---------- Factures ----------
def delete_facture(db: Session, facture_id: int):
    facture = db.query(models_sql.Facture).get(facture_id)
    if facture:
        # Supprimer d'abord les lignes et valeurs associées (cascade possible)
        lignes = db.query(models_sql.LigneFacture).filter(
            models_sql.LigneFacture.id_facture == facture_id
        ).all()
        for ligne in lignes:
            db.query(models_sql.ValeurLigne).filter(
                models_sql.ValeurLigne.id_ligne == ligne.id_ligne
            ).delete()
            db.delete(ligne)
        db.delete(facture)
        db.commit()
        return True
    return False


def create_item_manuel(db: Session, libelle: str, id_concession: Optional[int] = None) -> models_sql.Item:
    item = models_sql.Item(
        id_concession=id_concession,
        libelle_canonique=libelle,
        libelle_recherche=normalize_text(libelle)
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

def create_colonne_manuel(db: Session, libelle: str, id_concession: Optional[int] = None) -> models_sql.Colonne:
    colonne = models_sql.Colonne(
        id_concession=id_concession,
        libelle_canonique=libelle,
        libelle_recherche=normalize_text(libelle)
    )
    db.add(colonne)
    db.commit()
    db.refresh(colonne)
    return colonne

def update_item(db: Session, item_id: int, new_libelle: str) -> Optional[models_sql.Item]:
    item = db.query(models_sql.Item).get(item_id)
    if item:
        item.libelle_canonique = new_libelle
        item.libelle_recherche = normalize_text(new_libelle)
        db.commit()
        db.refresh(item)
    return item

def update_colonne(db: Session, colonne_id: int, new_libelle: str) -> Optional[models_sql.Colonne]:
    colonne = db.query(models_sql.Colonne).get(colonne_id)
    if colonne:
        colonne.libelle_canonique = new_libelle
        colonne.libelle_recherche = normalize_text(new_libelle)
        db.commit()
        db.refresh(colonne)
    return colonne

def get_item_usage_count(db: Session, item_id: int) -> int:
    return db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_item == item_id
    ).count()

def get_colonne_usage_count(db: Session, colonne_id: int) -> int:
    return db.query(models_sql.ValeurLigne).filter(
        models_sql.ValeurLigne.id_colonne == colonne_id
    ).count()

