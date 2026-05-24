from sqlalchemy.orm import Session
from backend.api import models_sql, schemas
from datetime import datetime
from typing import List, Optional, Tuple
from backend.semantic.preprocessing.normalizer import normalize_text
import uuid
import logging
_log = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# 1. CONCESSIONS
# ------------------------------------------------------------------------------
def get_or_create_concession(db: Session, nom: str) -> models_sql.Concession:
    """Recherche une concession par son nom normalisé ; la crée si absente."""
    # On utilise la version de la binôme (strip + import correct)
    nom_norm = normalize_text(nom).upper()
    concession = db.query(models_sql.Concession).filter(
        models_sql.Concession.nom_normalise == nom_norm
    ).first()
    if not concession:
        concession = models_sql.Concession(
            nom=nom.strip(),
            nom_normalise=nom_norm
        )
        db.add(concession)
        db.flush()
    return concession


# ------------------------------------------------------------------------------
# 2. ITEMS
# ------------------------------------------------------------------------------
def get_or_create_item(
    db: Session,
    id_concession: int,
    libelle_canonique: str
) -> Tuple[models_sql.Item, bool]:
    """
    Recherche un item par libellé canonique pour une concession donnée.
    Retourne (item, créé) – version enrichie de la binôme.
    """
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
    """Fusionne deux items (binôme)."""
    source = db.query(models_sql.Item).get(source_id)
    target = db.query(models_sql.Item).get(target_id)
    if not source or not target:
        return False
    lignes = db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_item == source_id
    ).all()
    for ligne in lignes:
        ligne.id_item = target_id
    source.statut = "fusionne"
    source.fusionne_avec = target_id
    db.commit()
    return True


def create_item_manuel(
    db: Session, libelle: str, id_concession: Optional[int] = None
) -> models_sql.Item:
    """Création manuelle d'un item (version binôme avec strip)."""
    item = models_sql.Item(
        id_concession=id_concession,
        libelle_canonique=libelle.strip(),
        libelle_recherche=normalize_text(libelle),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item_id: int, new_libelle: str) -> Optional[models_sql.Item]:
    """Mise à jour d'un item (ta version dashboard)."""
    item = db.query(models_sql.Item).get(item_id)
    if item:
        item.libelle_canonique = new_libelle
        item.libelle_recherche = normalize_text(new_libelle)
        db.commit()
        db.refresh(item)
    return item


def delete_items(db: Session, item_ids: List[int]) -> Tuple[int, List[int]]:
    """Suppression d'items (version binôme, identique à la tienne)."""
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


def get_item_usage_count(db: Session, item_id: int) -> int:
    """Compte le nombre d'utilisations d'un item (ta version)."""
    return db.query(models_sql.LigneFacture).filter(
        models_sql.LigneFacture.id_item == item_id
    ).count()


# ------------------------------------------------------------------------------
# 3. COLONNES
# ------------------------------------------------------------------------------
# backend/api/crud.py - Fonction get_or_create_colonne corrigée

def get_or_create_colonne(
    db: Session,
    id_concession: int,
    libelle_canonique: str
) -> models_sql.Colonne:
    """
    Recherche ou crée une colonne (version corrigée avec validation).
    """
    # 🔥 CORRECTION : Vérifier que le libellé n'est pas vide
    if not libelle_canonique or not libelle_canonique.strip():
        # Générer un nom par défaut si le libellé est vide
        libelle_canonique = f"Colonne_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _log.warning(f"Libellé de colonne vide, remplacé par : {libelle_canonique}")
    
    libelle_clean = libelle_canonique.strip()
    
    colonne = db.query(models_sql.Colonne).filter(
        models_sql.Colonne.id_concession == id_concession,
        models_sql.Colonne.libelle_canonique == libelle_clean
    ).first()
    
    if not colonne:
        colonne = models_sql.Colonne(
            id_concession=id_concession,
            libelle_canonique=libelle_clean,
            libelle_recherche=normalize_text(libelle_clean),
        )
        db.add(colonne)
        db.flush()
        _log.info(f"Nouvelle colonne créée : {libelle_clean}")
    
    return colonne


def process_column_decision(
    db: Session,
    id_concession: int,
    header: str,
    semantic_decision: Optional[str] = None,
    semantic_target_id: Optional[int] = None
) -> models_sql.Colonne:
    """
    Traite une colonne avec décision sémantique.
    - 'link' → utilise la colonne existante
    - 'new' → crée une nouvelle colonne
    - 'skip' → None (ignorer, mais normalement on skip pas une colonne entière)
    """
    if semantic_decision == 'link' and semantic_target_id:
        colonne = db.query(models_sql.Colonne).get(semantic_target_id)
        if colonne:
            return colonne
    
    # Par défaut : get_or_create
    return get_or_create_colonne(db, id_concession, header)


def create_colonne_manuel(
    db: Session, libelle: str, id_concession: Optional[int] = None
) -> models_sql.Colonne:
    """Création manuelle d'une colonne (binôme)."""
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
    """Mise à jour d'une colonne (ta version)."""
    colonne = db.query(models_sql.Colonne).get(colonne_id)
    if colonne:
        colonne.libelle_canonique = new_libelle
        colonne.libelle_recherche = normalize_text(new_libelle)
        db.commit()
        db.refresh(colonne)
    return colonne


def delete_colonnes(db: Session, colonne_ids: List[int]) -> Tuple[int, List[int]]:
    """Suppression de colonnes (ta version, car absente de la binôme)."""
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
    """Compte le nombre d'utilisations d'une colonne (ta version)."""
    return db.query(models_sql.ValeurLigne).filter(
        models_sql.ValeurLigne.id_colonne == colonne_id
    ).count()


# ------------------------------------------------------------------------------
# 4. FACTURES
# ------------------------------------------------------------------------------
def create_facture(db: Session, facture_data: schemas.FactureCreate) -> models_sql.Facture:
    """Création d'une facture (version enrichie de la binôme)."""
    if not facture_data.numero_facture:
        facture_data.numero_facture = f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    db_facture = models_sql.Facture(
        id_concession=facture_data.id_concession,
        numero_facture=facture_data.numero_facture,
        date_facture=facture_data.date_facture,
        devise=facture_data.devise or "EUR",          # ajout binôme
        fichier_source=facture_data.fichier_source,
        statut=facture_data.statut or "traite",       # ajout binôme
        total_montant=facture_data.total_montant,
        fournisseur=facture_data.fournisseur, 
        extra_metadata=facture_data.extra_metadata,         # ajout binôme
    )
    db.add(db_facture)
    db.flush()
    return db_facture

# Dans crud.py, modifier _create_section_and_lines

def _create_section_and_lines(
    db: Session,
    id_facture: int,
    section_index: int,
    section: schemas.SectionPayload,
    id_concession: int,
    matches: Optional[List[dict]] = None
) -> models_sql.SectionFacture:
    section_db = models_sql.SectionFacture(
        id_facture=id_facture,
        section_index=section_index,
        titre=section.titre or f"Section {section_index + 1}"
    )
    db.add(section_db)
    db.flush()

    # Traitement des colonnes avec matching sémantique
    for col_payload in section.colonnes:
        # Utiliser la décision sémantique si présente
        if hasattr(col_payload, 'semantic_decision') and col_payload.semantic_decision:
            colonne = process_column_decision(
                db, 
                id_concession, 
                col_payload.header,
                col_payload.semantic_decision,
                col_payload.semantic_target_id
            )
        else:
            # Fallback : matching automatique
            colonne = get_or_create_colonne(db, id_concession, col_payload.header)
        
        section_col = models_sql.SectionColonne(
            id_section=section_db.id_section,
            id_colonne=colonne.id_colonne,
            ordre=col_payload.ordre
        )
        db.add(section_col)

    # Le reste reste identique
    create_lignes_facture(
        db,
        id_facture=id_facture,
        items_data=section.items_data,
        id_concession=id_concession,
        matches=matches,
        id_section=section_db.id_section
    )
    return section_db


def create_lignes_facture(
    db: Session,
    id_facture: int,
    items_data: Optional[List[schemas.LigneFacturePayload]] = None,
    id_concession: int = None,
    matches: Optional[List[dict]] = None,
    id_section: Optional[int] = None,
    sections: Optional[List[schemas.SectionPayload]] = None
) -> None:
    # Mode sections
    if sections:
        for idx, section in enumerate(sections):
            _create_section_and_lines(
                db, id_facture, idx, section, id_concession, matches
            )
        db.commit()
        return

    if not items_data:
        return

    # Section par défaut si aucune fournie
    if id_section is None:
        existing_section = db.query(models_sql.SectionFacture).filter_by(
            id_facture=id_facture, section_index=0
        ).first()
        if existing_section:
            id_section = existing_section.id_section
        else:
            default_section = models_sql.SectionFacture(
                id_facture=id_facture,
                section_index=0,
                titre="Section 1"
            )
            db.add(default_section)
            db.flush()
            id_section = default_section.id_section
            
    match_map = {m["description"]: m for m in matches} if matches else {}

    for item_dict in items_data:
        description = item_dict.description.strip()
        if not description:
            continue

        # 1. Décision sémantique (prioritaire)
        decision = getattr(item_dict, 'semantic_decision', None)
        target_id = getattr(item_dict, 'semantic_target_id', None)
        auto_flag = getattr(item_dict, 'semantic_auto', '1')

        if decision == 'skip':
            continue  # ignorer cette ligne

        item = None
        if decision == 'link' and target_id:
            item = db.query(models_sql.Item).get(target_id)
        elif decision == 'new':
            # Créer un nouvel item systématiquement
            item, _ = get_or_create_item(db, id_concession, description)
        else:
            # Pas de décision → fallback sur l'auto-match
            match_info = match_map.get(description, {})  
            if match_info.get("item_id"):
                item = db.query(models_sql.Item).get(match_info["item_id"])
            if not item:
                item, _ = get_or_create_item(db, id_concession, description)

        if not item:
            continue

        # Mise à jour date dernière utilisation
        item.date_derniere_util = datetime.utcnow()

        confiance = 1.0
        if decision != 'new' and decision != 'skip':
            # Récupérer la confiance du matching automatique si existante
            match_info = match_map.get(description, {}) 
            confiance = match_info.get("confiance", 1.0)

        ligne = models_sql.LigneFacture(
            id_facture=id_facture,
            id_item=item.id_item,
            id_section=id_section,
            confiance=confiance,
            auto_match=auto_flag,
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
            valeur_ligne = models_sql.ValeurLigne(
                id_ligne=ligne.id_ligne,
                id_colonne=colonne.id_colonne,
                valeur_brute=val_str
            )
            db.add(valeur_ligne)

    db.commit()


def get_all_factures(db: Session) -> List[models_sql.Facture]:
    return db.query(models_sql.Facture).order_by(models_sql.Facture.id_facture.desc()).all()


def get_facture_by_id(db: Session, facture_id: int) -> Optional[models_sql.Facture]:
    return db.query(models_sql.Facture).filter(models_sql.Facture.id_facture == facture_id).first()


def get_fact_data_by_facture(db: Session, facture_id: int) -> List[dict]:
    """Retourne les lignes avec auto_match et confiance (version binôme)."""
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
            
            "valeurs": [
                {
                    "colonne": db.query(models_sql.Colonne).get(v.id_colonne).libelle_canonique,
                    "valeur_brute": v.valeur_brute
                }
                for v in valeurs
            ]
        })
    return result


def delete_facture(db: Session, facture_id: int) -> bool:
    """
    Suppression d'une facture. On conserve la version robuste qui nettoie
    d'abord les lignes et valeurs (ta version) pour éviter les surprises
    de cascade.
    """
    facture = db.query(models_sql.Facture).get(facture_id)
    if facture:
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


# ------------------------------------------------------------------------------
# 5. VALEURS (ta version dashboard)
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