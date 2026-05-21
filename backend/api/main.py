

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import  StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
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
import logging

# --- Imports métier -----------------------------------------------------------
from backend.api.database import get_db, engine, Base
from backend.api import models_sql, schemas, crud, resume
from backend.extraction.invoice_extraction_bridge import extract_invoice
from backend.postprocess.pipeline import process_from_dict
from backend.semantic.preprocessing.normalizer import normalize_text
from backend.semantic.matching.pipeline import SemanticPipeline
from backend.semantic.matching.engine import DBItem
from backend.semantic.embeddings.indexer import  invalidate_cache

_log = logging.getLogger(__name__)


# ==============================================================================
# HELPERS
# ==============================================================================

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _parse_montant(val_brute: str) -> float | None:
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
    HIGH    = ['montant total', 'total ttc', 'total ht', 'total general',
               'total facture', 'montant ttc', 'montant ht']
    MED     = ['montant', 'total', 'amount', 'prix total', 'sous-total']
    LOW     = ['prix', 'tarif', 'prix unitaire', 'pu', 'unit price', 'valeur', 'cout', 'cost']
    EXCLUDE = ['qte', 'quantite', 'quantity', 'qty', 'ref', 'reference',
               'taux', 'tva', 'remise', 'discount', 'code']
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


def _match_description(description: str, id_concession: int, db: Session) -> dict:
    """Helper commun pour tous les endpoints de matching sémantique."""
    items = db.query(models_sql.Item).filter(
        models_sql.Item.id_concession == id_concession,
        or_(models_sql.Item.statut == "actif", models_sql.Item.statut == None)
    ).all()

    if not items:
        return {"action": "create_new", "reason": "aucun item dans la base"}

    db_items = [
        DBItem(id_item=i.id_item,
               libelle_recherche=i.libelle_recherche,
               libelle_canonique=i.libelle_canonique)
        for i in items
    ]
    pipeline = SemanticPipeline()
    return pipeline.process_item(description, db_items, id_concession)


# ==============================================================================
# INITIALISATION
# ==============================================================================

Base.metadata.create_all(bind=engine, checkfirst=True)
app = FastAPI(title="DocCore Invoice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Préchauffe les modèles au démarrage pour éviter la latence au premier appel."""
    try:
        from backend.semantic.embeddings.embedder import _get_model
        _get_model()
        _log.info("✅ Modèle d'embedding préchargé")
    except Exception as e:
        _log.warning(f"⚠️ Erreur préchargement embedding: {e}")

    try:
        from backend.semantic.preprocessing.translator import _load_translator_en_fr
        _load_translator_en_fr()
        _log.info("✅ Traducteur EN→FR préchargé")
    except Exception as e:
        _log.warning(f"⚠️ Erreur préchargement traducteur: {e}")


# ==============================================================================
# 1. UPLOAD & EXTRACTION
# ==============================================================================

@app.post("/upload", response_model=schemas.ExtractionResponse)
async def upload_facture(file: UploadFile = File(...)):
    content = await file.read()
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()

        _log.debug("Fichier reçu : %s (%d octets)", file.filename, len(content))

        t0 = time.time()
        logging.getLogger("backend.extraction.engine").setLevel(logging.DEBUG)
        raw_result = extract_invoice(tmp_path, max_pages=50)
        _log.debug("[TIMER] extract_invoice: %.2fs", time.time() - t0)

        t1 = time.time()
        structured = process_from_dict(raw_result)
        _log.debug("[TIMER] process_from_dict: %.2fs", time.time() - t1)

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

    # Réponse déjà dict (cas de secours)
    if isinstance(structured, dict):
        return structured

    # Construction de la réponse structurée
    response_data: dict = {"metadata": {}, "columns": [], "items": []}

    if hasattr(structured, 'identity'):
        response_data["metadata"] = {
            "company":          getattr(structured.identity, 'company', None),
            "concession":       getattr(structured.identity, 'concession', None),
            "date":             getattr(structured.identity, 'period', None),
            "currency":         getattr(structured.identity, 'currency', 'USD'),
            "first_column_name": "Description",
        }

    headers = []
    if hasattr(structured, 'schema'):
        if hasattr(structured.schema, 'headers_display'):
            headers = structured.schema.headers_display
        elif hasattr(structured.schema, 'columns'):
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
                        amt = item.values.get(sem)
                        if amt:
                            valeurs[headers[i]] = amt.value if amt.value is not None else amt.raw
                items.append({"description": item.description, "valeurs": valeurs})
    response_data["items"] = items

    return response_data


# ==============================================================================
# 2. CRÉATION D'UNE FACTURE avec pipeline sémantique automatique
# ==============================================================================

@app.post("/facture", response_model=schemas.FactureOut)
def create_facture(
    payload: schemas.FactureWithItems,
    db: Session = Depends(get_db),
    force: bool = False,
):
    # --- Concession -----------------------------------------------------------
    concession_id  = payload.facture.id_concession
    concession_nom = getattr(payload.facture, "nom_concession", None)
    if not concession_id and not concession_nom:
        raise HTTPException(status_code=400, detail="id_concession ou nom_concession requis")
    if not concession_id:
        concession = crud.get_or_create_concession(db, concession_nom)
        concession_id = concession.id_concession
    else:
        concession = db.query(models_sql.Concession).get(concession_id)
        if not concession:
            raise HTTPException(status_code=404, detail="Concession introuvable")
    payload.facture.id_concession = concession_id

    # --- Date -----------------------------------------------------------------
    if payload.facture.date_facture and isinstance(payload.facture.date_facture, str):
        parsed = parse_date(payload.facture.date_facture)
        if parsed is None:
            raise HTTPException(status_code=400, detail="Format de date invalide")
        payload.facture.date_facture = parsed

    # --- Hash de contenu ------------------------------------------------------
    all_items = payload.items_data or []
    if not all_items and payload.sections:
        for section in payload.sections:
            all_items.extend(section.items_data)

    normalized_items = sorted(
        [{"description": i.description.strip(),
          "valeurs": sorted(i.valeurs.items()) if i.valeurs else []}
         for i in all_items],
        key=lambda x: x["description"]
    )
    content_hash = hashlib.sha256(
        json.dumps(normalized_items, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()

    existing = db.query(models_sql.Facture).filter(
        models_sql.Facture.hash_contenu == content_hash
    ).first()
    if existing and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Facture existante (ID: {existing.id_facture}). Utilisez force=true."
        )
    if existing and force:
        db.delete(existing)
        db.commit()

    # --- Création en base -----------------------------------------------------
    db_facture = crud.create_facture(db, payload.facture)
    db_facture.hash_contenu = content_hash
    db.flush()

    # --- Matching sémantique batch --------------------------------------------
    descriptions = [i.description.strip() for i in all_items if i.description.strip()]
    matches = []
    if descriptions:
        try:
            for desc in descriptions:
                result = _match_description(desc, concession_id, db)
                if result["action"] in ("high_confidence", "exact") and result["item_id"]:
                    matches.append({"description": desc, "item_id": result["item_id"],
                                    "confiance": result["score"], "auto_match": "1"})
                elif result["action"] == "needs_validation" and result["item_id"]:
                    matches.append({"description": desc, "item_id": result["item_id"],
                                    "confiance": result["score"], "auto_match": "0"})
        except Exception as e:
            _log.error("Erreur matching batch: %s", e)

    total_articles = len(all_items)
    _log.debug("Nombre d'articles reçus : %d", total_articles)

    # --- Insertion des lignes -------------------------------------------------
    if payload.sections:
        crud.create_lignes_facture(
            db,
            id_facture=db_facture.id_facture,
            id_concession=concession_id,
            matches=matches,
            sections=payload.sections,
        )
    else:
        crud.create_lignes_facture(
            db,
            id_facture=db_facture.id_facture,
            items_data=payload.items_data or [],
            id_concession=concession_id,
            matches=matches,
        )

    invalidate_cache(concession_id)
    return db_facture


# ==============================================================================
# 3. LECTURE DES FACTURES
# ==============================================================================

@app.get("/factures", response_model=List[schemas.FactureOut])
def get_all_factures(db: Session = Depends(get_db)):
    return crud.get_all_factures(db)


@app.get("/facture/{facture_id}")
def get_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    facture_dict = {
        "id_facture":    facture.id_facture,
        "id_concession": facture.id_concession,
        "concession": {
            "id_concession": facture.concession.id_concession if facture.concession else None,
            "nom":           facture.concession.nom            if facture.concession else None,
        },
        "fournisseur":    facture.fournisseur,
        "date_facture":   facture.date_facture.isoformat() if facture.date_facture else None,
        "devise":         facture.devise,
        "total_montant":  facture.total_montant,
        "fichier_source": facture.fichier_source,
        "statut":         facture.statut,
        "valide":         facture.valide,
    }
    data = crud.get_fact_data_by_facture(db, facture_id)
    return {"facture": facture_dict, "data": data}


@app.get("/facture/{facture_id}/details")
def get_facture_details(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    details = [
        {"item": li["item"], "colonne": v["colonne"], "valeur": v["valeur_brute"]}
        for li in lignes_data
        for v in li["valeurs"]
    ]
    return {"id_facture": facture_id, "details": details}


@app.get("/facture/{facture_id}/sections")
def get_facture_sections(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    sections_db = db.query(models_sql.SectionFacture).filter(
        models_sql.SectionFacture.id_facture == facture_id
    ).order_by(models_sql.SectionFacture.section_index).all()

    result = []
    for section in sections_db:
        cols = db.query(models_sql.SectionColonne).filter(
            models_sql.SectionColonne.id_section == section.id_section
        ).order_by(models_sql.SectionColonne.ordre).all()

        headers = []
        for col in cols:
            colonne = db.query(models_sql.Colonne).get(col.id_colonne)
            if colonne:
                headers.append(colonne.libelle_canonique)

        lignes = db.query(models_sql.LigneFacture).filter(
            models_sql.LigneFacture.id_section == section.id_section
        ).all()

        items_data = []
        for ligne in lignes:
            item = db.query(models_sql.Item).get(ligne.id_item)
            valeurs_db = db.query(models_sql.ValeurLigne).filter(
                models_sql.ValeurLigne.id_ligne == ligne.id_ligne
            ).all()
            valeurs_dict = {}
            for v in valeurs_db:
                colonne = db.query(models_sql.Colonne).get(v.id_colonne)
                if colonne and colonne.libelle_canonique in headers:
                    valeurs_dict[colonne.libelle_canonique] = v.valeur_brute
            items_data.append({
                "description": item.libelle_canonique if item else "",
                "valeurs": valeurs_dict,
            })

        result.append({"titre": section.titre, "headers": headers, "items_data": items_data})

    return {"facture_id": facture_id, "sections": result}


# ==============================================================================
# 4. ITEMS & COLONNES
# ==============================================================================

@app.get("/items", response_model=List[schemas.ItemOut])
def get_all_items(db: Session = Depends(get_db), id_concession: Optional[int] = Query(None)):
    if id_concession:
        items = db.query(models_sql.Item).filter(
            models_sql.Item.id_concession == id_concession,
            or_(models_sql.Item.statut == "actif", models_sql.Item.statut == None)
        ).order_by(models_sql.Item.libelle_canonique).all()
    else:
        items = crud.get_all_items(db)

    # Comptage des usages en une seule requête
    counts = (
        dict(
            db.query(models_sql.LigneFacture.id_item, func.count(models_sql.LigneFacture.id_ligne))
            .filter(models_sql.LigneFacture.id_item.in_([i.id_item for i in items]))
            .group_by(models_sql.LigneFacture.id_item).all()
        )
        if items else {}
    )
    for item in items:
        item.usage_count = counts.get(item.id_item, 0)
    return items


@app.get("/colonnes", response_model=List[schemas.ColonneOut])
def get_all_colonnes(db: Session = Depends(get_db), id_concession: Optional[int] = Query(None)):
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
    invalidate_cache(payload.id_concession)
    return item


@app.post("/colonnes", response_model=schemas.ColonneOut)
def api_create_colonne(payload: schemas.ColonneCreatePayload, db: Session = Depends(get_db)):
    return crud.create_colonne_manuel(db, payload.libelle_canonique, payload.id_concession)


# ==============================================================================
# 5. SUGGESTION SÉMANTIQUE
# ==============================================================================

@app.get("/suggest", response_model=schemas.SuggestionResponse)
def suggest_item(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    if result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {
            "item_id":          result["item_id"],
            "libelle_canonique": item.libelle_canonique if item else None,
            "confiance":         result["score"],
        }
    return {"item_id": None, "libelle_canonique": None, "confiance": None}


@app.get("/suggest/confirm")
def suggest_with_confirmation(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    if result["action"] in ("high_confidence", "exact") and result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {
            "auto_match":       True,
            "item_id":          result["item_id"],
            "libelle":          item.libelle_canonique if item else "",
            "confiance":        result["score"],
            "needs_confirmation": False,
        }
    if result["action"] == "needs_validation" and result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {
            "auto_match":       False,
            "suggested_item":   {"item_id": result["item_id"],
                                 "libelle": item.libelle_canonique if item else "",
                                 "confiance": result["score"]},
            "candidates":       result.get("candidates", [])[:5],
            "needs_confirmation": True,
            "message": f"Item similaire: '{item.libelle_canonique if item else '?'}' ({result['score']:.0%})",
        }
    if result["action"] == "skip":
        return {
            "auto_match":       False,
            "suggested_item":   None,
            "candidates":       [],
            "needs_confirmation": False,
            "message": f"Texte ignoré: {result.get('reason', '')}",
        }
    return {
        "auto_match":       False,
        "suggested_item":   None,
        "candidates":       result.get("candidates", [])[:5],
        "needs_confirmation": False,
        "message": "Aucun item similaire trouvé.",
    }


@app.get("/semantic/test")
def test_semantic(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    item = db.query(models_sql.Item).get(result["item_id"]) if result["item_id"] else None
    return {
        "matched":    result["item_id"] is not None,
        "item_id":    result["item_id"],
        "item_label": item.libelle_canonique if item else None,
        "score":      result["score"],
        "level":      result.get("niveau"),
        "candidates": result.get("candidates", [])[:3],
    }


# ==============================================================================
# 6. CONCESSIONS
# ==============================================================================

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
        return {"matched": True, "concession_id": best_match.id_concession,
                "concession_nom": best_match.nom, "score": best_score}
    return {"matched": False, "concession_id": None, "concession_nom": None, "score": best_score}


# ==============================================================================
# 7. FOURNISSEURS
# ==============================================================================

@app.get("/fournisseurs", response_model=List[schemas.FournisseurOut])
def get_fournisseurs(db: Session = Depends(get_db)):
    return db.query(models_sql.Fournisseur).all()


@app.post("/fournisseurs", response_model=schemas.FournisseurOut)
def create_fournisseur(payload: schemas.FournisseurCreate, db: Session = Depends(get_db)):
    nom_norm = normalize_text(payload.nom)
    db_fourn = models_sql.Fournisseur(
        nom=payload.nom,
        nom_normalise=nom_norm,
        id_concession=payload.id_concession,
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
    nom_norm = normalize_text(nom_extrait)
    best_match, best_score = None, 0.0
    for f in fournisseurs:
        score = fuzz.ratio(nom_norm.lower(), f.nom_normalise.lower()) / 100.0
        if score > best_score:
            best_score, best_match = score, f
    if best_score >= 0.8 and best_match:
        return {"matched": True, "fournisseur_id": best_match.id_fournisseur,
                "nom": best_match.nom, "score": best_score}
    return {"matched": False, "fournisseur_id": None, "nom": None, "score": best_score}


# ==============================================================================
# 8. SUPPRESSION
# ==============================================================================

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


# ==============================================================================
# 9. RÉSUMÉ
# ==============================================================================

@app.post("/facture/{facture_id}/resume", response_model=schemas.ResumeOut)
def get_resume_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    items_dict: dict = {}
    for ligne_info in lignes_data:
        for val in ligne_info["valeurs"]:
            items_dict.setdefault(ligne_info["item"], {})[val["colonne"]] = val["valeur_brute"]
    items_list = [{"description": k, "valeurs": v} for k, v in items_dict.items()]

    concession_nom = facture.concession.nom if facture.concession else "Non spécifiée"
    fournisseur    = facture.fournisseur    if facture.fournisseur else "Non spécifié"

    return resume.generate_resume({
        "id_facture":    facture.id_facture,
        "date_facture":  facture.date_facture.isoformat() if facture.date_facture else None,
        "fournisseur":   fournisseur,
        "concession":    concession_nom,
        "concession_nom": concession_nom,
        "devise":        facture.devise,
        "items":         items_list,
        "date_insertion": facture.date_extraction.isoformat() if facture.date_extraction else None,
    })


# ==============================================================================
# 10. DEBUG
# ==============================================================================

@app.post("/debug/rebuild")
def rebuild(db: Session = Depends(get_db)):
    invalidate_cache()
    return {"status": "ok"}


# ==============================================================================
# 11. ANALYSES COMPARATIVES
# ==============================================================================

class AnalyseRequest(BaseModel):
    id_concession: int
    annee:         Optional[int]  = None
    date_debut:    Optional[date] = None
    date_fin:      Optional[date] = None
    mois:          Optional[int]  = None
    trimestre:     Optional[int]  = None


@app.get("/analyses/comparaison")
def get_comparaison_analyses(
    id_concession: int,
    annee:         Optional[int]  = None,
    date_debut:    Optional[date] = None,
    date_fin:      Optional[date] = None,
    mois:          Optional[int]  = None,
    trimestre:     Optional[int]  = None,
    db: Session = Depends(get_db),
):
    concession = db.query(models_sql.Concession).get(id_concession)
    if not concession:
        raise HTTPException(status_code=404, detail="Concession non trouvée")

    # Plage de dates
    if date_debut and date_fin:
        plage_debut, plage_fin = date_debut, date_fin
    elif annee and mois:
        plage_debut = date(annee, mois, 1)
        plage_fin   = date(annee, 12, 31) if mois == 12 else date(annee, mois + 1, 1) - timedelta(days=1)
    elif annee and trimestre:
        sm = (trimestre - 1) * 3 + 1
        em = sm + 2
        plage_debut = date(annee, sm, 1)
        plage_fin   = date(annee, 12, 31) if em == 12 else date(annee, em + 1, 1) - timedelta(days=1)
    elif annee:
        plage_debut, plage_fin = date(annee, 1, 1), date(annee, 12, 31)
    else:
        raise HTTPException(status_code=400, detail="Veuillez spécifier une plage de dates")

    factures = db.query(models_sql.Facture).filter(
        models_sql.Facture.id_concession == id_concession,
        models_sql.Facture.date_facture  >= plage_debut,
        models_sql.Facture.date_facture  <= plage_fin,
    ).all()

    MOIS_NOMS = ['Janvier','Février','Mars','Avril','Mai','Juin',
                 'Juillet','Août','Septembre','Octobre','Novembre','Décembre']

    if not factures:
        return {
            "concession":        concession.nom,
            "plage":             {"debut": str(plage_debut), "fin": str(plage_fin)},
            "nb_factures":       0,
            "kpi":               {"total_facture": 0, "nb_factures": 0,
                                  "panier_moyen": 0, "top_article": None,
                                  "top_article_occurrences": 0},
            "totaux_mensuels":   [0] * 12,
            "articles_comparaison": [],
            "anomalies":         ["Aucune facture trouvée sur cette période."],
            "repartition_articles": [],
            "comparaison_n1":    None,
            "evolution_globale": 0,
            "meilleur_mois":     {"mois": "—", "montant": 0},
            "mois_faible":       {"mois": "—", "montant": 0},
        }

    total_facture = sum(f.total_montant or 0 for f in factures)
    nb_factures   = len(factures)
    panier_moyen  = total_facture / nb_factures if nb_factures else 0.0

    # Totaux mensuels
    totaux_mensuels = [0.0] * 12
    for f in factures:
        if f.date_facture:
            totaux_mensuels[f.date_facture.month - 1] += f.total_montant or 0

    # Meilleur / plus faible mois
    max_val = max(totaux_mensuels)
    actifs  = [m for m in totaux_mensuels if m > 0]
    min_val = min(actifs) if actifs else 0
    meilleur_mois = {"mois": MOIS_NOMS[totaux_mensuels.index(max_val)], "montant": max_val}
    mois_faible   = {"mois": MOIS_NOMS[totaux_mensuels.index(min_val)], "montant": min_val} if actifs else {"mois": "—", "montant": 0}

    # Comparaison N-1
    annee_prec = plage_debut.year - 1
    comparaison_n1   = None
    evolution_globale = 0.0
    if annee_prec >= 2000:
        try:
            plage_prec_debut = date(annee_prec, plage_debut.month, plage_debut.day)
            plage_prec_fin   = date(annee_prec, plage_fin.month,   plage_fin.day)
        except ValueError:
            plage_prec_debut = date(annee_prec, 1, 1)
            plage_prec_fin   = date(annee_prec, 12, 31)
        factures_n1     = db.query(models_sql.Facture).filter(
            models_sql.Facture.id_concession == id_concession,
            models_sql.Facture.date_facture  >= plage_prec_debut,
            models_sql.Facture.date_facture  <= plage_prec_fin,
        ).all()
        total_n1 = sum(f.total_montant or 0 for f in factures_n1)
        totaux_n1 = [0.0] * 12
        for f in factures_n1:
            if f.date_facture:
                totaux_n1[f.date_facture.month - 1] += f.total_montant or 0
        evolution_globale = ((total_facture - total_n1) / total_n1 * 100) if total_n1 else 0.0
        comparaison_n1 = {
            "totaux_mensuels": totaux_n1,
            "total":           round(total_n1, 2),
            "evolution_pct":   round(evolution_globale, 2),
        }

    # Détails lignes pour articles
    details_items = []
    for f in factures:
        for ligne_info in crud.get_fact_data_by_facture(db, f.id_facture):
            item_name = ligne_info["item"]
            valeurs   = {v["colonne"]: v["valeur_brute"] for v in ligne_info["valeurs"]}
            # Montant : priorité aux colonnes high > medium > low
            montant = None
            cols_sorted = sorted(
                valeurs.items(),
                key=lambda x: (
                    2 if any(h in x[0].lower() for h in ['total ttc', 'montant total', 'total ht']) else
                    1 if _is_montant_column(x[0]) else 0
                ),
                reverse=True,
            )
            for col_name, val in cols_sorted:
                if not _is_montant_column(col_name):
                    continue
                parsed = _parse_montant(val)
                if parsed is not None and parsed > 0:
                    montant = parsed
                    break
            details_items.append({
                "facture_id":  f.id_facture,
                "date_facture": f.date_facture.isoformat() if f.date_facture else None,
                "item":        item_name,
                "montant":     montant,
                "valeurs":     valeurs,
            })

    # Stats par article
    articles_stats: dict = {}
    for d in details_items:
        item = d["item"]
        if item not in articles_stats:
            articles_stats[item] = {"occurrences": 0, "montants": []}
        articles_stats[item]["occurrences"] += 1
        if d["montant"] is not None:
            articles_stats[item]["montants"].append(d["montant"])

    articles_comparaison = []
    articles_total: dict = {}
    for article, stats in articles_stats.items():
        montants = stats["montants"]
        if montants:
            pm = sum(montants) / len(montants)
            articles_comparaison.append({
                "article":    article,
                "occurrences": stats["occurrences"],
                "prix_moyen": round(pm, 2),
                "prix_min":   min(montants),
                "prix_max":   max(montants),
            })
            articles_total[article] = sum(montants)
        else:
            articles_comparaison.append({
                "article":    article,
                "occurrences": stats["occurrences"],
                "prix_moyen": None,
                "prix_min":   None,
                "prix_max":   None,
            })

    top_article = max(articles_stats, key=lambda a: articles_stats[a]["occurrences"]) if articles_stats else None

    # Répartition top 5 + autres
    sorted_arts = sorted(articles_total.items(), key=lambda x: x[1], reverse=True)
    repartition = [{"article": a, "montant": round(m, 2)} for a, m in sorted_arts[:5]]
    autres = sum(m for _, m in sorted_arts[5:])
    if autres > 0:
        repartition.append({"article": "Autres", "montant": round(autres, 2)})

    # Anomalies
    anomalies = []
    for m in range(12):
        if totaux_mensuels[m] == 0:
            anomalies.append(f"Aucune facture en {MOIS_NOMS[m]} {plage_debut.year}")
    for art in articles_comparaison:
        if art["prix_moyen"] and art["prix_min"] and art["prix_max"] and art["prix_min"] > 0:
            if (art["prix_max"] - art["prix_min"]) / art["prix_min"] > 0.5:
                anomalies.append(
                    f"Variation de prix importante pour '{art['article']}' : "
                    f"min {art['prix_min']} €, max {art['prix_max']} €"
                )
    if panier_moyen > 0:
        anormales = [f for f in factures if (f.total_montant or 0) > panier_moyen * 3]
        if anormales:
            anomalies.append(f"{len(anormales)} facture(s) avec un montant anormalement élevé")
    if not anomalies:
        anomalies.append("Aucune anomalie détectée")

    return {
        "concession":        concession.nom,
        "plage":             {"debut": str(plage_debut), "fin": str(plage_fin)},
        "nb_factures":       nb_factures,
        "kpi": {
            "total_facture":          round(total_facture, 2),
            "nb_factures":            nb_factures,
            "panier_moyen":           round(panier_moyen, 2),
            "top_article":            top_article,
            "top_article_occurrences": articles_stats[top_article]["occurrences"] if top_article else 0,
        },
        "totaux_mensuels":   totaux_mensuels,
        "articles_comparaison": articles_comparaison,
        "anomalies":         anomalies,
        "repartition_articles": repartition,
        "comparaison_n1":    comparaison_n1,
        "evolution_globale": round(evolution_globale, 2),
        "meilleur_mois":     meilleur_mois,
        "mois_faible":       mois_faible,
    }


# ==============================================================================
# 12. EXPORT EXCEL
# ==============================================================================

@app.get("/analyses/export-excel")
def export_analyse_excel(
    id_concession: int,
    annee:         Optional[int]  = None,
    date_debut:    Optional[date] = None,
    date_fin:      Optional[date] = None,
    mois:          Optional[int]  = None,
    trimestre:     Optional[int]  = None,
    db: Session = Depends(get_db),
):
    data = get_comparaison_analyses(
        id_concession=id_concession, annee=annee,
        date_debut=date_debut, date_fin=date_fin,
        mois=mois, trimestre=trimestre, db=db,
    )

    MOIS_NOMS = ['Janvier','Février','Mars','Avril','Mai','Juin',
                 'Juillet','Août','Septembre','Octobre','Novembre','Décembre']
    wb = openpyxl.Workbook()

    # Feuille 1 – Résumé
    ws = wb.active
    ws.title = "Résumé"
    ws.append(["Analyse pour", data["concession"],
               f"{data['plage']['debut']} à {data['plage']['fin']}"])
    ws.append([])
    ws.append(["Indicateur", "Valeur"])
    ws.append(["Total facturé",     data["kpi"]["total_facture"]])
    ws.append(["Nombre de factures", data["kpi"]["nb_factures"]])
    ws.append(["Panier moyen",       data["kpi"]["panier_moyen"]])
    ws.append(["Top article",        data["kpi"]["top_article"] or "—"])
    if data.get("evolution_globale") is not None:
        ws.append(["Évolution vs N-1", f"{data['evolution_globale']:.1f}%"])
    ws.append([])
    ws.append(["Meilleur mois", f"{data['meilleur_mois']['mois']}: {data['meilleur_mois']['montant']:.2f} €"])
    ws.append(["Mois le plus faible", f"{data['mois_faible']['mois']}: {data['mois_faible']['montant']:.2f} €"])

    # Feuille 2 – Évolution mensuelle
    ws2 = wb.create_sheet("Évolution mensuelle")
    ws2.append(["Mois", "Montant (€)", "Montant N-1 (€)"])
    n1_totaux = data.get("comparaison_n1", {}).get("totaux_mensuels", [0] * 12) if data.get("comparaison_n1") else [0] * 12
    for i, montant in enumerate(data["totaux_mensuels"]):
        ws2.append([MOIS_NOMS[i], montant, n1_totaux[i]])

    # Feuille 3 – Articles
    ws3 = wb.create_sheet("Articles")
    ws3.append(["Article", "Occurrences", "Prix moyen (€)", "Prix min (€)", "Prix max (€)"])
    for art in data["articles_comparaison"]:
        ws3.append([art["article"], art["occurrences"],
                    art["prix_moyen"], art["prix_min"], art["prix_max"]])

    # Feuille 4 – Répartition
    ws4 = wb.create_sheet("Répartition")
    ws4.append(["Article", "Montant (€)", "Part (%)"])
    total = data["kpi"]["total_facture"]
    for art in data["repartition_articles"]:
        part = (art["montant"] / total * 100) if total > 0 else 0
        ws4.append([art["article"], art["montant"], f"{part:.1f}%"])

    # Feuille 5 – Anomalies
    ws5 = wb.create_sheet("Anomalies")
    ws5.append(["Anomalie"])
    for a in data["anomalies"]:
        if "aucune" not in a.lower():
            ws5.append([a])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"analyse_{data['concession']}_{annee or 'periode'}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==============================================================================
# 13. SSE – Upload avec logs temps réel
# ==============================================================================

extraction_logs: dict = {}


@app.post("/upload/stream")
async def upload_facture_stream(file: UploadFile = File(...)):
    task_id   = str(uuid.uuid4())
    log_queue = queue.Queue()
    extraction_logs[task_id] = log_queue

    content  = await file.read()
    suffix   = Path(file.filename).suffix
    tmp      = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.close()

        def extract_with_logs():
            import time as T
            try:
                t0 = T.time()

                def put(step, msg, pct, **kw):
                    log_queue.put(json.dumps(
                        {"step": step, "message": msg, "progress": pct,
                         "elapsed": round(T.time() - t0, 1), **kw}
                    ))

                put("upload",    "Fichier reçu, démarrage...",       2)
                T.sleep(0.3)
                put("preprocess","Analyse qualité image...",          5)
                T.sleep(0.3)
                put("language",  "Détection langue...",               8)
                T.sleep(0.3)
                put("ocr_select","Sélection moteur OCR...",          12)

                ocr_start   = T.time()
                ocr_running = True
                last_pct    = [12.0]

                def _ocr_ticker():
                    while ocr_running:
                        T.sleep(1)
                        if not ocr_running:
                            break
                        elapsed = T.time() - t0
                        p = min(12 + (T.time() - ocr_start) / 180 * 48, 60)
                        last_pct[0] = max(last_pct[0], p)
                        log_queue.put(json.dumps({
                            "step": "ocr", "message": "OCR en cours...",
                            "progress": round(last_pct[0], 1),
                            "elapsed": round(elapsed, 1),
                            "ocr_elapsed": round(T.time() - ocr_start, 1),
                        }))

                threading.Thread(target=_ocr_ticker, daemon=True).start()
                raw_result  = extract_invoice(tmp_path, max_pages=50)
                ocr_running = False
                ocr_total   = round(T.time() - ocr_start, 1)

                put("ocr_done",    f"OCR terminé en {ocr_total}s",  65, ocr_elapsed=ocr_total)
                T.sleep(0.3)
                put("postprocess", "Post-processing...",             78)
                structured = process_from_dict(raw_result)
                T.sleep(0.3)
                put("correct",     "Correction intelligente...",     92)

                # Construire le dict résultat
                response_data: dict = {"metadata": {}, "columns": [], "items": []}
                if hasattr(structured, 'identity'):
                    response_data["metadata"] = {
                        "company":    getattr(structured.identity, 'company',    None),
                        "concession": getattr(structured.identity, 'concession', None),
                        "date":       getattr(structured.identity, 'period',     None),
                        "currency":   getattr(structured.identity, 'currency',   'USD'),
                        "first_column_name": "Description",
                    }
                headers = []
                if hasattr(structured, 'schema'):
                    if hasattr(structured.schema, 'headers_display'):
                        headers = structured.schema.headers_display
                    elif hasattr(structured.schema, 'columns'):
                        headers = [col.header_raw for col in structured.schema.columns]
                response_data["columns"] = headers
                items = []
                if hasattr(structured, 'sections'):
                    for section in structured.sections:
                        for item in section.items:
                            if item.row_type == "total":
                                continue
                            valeurs   = {}
                            semantics = structured.schema.semantics if hasattr(structured.schema, 'semantics') else []
                            for i, sem in enumerate(semantics):
                                if i < len(headers):
                                    amt = item.values.get(sem)
                                    if amt:
                                        valeurs[headers[i]] = amt.value if amt.value is not None else amt.raw
                            items.append({"description": item.description, "valeurs": valeurs})
                response_data["items"] = items
                item_count = len(items)

                total = round(T.time() - t0, 1)
                log_queue.put(json.dumps({
                    "step":        "done",
                    "message":     f"Extraction terminée en {total}s ! {item_count} articles",
                    "progress":    100,
                    "elapsed":     total,
                    "ocr_elapsed": ocr_total,
                    "item_count":  item_count,
                    "result":      response_data,
                }))

            except Exception as e:
                log_queue.put(json.dumps({
                    "step": "error", "message": f"Erreur : {str(e)}",
                    "progress": 0, "error": True,
                }))
            finally:
                log_queue.put(None)

        threading.Thread(target=extract_with_logs).start()
        return {"task_id": task_id, "filename": file.filename}

    except Exception as e:
        extraction_logs.pop(task_id, None)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/upload/logs/{task_id}")
async def stream_logs(task_id: str):
    if task_id not in extraction_logs:
        async def _empty():
            yield f"data: {json.dumps({'error': 'Tâche non trouvée'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

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
        headers={
            "Cache-Control":    "no-cache",
            "Connection":       "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



for _fp in ("frontend-doc", "frontend"):
    _frontend_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", _fp
    )
    if os.path.isdir(_frontend_path):
        app.mount("/", StaticFiles(directory=_frontend_path, html=True), name="frontend")
        break