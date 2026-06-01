# ------------------------------------------------------------------------------
# main.py – version fusionnée
# Chaîne : extraction (invoice_extraction_bridge) → postprocess (pipeline)
#          → stockage avec matching sémantique automatique
# ------------------------------------------------------------------------------
import os
# Force le mode hors-ligne pour toutes les bibliothèques Hugging Face
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO
from datetime import datetime, date, timedelta
from typing import List, Optional
from pydantic import BaseModel
import tempfile
from pathlib import Path
import os
import time
import gc
import re
import hashlib
import json
import asyncio
import queue
import threading
import uuid
import openpyxl

# --- Imports métier (fusionnés) -------------------------------------------
from backend.api.database import get_db, engine, Base
from backend.api import models_sql, schemas, crud, resume
from backend.extraction.invoice_extraction_bridge import extract_invoice   # ton module
from backend.postprocess.pipeline import process_from_dict                 # ton module

# Après (code binôme)
from backend.semantic.preprocessing.normalizer import normalize_text
from backend.semantic.matching.pipeline import SemanticPipeline
from backend.semantic.matching.engine import MatchingEngine, DBItem
from backend.semantic.embeddings.indexer import get_or_build_index, invalidate_cache
from backend.semantic.embeddings.embedder import EMBEDDING_AVAILABLE
import logging
_log = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Configuration & utilitaires
# ------------------------------------------------------------------------------
def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

Base.metadata.create_all(bind=engine, checkfirst=True)
app = FastAPI(title="DocCore Invoice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _parse_montant(val_brute: str) -> float | None:
    """Parse robuste d’un montant (identique dans les deux versions)."""
    if not val_brute:
        return None
    s = str(val_brute).strip()
    s = re.sub(r'[€$£\u00a0\u202f]', '', s).strip()
    negative = s.startswith('(') and s.endswith(')')
    if negative:
        s = s[1:-1]
    if re.search(r'\.\d{3}[,]\d{2}$', s):
        s = s.replace('.', '').replace(',', '.')
    elif re.search(r',\d{3}[.]\d{2}$', s):
        s = s.replace(',', '')
    elif ',' in s and '.' not in s:
        s = s.replace(',', '.')
    elif '.' in s and ',' not in s:
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3:
            s = s.replace('.', '')
    else:
        s = re.sub(r"[\s']", '', s)
    try:
        result = float(s)
        return -result if negative else result
    except ValueError:
        return None

def _is_montant_column(col_name: str) -> bool:
    col_lower = col_name.lower().strip()
    HIGH = ['montant total', 'total ttc', 'total ht', 'total general', 'total facture', 'montant ttc', 'montant ht']
    MED = ['montant', 'total', 'amount', 'prix total', 'sous-total']
    LOW = ['prix', 'tarif', 'prix unitaire', 'pu', 'unit price', 'valeur', 'cout', 'cost']
    EXCLUDE = ['qte', 'quantite', 'quantity', 'qty', 'ref', 'reference', 'ref', 'taux', 'tva', 'remise', 'discount', 'code']
    for ex in EXCLUDE:
        if ex in col_lower:
            return False
    for h in HIGH:
        if h in col_lower:
            return True
    for m in MED:
        if m in col_lower:
            return True
    for l in LOW:
        if l in col_lower:
            return True
    return False
from sqlalchemy import or_

def _match_description(description: str, id_concession: int, db: Session) -> dict:
    """Helper commun pour tous les endpoints de matching."""
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        or_(models_sql.Item.statut == "actif", models_sql.Item.statut == None)
    ).all()
    
    if not items:
        return {"action": "create_new", "reason": "aucun item dans la base"}
    
    db_items = [DBItem(id_item=i.id_item, libelle_recherche=i.libelle_recherche,
                       libelle_canonique=i.libelle_canonique) for i in items]
    
    pipeline = SemanticPipeline()
    return pipeline.process_item(description, db_items, id_concession)
# ------------------------------------------------------------------------------
# 1. UPLOAD & EXTRACTION (ta chaîne : extract_invoice → process_from_dict)
# ------------------------------------------------------------------------------
@app.post("/upload")
async def upload_facture(file: UploadFile = File(...)):
    content = await file.read()
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()

        # ----- DIAGNOSTIC (optionnel) -----
        print("=" * 60)
        print("DIAGNOSTIC FICHIER TEMPORAIRE")
        print(f"  Nom original : {file.filename}")
        print(f"  Taille reçue  : {len(content)} octets")
        print(f"  Chemin temp   : {tmp_path}")
        print(f"  Taille disque : {os.path.getsize(tmp_path)} octets")
        print("=" * 60)

        # Extraction + post‑process (UN SEUL APPEL)
        import time
        t0 = time.time()
        import logging
        logging.getLogger("backend.extraction.engine").setLevel(logging.DEBUG)
        raw_result = extract_invoice(tmp_path, max_pages=50)
        print(f"[TIMER] extract_invoice: {time.time() - t0:.2f}s")

        t1 = time.time()
        invoice = process_from_dict(raw_result)
        structured = invoice.to_dict()
        print(f"[TIMER] process_from_dict + to_dict: {time.time() - t1:.2f}s")

        return JSONResponse(content=structured)

    finally:
        try:
            os.unlink(tmp_path)
        except PermissionError:
            gc.collect()
            time.sleep(0.5)
            try:
                os.unlink(tmp_path)
            except PermissionError:
                pass

# ------------------------------------------------------------------------------
# 2. CRÉATION D’UNE FACTURE avec pipeline sémantique automatique
# ------------------------------------------------------------------------------
@app.post("/facture", response_model=schemas.FactureOut)
def create_facture(payload: schemas.FactureWithItems,
                   db: Session = Depends(get_db),
                   force: bool = False):
    """
    Crée une facture :
      - hash de contenu basé sur les items (ta méthode, robuste)
      - exécute le pipeline sémantique (binôme) pour auto‑matcher les articles
      - passe les matches à create_lignes_facture (version binôme améliorée)
    """
    # 1. Concession
    concession_id = payload.facture.id_concession
    concession_nom = getattr(payload.facture, "nom_concession", None)
    if not concession_id and not concession_nom:
        raise HTTPException(status_code=400, detail="id_concession ou nom_concession requis")
    if not concession_id and concession_nom:
        concession = crud.get_or_create_concession(db, concession_nom)
        concession_id = concession.id_concession
    elif concession_id:
        concession = db.query(models_sql.Concession).get(concession_id)
        if not concession:
            raise HTTPException(status_code=404, detail="Concession introuvable")
    payload.facture.id_concession = concession_id

    # 2. Date
    if payload.facture.date_facture and isinstance(payload.facture.date_facture, str):
        parsed = parse_date(payload.facture.date_facture)
        if parsed is None:
            raise HTTPException(status_code=400, detail="Format de date invalide")
        payload.facture.date_facture = parsed

    # 3. Hash de contenu (basée sur tous les articles de la facture)
    all_items_for_hash = []
    if payload.items_data:
        all_items_for_hash = payload.items_data
    elif payload.sections:
        for section in payload.sections:
            all_items_for_hash.extend(section.items_data)

    normalized_items = []
    for item in all_items_for_hash:
        desc = item.description.strip()
        sorted_vals = sorted(item.valeurs.items()) if item.valeurs else []
        normalized_items.append({"description": desc, "valeurs": sorted_vals})
    normalized_items.sort(key=lambda x: x["description"])
    content_string = json.dumps(normalized_items, ensure_ascii=False, sort_keys=True)
    content_hash = hashlib.sha256(content_string.encode("utf-8")).hexdigest()

    # Vérification existence
    existing = db.query(models_sql.Facture).filter(
        models_sql.Facture.hash_contenu == content_hash
    ).first()
    if existing and not force:
        raise HTTPException(
            status_code=409,
            detail="Une facture avec le même contenu existe déjà. Utilisez force=true pour écraser."
        )
    if existing and force:
        db.delete(existing)
        db.commit()


 
    # 4. Création de la facture (crud enrichi par la binôme)
    db_facture = crud.create_facture(db, payload.facture)
    db_facture.hash_contenu = content_hash
    db.flush()

    matches = []
    # Log du nombre d'articles reçus (tous modes)
    if payload.items_data:
        total_articles = len(payload.items_data)
    elif payload.sections:
        total_articles = sum(len(s.items_data) for s in payload.sections)
    else:
        total_articles = 0
    print("Nombre d'articles reçus :", total_articles)
    # 6. Insertion des lignes avec les matches
    # 6. Insertion des lignes avec les sections (si présentes) ou mode plat
    if payload.sections:
        crud.create_lignes_facture(
            db,
            id_facture=db_facture.id_facture,
            id_concession=concession_id,
           
            sections=payload.sections
        )
    else:
        crud.create_lignes_facture(
            db,
            id_facture=db_facture.id_facture,
            items_data=payload.items_data or [],
            id_concession=concession_id,
          
        )

    # 7. Invalidation du cache sémantique pour cette concession
    invalidate_cache(concession_id)

    return db_facture

# ------------------------------------------------------------------------------
# 3. LECTURE DES FACTURES
# ------------------------------------------------------------------------------
@app.get("/factures", response_model=List[schemas.FactureOut])
def get_all_factures(db: Session = Depends(get_db)):
    return crud.get_all_factures(db)

@app.get("/facture/{facture_id}")
def get_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    data = crud.get_fact_data_by_facture(db, facture_id)
    return {"facture": facture, "data": data}

@app.get("/facture/{facture_id}/details")
def get_facture_details(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    details = []
    for ligne_info in lignes_data:
        for val in ligne_info["valeurs"]:
            details.append({
                "item": ligne_info["item"],
                "colonne": val["colonne"],
                "valeur": val["valeur_brute"],
                
            })
    return {"id_facture": facture_id, "details": details}
@app.get("/facture/{facture_id}/sections")
def get_facture_sections(facture_id: int, db: Session = Depends(get_db)):
    """
    Retourne les sections d'une facture avec leurs colonnes et lignes.
    """
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    sections_db = db.query(models_sql.SectionFacture).filter(
        models_sql.SectionFacture.id_facture == facture_id
    ).order_by(models_sql.SectionFacture.section_index).all()

    result = []
    for section in sections_db:
        # Colonnes de cette section (dans l'ordre)
        cols = db.query(models_sql.SectionColonne).filter(
            models_sql.SectionColonne.id_section == section.id_section
        ).order_by(models_sql.SectionColonne.ordre).all()

        headers = []
        for col in cols:
            colonne = db.query(models_sql.Colonne).get(col.id_colonne)
            if colonne:
                headers.append(colonne.libelle_canonique)

        # Lignes de cette section
        lignes = db.query(models_sql.LigneFacture).filter(
            models_sql.LigneFacture.id_section == section.id_section
        ).all()

        items_data = []
        for ligne in lignes:
            item = db.query(models_sql.Item).get(ligne.id_item)
            valeurs = db.query(models_sql.ValeurLigne).filter(
                models_sql.ValeurLigne.id_ligne == ligne.id_ligne
            ).all()

            valeurs_dict = {}
            for v in valeurs:
                colonne = db.query(models_sql.Colonne).get(v.id_colonne)
                if colonne and colonne.libelle_canonique in headers:
                    valeurs_dict[colonne.libelle_canonique] = v.valeur_brute

            items_data.append({
                "description": item.libelle_canonique if item else "",
                "valeurs": valeurs_dict
            })

        result.append({
            "titre": section.titre,
            "headers": headers,
            "items_data": items_data
        })

    return {"facture_id": facture_id, "sections": result}
# ------------------------------------------------------------------------------
# 4. GESTION DES ITEMS & COLONNES
# ------------------------------------------------------------------------------
@app.get("/items", response_model=List[schemas.ItemOut])
def get_all_items(db: Session = Depends(get_db),
                  id_concession: Optional[int] = Query(None)):
    if id_concession:
        items = db.query(models_sql.Item).filter(
            models_sql.Item.id_concession == id_concession,
            or_(models_sql.Item.statut == "actif", models_sql.Item.statut == None)
        ).all()
    else:
        items = crud.get_all_items(db)
    for item in items:
        item.usage_count = crud.get_item_usage_count(db, item.id_item)  # ta fonction
    return items

@app.get("/colonnes", response_model=List[schemas.ColonneOut])
def get_all_colonnes(db: Session = Depends(get_db),
                     id_concession: Optional[int] = Query(None)):
    if id_concession:
        colonnes = db.query(models_sql.Colonne).filter(
            models_sql.Colonne.id_concession == id_concession
        ).all()
    else:
        colonnes = crud.get_all_colonnes(db)
    for colonne in colonnes:
        colonne.usage_count = crud.get_colonne_usage_count(db, colonne.id_colonne)
    return colonnes

@app.post("/items", response_model=schemas.ItemOut)
def api_create_item(payload: schemas.ItemCreatePayload, db: Session = Depends(get_db)):
    item = crud.create_item_manuel(db, payload.libelle_canonique, payload.id_concession)
    invalidate_cache(payload.id_concession)   # binôme
    return item

@app.post("/colonnes", response_model=schemas.ColonneOut)
def api_create_colonne(payload: schemas.ColonneCreatePayload, db: Session = Depends(get_db)):
    colonne = crud.create_colonne_manuel(db, payload.libelle_canonique, payload.id_concession)
    return colonne

# ------------------------------------------------------------------------------
# 5. SUGGESTION SÉMANTIQUE (endpoints binôme enrichis)
# ------------------------------------------------------------------------------
@app.get("/suggest", response_model=schemas.SuggestionResponse)
def suggest_item(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    if result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {"item_id": result["item_id"], "libelle_canonique": item.libelle_canonique if item else None, "confiance": result["score"]}
    return {"item_id": None, "libelle_canonique": None, "confiance": None}

# backend/api/main.py - Remplacer la fonction suggest_with_confirmation

@app.get("/suggest/confirm")
def suggest_with_confirmation(
    description: str, 
    id_concession: int, 
    db: Session = Depends(get_db)
):
    """Version optimisée du matching sémantique avec format standardisé"""
    from backend.semantic.matching.pipeline import semantic_pipeline
    from backend.semantic.matching.engine import DBItem
    
    # Récupération rapide des items
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        or_(models_sql.Item.statut == "actif", models_sql.Item.statut == None)
    ).all()
    
    # Résultat par défaut si aucun item
    default_result = {
        "auto_match": False,
        "item_id": None,
        "libelle": None,
        "confiance": 0.0,
        "needs_confirmation": True,
        "message": "Aucun item dans la base",
        "text_type": "text"
    }
    
    if not items:
        return default_result
    
    db_items = [
        DBItem(
            id_item=i.id_item, 
            libelle_recherche=i.libelle_recherche,
            libelle_canonique=i.libelle_canonique
        ) 
        for i in items
    ]
    
    try:
        # Utilisation du pipeline
        result = semantic_pipeline.process_item(description, db_items, id_concession)
        
        # 🔥 FORMAT STANDARDISÉ pour le frontend
        return {
            "auto_match": result.get("auto_match", False),
            "item_id": result.get("item_id"),
            "libelle": result.get("libelle"),
            "confiance": result.get("confiance", 0.0),
            "needs_confirmation": result.get("needs_confirmation", True),
            "message": result.get("message"),
            "text_type": result.get("text_type", "text"),
            "suggested_item": {
                "item_id": result.get("item_id"),
                "libelle": result.get("libelle"),
                "confiance": result.get("confiance", 0.0)
            } if result.get("item_id") else None
        }
    except Exception as e:
        _log.error(f"Erreur dans suggest_with_confirmation: {e}")
        return {
            "auto_match": False,
            "item_id": None,
            "libelle": None,
            "confiance": 0.0,
            "needs_confirmation": True,
            "message": f"Erreur: {str(e)[:100]}",
            "text_type": "error"
        }


@app.get("/semantic/test")
def test_semantic(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    item = db.query(models_sql.Item).get(result["item_id"]) if result["item_id"] else None
    return {"matched": result["item_id"] is not None, "item_id": result["item_id"], "item_label": item.libelle_canonique if item else None, "score": result["score"], "level": result.get("niveau"), "candidates": result.get("candidates", [])[:3]}

@app.get("/suggest/column", response_model=schemas.SuggestionResponse)
def suggest_column(
    column_name: str, 
    id_concession: int, 
    db: Session = Depends(get_db)
):
    """Suggère une colonne existante correspondant à l'en-tête extrait."""
    colonnes = db.query(models_sql.Colonne).filter(
        models_sql.Colonne.id_concession == id_concession
    ).all()
    
    if not colonnes:
        return {"item_id": None, "libelle_canonique": None, "confiance": None}
    
    from backend.semantic.preprocessing.normalizer import normalize_text
    from rapidfuzz import fuzz
    
    col_norm = normalize_text(column_name)
    best_match = None
    best_score = 0.0
    
    for col in colonnes:
        # 1. Match exact
        if col.libelle_canonique.lower() == column_name.lower():
            return {"item_id": col.id_colonne, "libelle_canonique": col.libelle_canonique, "confiance": 1.0}
        
        # 2. Match normalisé
        if col.libelle_recherche == col_norm:
            return {"item_id": col.id_colonne, "libelle_canonique": col.libelle_canonique, "confiance": 0.95}
        
        # 3. Fuzzy matching
        score = fuzz.token_sort_ratio(col_norm, col.libelle_recherche) / 100.0
        if score > best_score and score >= 0.70:
            best_score = score
            best_match = col
    
    if best_match:
        return {
            "item_id": best_match.id_colonne,
            "libelle_canonique": best_match.libelle_canonique,
            "confiance": round(best_score, 4)
        }
    
    return {"item_id": None, "libelle_canonique": None, "confiance": None}
# ------------------------------------------------------------------------------
# 6. CONCESSIONS
# ------------------------------------------------------------------------------
@app.post("/concessions", response_model=schemas.ConcessionOut)
def create_concession(payload: schemas.ConcessionCreatePayload, db: Session = Depends(get_db)):
    concession = crud.get_or_create_concession(db, payload.nom)
    db.commit()
    return concession

@app.get("/concessions", response_model=List[schemas.ConcessionOut])
def list_concessions(db: Session = Depends(get_db)):
    return db.query(models_sql.Concession).all()

@app.get("/match-concession")
def match_concession(nom_extrait: str, db: Session = Depends(get_db)):
    from rapidfuzz import fuzz
    concessions = db.query(models_sql.Concession).all()
    best_match, best_score = None, 0.0
    nom_norm = normalize_text(nom_extrait)
    for c in concessions:
        score = fuzz.ratio(nom_norm.lower(), c.nom_normalise.lower()) / 100.0
        if score > best_score:
            best_score, best_match = score, c
    if best_score >= 0.8 and best_match:
        return {"matched": True,
                "concession_id": best_match.id_concession,
                "concession_nom": best_match.nom,
                "score": best_score}
    return {"matched": False, "concession_id": None, "concession_nom": None, "score": best_score}


# ------------------------------------------------------------------------------
# Fournisseurs
# ------------------------------------------------------------------------------
@app.get("/fournisseurs", response_model=List[schemas.FournisseurOut])
def get_fournisseurs(db: Session = Depends(get_db)):
    return db.query(models_sql.Fournisseur).all()

@app.post("/fournisseurs", response_model=schemas.FournisseurOut)
def create_fournisseur(payload: schemas.FournisseurCreate, db: Session = Depends(get_db)):
    from backend.semantic.preprocessing.normalizer import normalize_text
    nom_norm = normalize_text(payload.nom)
    db_fourn = models_sql.Fournisseur(
        nom=payload.nom,
        nom_normalise=nom_norm,
        id_concession=payload.id_concession
    )
    db.add(db_fourn)
    db.commit()
    db.refresh(db_fourn)
    return db_fourn

@app.get("/match-supplier")
def match_supplier(nom_extrait: str, db: Session = Depends(get_db)):
    from rapidfuzz import fuzz
    fournisseurs = db.query(models_sql.Fournisseur).all()
    if not fournisseurs:
        return {"matched": False, "fournisseur_id": None, "nom": None, "score": 0}
    from backend.semantic.preprocessing.normalizer import normalize_text
    nom_norm = normalize_text(nom_extrait)
    best_match, best_score = None, 0.0
    for f in fournisseurs:
        score = fuzz.ratio(nom_norm.lower(), f.nom_normalise.lower()) / 100.0
        if score > best_score:
            best_score, best_match = score, f
    if best_score >= 0.8 and best_match:
        return {"matched": True,
                "fournisseur_id": best_match.id_fournisseur,
                "nom": best_match.nom,
                "score": best_score}
    else:
        return {"matched": False,
                "fournisseur_id": None,
                "nom": None,
                "score": best_score}
# ------------------------------------------------------------------------------
# 7. SUPPRESSION
# ------------------------------------------------------------------------------
@app.delete("/facture/{facture_id}")
def delete_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    cid = facture.id_concession
    db.delete(facture)
    db.commit()
    invalidate_cache(cid)
    return {"message": "Facture supprimée"}

@app.delete("/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models_sql.Item).get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item non trouvé")
    cid = item.id_concession
    db.delete(item)
    db.commit()
    invalidate_cache(cid)
    return {"message": f"Item {item_id} supprimé"}

@app.delete("/items")
def api_delete_items(item_ids: List[int], db: Session = Depends(get_db)):
    deleted, refused = crud.delete_items(db, item_ids)
    if deleted > 0:
        invalidate_cache()
    return {"deleted": deleted, "refused": refused}

# ------------------------------------------------------------------------------
# 8. RÉSUMÉ
# ------------------------------------------------------------------------------
@app.post("/facture/{facture_id}/resume", response_model=schemas.ResumeOut)
def get_resume_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    items_dict = {}
    for ligne_info in lignes_data:
        for val in ligne_info["valeurs"]:
            items_dict.setdefault(ligne_info["item"], {})[val["colonne"]] = val["valeur_brute"]
    items_list = [{"description": k, "valeurs": v} for k, v in items_dict.items()]
    concession_nom = facture.concession.nom if facture.concession else ""
    return resume.generate_resume({
        "id_facture": facture.id_facture,
        "date_facture": facture.date_facture.isoformat() if facture.date_facture else None,
        "concession": concession_nom,
        "devise": facture.devise,
        "items": items_list,
        "date_insertion": facture.date_extraction.isoformat() if facture.date_extraction else None,
        "fournisseur": concession_nom,
    })

# ------------------------------------------------------------------------------
# 9. DEBUG
# ------------------------------------------------------------------------------
@app.post("/debug/rebuild")
def rebuild(db: Session = Depends(get_db)):
    invalidate_cache()
    return {"status": "ok"}

# ------------------------------------------------------------------------------
# 10. ANALYSES COMPARATIVES (ta version enrichie)
# ------------------------------------------------------------------------------
class AnalyseRequest(BaseModel):
    id_concession: int
    annee: Optional[int] = None
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    mois: Optional[int] = None
    trimestre: Optional[int] = None

@app.get("/analyses/comparaison")
def get_comparaison_analyses(
    id_concession: int,
    annee: Optional[int] = None,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    mois: Optional[int] = None,
    trimestre: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Analyse enrichie avec KPI, totaux mensuels, comparaison N-1,
    répartition des articles, anomalies, etc.
    """
    concession = db.query(models_sql.Concession).get(id_concession)
    if not concession:
        raise HTTPException(status_code=404, detail="Concession non trouvée")

    # Détermination de la plage de dates
    if date_debut and date_fin:
        plage_debut, plage_fin = date_debut, date_fin
    elif annee and mois:
        plage_debut = date(annee, mois, 1)
        plage_fin = date(annee, 12, 31) if mois == 12 else date(annee, mois + 1, 1) - timedelta(days=1)
    elif annee and trimestre:
        sm = (trimestre - 1) * 3 + 1
        plage_debut = date(annee, sm, 1)
        em = sm + 2
        plage_fin = date(annee, 12, 31) if em == 12 else date(annee, em + 1, 1) - timedelta(days=1)
    elif annee:
        plage_debut, plage_fin = date(annee, 1, 1), date(annee, 12, 31)
    else:
        raise HTTPException(status_code=400, detail="Veuillez spécifier une plage de dates")

    factures = db.query(models_sql.Facture).filter(
        models_sql.Facture.id_concession == id_concession,
        models_sql.Facture.date_facture >= plage_debut,
        models_sql.Facture.date_facture <= plage_fin
    ).all()

    if not factures:
        return {
            "concession": concession.nom,
            "plage": {"debut": str(plage_debut), "fin": str(plage_fin)},
            "nb_factures": 0,
            "kpi": None,
            "totaux_mensuels": [],
            "articles_comparaison": [],
            "anomalies": ["Aucune facture trouvée sur cette période."],
            "repartition_articles": [],
            "comparaison_n1": None
        }

    # KPI
    total_facture = sum(f.total_montant or 0 for f in factures)
    nb_factures = len(factures)
    panier_moyen = total_facture / nb_factures if nb_factures else 0.0

    # Détails des lignes
    details_items = []
    for f in factures:
        for ligne_info in crud.get_fact_data_by_facture(db, f.id_facture):
            item_name = ligne_info["item"]
            valeurs = {v["colonne"]: v["valeur_brute"] for v in ligne_info["valeurs"]}
            montant = None
            # Tri des colonnes par priorité pour trouver le montant
            cols_sorted = sorted(
                valeurs.items(),
                key=lambda x: (
                    2 if any(h in x[0].lower() for h in ['total ttc','montant total','total ht']) else
                    1 if _is_montant_column(x[0]) else 0
                ),
                reverse=True
            )
            for col_name, val in cols_sorted:
                if not _is_montant_column(col_name):
                    continue
                parsed = _parse_montant(val)
                if parsed is not None and parsed > 0:
                    montant = parsed
                    break
            details_items.append({
                "facture_id": f.id_facture,
                "date_facture": f.date_facture.isoformat() if f.date_facture else None,
                "item": item_name,
                "montant": montant,
                "valeurs": valeurs
            })

    # Top article
    articles_count = {}
    articles_total = {}
    for d in details_items:
        item = d["item"]
        articles_count[item] = articles_count.get(item, 0) + 1
        if d["montant"] is not None:
            articles_total[item] = articles_total.get(item, 0) + d["montant"]
    top_article = max(articles_count, key=articles_count.get) if articles_count else None

    kpi = {
        "total_facture": round(total_facture, 2),
        "nb_factures": nb_factures,
        "panier_moyen": round(panier_moyen, 2),
        "top_article": top_article,
        "top_article_occurrences": articles_count.get(top_article, 0) if top_article else 0
    }

    # Totaux mensuels
    totaux_mensuels = [0.0] * 12
    for f in factures:
        if f.date_facture:
            totaux_mensuels[f.date_facture.month - 1] += f.total_montant or 0

    # Comparaison N-1
    annee_prec_debut = date(plage_debut.year - 1, plage_debut.month, plage_debut.day)
    annee_prec_fin = date(plage_fin.year - 1, plage_fin.month, plage_fin.day)
    factures_n1 = db.query(models_sql.Facture).filter(
        models_sql.Facture.id_concession == id_concession,
        models_sql.Facture.date_facture >= annee_prec_debut,
        models_sql.Facture.date_facture <= annee_prec_fin
    ).all()
    totaux_mensuels_n1 = [0.0] * 12
    for f in factures_n1:
        if f.date_facture:
            totaux_mensuels_n1[f.date_facture.month - 1] += f.total_montant or 0
    total_n1 = sum(f.total_montant or 0 for f in factures_n1)
    evolution = ((total_facture - total_n1) / total_n1 * 100) if total_n1 else None
    comparaison_n1 = {
        "totaux_mensuels": totaux_mensuels_n1,
        "total": round(total_n1, 2),
        "evolution_pct": round(evolution, 2) if evolution is not None else None
    }

    # Articles comparaison
    articles_stats = {}
    for d in details_items:
        item = d["item"]
        if item not in articles_stats:
            articles_stats[item] = {"occurrences": 0, "montants": []}
        articles_stats[item]["occurrences"] += 1
        if d["montant"] is not None:
            articles_stats[item]["montants"].append(d["montant"])

    articles_comparaison = []
    for article, stats in articles_stats.items():
        if stats["montants"]:
            articles_comparaison.append({
                "article": article,
                "occurrences": stats["occurrences"],
                "prix_moyen": round(sum(stats["montants"]) / len(stats["montants"]), 2),
                "prix_min": min(stats["montants"]),
                "prix_max": max(stats["montants"])
            })
        else:
            articles_comparaison.append({
                "article": article,
                "occurrences": stats["occurrences"],
                "prix_moyen": None,
                "prix_min": None,
                "prix_max": None
            })

    # Répartition articles (top 5 + autres)
    repartition = []
    sorted_articles = sorted(articles_total.items(), key=lambda x: x[1], reverse=True)
    top5 = sorted_articles[:5]
    for art, montant in top5:
        repartition.append({"article": art, "montant": round(montant, 2)})
    autres = sum(m for _, m in sorted_articles[5:])
    if autres > 0:
        repartition.append({"article": "Autres", "montant": round(autres, 2)})

    # Anomalies
    anomalies = []
    mois_noms = ['Janvier','Février','Mars','Avril','Mai','Juin',
                 'Juillet','Août','Septembre','Octobre','Novembre','Décembre']
    for m in range(12):
        if totaux_mensuels[m] == 0:
            anomalies.append(f"Aucune facture en {mois_noms[m]} {plage_debut.year}")
    for art in articles_comparaison:
        if art["prix_moyen"] and art["prix_min"] and art["prix_max"]:
            if art["prix_min"] > 0 and (art["prix_max"] - art["prix_min"]) / art["prix_min"] > 0.5:
                anomalies.append(
                    f"Variation de prix importante pour '{art['article']}' : "
                    f"min {art['prix_min']} €, max {art['prix_max']} €"
                )
    if not anomalies:
        anomalies.append("Aucune anomalie détectée")

    return {
        "concession": concession.nom,
        "plage": {"debut": str(plage_debut), "fin": str(plage_fin)},
        "nb_factures": nb_factures,
        "kpi": kpi,
        "totaux_mensuels": totaux_mensuels,
        "articles_comparaison": articles_comparaison,
        "anomalies": anomalies,
        "repartition_articles": repartition,
        "comparaison_n1": comparaison_n1
    }

# ------------------------------------------------------------------------------
# 11. EXPORT EXCEL
# ------------------------------------------------------------------------------
@app.get("/analyses/export-excel")
def export_analyse_excel(
    id_concession: int,
    annee: Optional[int] = None,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    mois: Optional[int] = None,
    trimestre: Optional[int] = None,
    db: Session = Depends(get_db)
):
    data = get_comparaison_analyses(
        id_concession=id_concession,
        annee=annee,
        date_debut=date_debut,
        date_fin=date_fin,
        mois=mois,
        trimestre=trimestre,
        db=db
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analyse"
    ws.append(["Analyse pour", data["concession"],
               f"{data['plage']['debut']} à {data['plage']['fin']}"])
    ws.append([])
    if data["kpi"]:
        ws.append(["KPI", ""])
        ws.append(["Total facturé", data["kpi"]["total_facture"]])
        ws.append(["Nombre factures", data["kpi"]["nb_factures"]])
        ws.append(["Panier moyen", data["kpi"]["panier_moyen"]])
    ws.append([])
    ws.append(["Mois", "Total", "Total N-1"])
    for i in range(12):
        ws.append([i+1, data["totaux_mensuels"][i],
                   data.get("comparaison_n1", {}).get("totaux_mensuels", [0]*12)[i]])
    ws.append([])
    ws.append(["Article", "Occurrences", "Prix moyen", "Prix min", "Prix max"])
    for art in data["articles_comparaison"]:
        ws.append([art["article"], art["occurrences"],
                   art["prix_moyen"], art["prix_min"], art["prix_max"]])
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=analyse_doccore.xlsx"}
    )

# ------------------------------------------------------------------------------
# 12. SSE - Upload avec logs temps réel (adapté à ta chaîne)
# ------------------------------------------------------------------------------
extraction_logs = {}

@app.post("/upload/stream")
async def upload_facture_stream(file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    log_queue = queue.Queue()
    extraction_logs[task_id] = log_queue
    content = await file.read()
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.close()

        def extract_with_logs():
            import time as time_module
            t0 = time_module.time()
            try:
                log_queue.put(json.dumps({"step": "upload", "message": "Fichier reçu, démarrage...", "progress": 2}))
                time_module.sleep(0.3)

                log_queue.put(json.dumps({"step": "extraction", "message": "Extraction en cours...", "progress": 15}))
                # Utilise TA chaîne : extract_invoice + process_from_dict
                raw_result = extract_invoice(tmp_path, max_pages=50)
                log_queue.put(json.dumps({"step": "postprocess", "message": "Post‑processing...", "progress": 60}))

                structured = process_from_dict(raw_result)

                # --- Construction d'un dictionnaire sérialisable (identique au /upload) ---
                response_data = {
                    "metadata": {},
                    "columns": [],
                    "items": []
                }
                if hasattr(structured, 'identity'):
                    response_data["metadata"] = {
                        "company": getattr(structured.identity, 'company', None),
                        "concession": getattr(structured.identity, 'concession', None),
                        "date": getattr(structured.identity, 'period', None),
                        "currency": getattr(structured.identity, 'currency', 'USD'),
                        "first_column_name": "Description"
                    }

                headers = []
                if hasattr(structured, 'schema') and hasattr(structured.schema, 'headers_display'):
                    headers = structured.schema.headers_display
                elif hasattr(structured, 'schema') and hasattr(structured.schema, 'columns'):
                    headers = [col.header_raw for col in structured.schema.columns]
                response_data["columns"] = headers

                items = []
                if hasattr(structured, 'sections'):
                    for section in structured.sections:
                        for item in section.items:
                            if item.row_type == "total":
                                continue
                            valeurs = {}
                            semantics = structured.schema.semantics if hasattr(structured.schema, 'semantics') else []
                            for i, sem in enumerate(semantics):
                                if i < len(headers):
                                    header = headers[i]
                                    amt = item.values.get(sem)
                                    if amt:
                                        if amt.value is not None:
                                            valeurs[header] = amt.value
                                        elif amt.raw:
                                            valeurs[header] = amt.raw
                            items.append({
                                "description": item.description,
                                "valeurs": valeurs
                            })
                response_data["items"] = items

                # Comptage pour les logs
                item_count = sum(len(section.items) for section in structured.sections) if hasattr(structured, 'sections') else 0

                total = round(time_module.time() - t0, 1)
                log_queue.put(json.dumps({
                    "step": "done",
                    "message": f"Extraction terminée en {total}s !",
                    "progress": 100,
                    "elapsed": total,
                    "item_count": item_count,
                    "result": response_data
                }))
            except Exception as e:
                log_queue.put(json.dumps({
                    "step": "error",
                    "message": f"Erreur : {str(e)}",
                    "progress": 0,
                    "error": True
                }))
            finally:
                log_queue.put(None)

        threading.Thread(target=extract_with_logs).start()
        return {"task_id": task_id, "filename": file.filename}
    except Exception as e:
        if task_id in extraction_logs:
            del extraction_logs[task_id]
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/upload/logs/{task_id}")
async def stream_logs(task_id: str):
    if task_id not in extraction_logs:
        async def empty():
            yield f"data: {json.dumps({'error': 'Tâche non trouvée'})}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")
    log_queue = extraction_logs[task_id]

    async def event_generator():
        try:
            while True:
                try:
                    msg = log_queue.get(timeout=0.1)
                    if msg is None:
                        yield f"data: {json.dumps({'step': 'complete', 'message': 'Terminé'})}\n\n"
                        break
                    yield f"data: {msg}\n\n"
                    await asyncio.sleep(0.01)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            extraction_logs.pop(task_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )

# ------------------------------------------------------------------------------
# 13. SERVIR LE FRONTEND (React, dossier 'frontend')
# ------------------------------------------------------------------------------
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend")
if os.path.isdir(frontend_path):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


@app.get("/debug/items/{id_concession}")
def debug_items(id_concession: int, db: Session = Depends(get_db)):
    """Debug: voir tous les items d'une concession"""
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession
    ).all()
    
    return {
        "count": len(items),
        "items": [
            {
                "id": i.id_item,
                "libelle": i.libelle_canonique,
                "recherche": i.libelle_recherche
            }
            for i in items
        ]
    }
    

@app.on_event("startup")
async def startup_event():
    """Événement déclenché au démarrage du serveur FastAPI"""
    import logging
    _log = logging.getLogger(__name__)
    _log.info("=" * 50)
    _log.info("🚀 SERVEUR FASTAPI EN DÉMARRAGE")
    _log.info("=" * 50)
    
    # Version synchrone : attend la fin du chargement
    from backend.semantic.embeddings.embedder import _get_model
    from backend.semantic.preprocessing.translator import _load_translator_en_fr, _load_translator_fr_en
    
    _log.info("🔄 Chargement du modèle d'embedding (peut prendre 10-15s)...")
    _get_model()
    _log.info("✅ Modèle embedding chargé")
    
    _log.info("🔄 Chargement des traducteurs...")
    _load_translator_en_fr()
    _load_translator_fr_en()
    _log.info("✅ Traducteurs chargés")
    
    _log.info("✅ TOUS LES MODÈLES CHARGÉS")
    _log.info("=" * 50)
    
    

@app.get("/debug/models/status")
def models_status():
    """Vérifie l'état des modèles chargés"""
    from backend.semantic.embeddings.embedder import _model as emb_model, EMBEDDING_AVAILABLE
    from backend.semantic.preprocessing.translator import _translator_en_fr, _translator_fr_en
    from backend.semantic.matching.pipeline import get_cache_stats
    
    return {
        "embedding": {
            "available": EMBEDDING_AVAILABLE,
            "loaded": emb_model is not None,
        },
        "translators": {
            "en_fr_loaded": _translator_en_fr is not None and _translator_en_fr is not False,
            "fr_en_loaded": _translator_fr_en is not None and _translator_fr_en is not False,
        },
        "cache": get_cache_stats(),
    }
    

@app.get("/debug/items-list")
def debug_items_list(id_concession: int, db: Session = Depends(get_db)):
    """Liste tous les items d'une concession pour debug"""
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        or_(models_sql.Item.statut == "actif", models_sql.Item.statut == None)
    ).all()
    
    return {
        "concession_id": id_concession,
        "count": len(items),
        "items": [
            {
                "id": i.id_item,
                "libelle": i.libelle_canonique,
                "recherche": i.libelle_recherche
            }
            for i in items[:20]
        ]
    }