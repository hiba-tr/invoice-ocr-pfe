"""
DocCore Invoice API — Version fusionnée
Chaîne : extraction (backend.extraction.main) → postprocess → stockage avec matching sémantique
"""
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import  StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
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

from backend.api.database import get_db, engine, Base
from backend.api import models_sql, schemas, crud, resume
from backend.extraction.invoice_extraction_bridge import extract_invoice
from backend.postprocess.pipeline import process_from_dict
from backend.semantic.preprocessing.normalizer import normalize_text
from backend.semantic.matching.pipeline import SemanticPipeline
from backend.semantic.matching.engine import MatchingEngine, DBItem
from backend.semantic.embeddings.indexer import get_or_build_index, invalidate_cache
from backend.semantic.embeddings.embedder import EMBEDDING_AVAILABLE
_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# INITIALISATION
# ═══════════════════════════════════════════════════════════════

Base.metadata.create_all(bind=engine)
app = FastAPI(title="DocCore Invoice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# 1. UPLOAD & EXTRACTION
# ═══════════════════════════════════════════════════════════════

@app.post("/upload", response_model=schemas.ExtractionResponse)
async def upload_facture(file: UploadFile = File(...)):
    content = await file.read()
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.close()
        raw_result = extract_invoice(tmp_path, max_pages=10)
        structured = process_from_dict(raw_result)
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

    if isinstance(structured, dict):
        return {"invoices": structured}
    
    # ✅ Construction correcte de la réponse
    response_data = {
        "metadata": {},
        "columns": [],
        "items": []
    }
    
    # Extraire les métadonnées
    if hasattr(structured, 'identity'):
        response_data["metadata"] = {
            "company": getattr(structured.identity, 'company', None),
            "concession": getattr(structured.identity, 'concession', None),
            "date": getattr(structured.identity, 'period', None),
            "currency": getattr(structured.identity, 'currency', 'USD'),
            "first_column_name": "Description"
        }
    
    # Extraire les colonnes (headers)
    headers = []
    if hasattr(structured, 'schema') and hasattr(structured.schema, 'headers_display'):
        headers = structured.schema.headers_display
    elif hasattr(structured, 'schema') and hasattr(structured.schema, 'columns'):
        headers = [col.header_raw for col in structured.schema.columns]
    response_data["columns"] = headers
    
    # Extraire les items avec le bon mapping
    items = []
    if hasattr(structured, 'sections'):
        for section in structured.sections:
            for item in section.items:
                if item.row_type == "total":
                    continue
                
                # Construire les valeurs avec le header comme clé
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
    
    return response_data


# ═══════════════════════════════════════════════════════════════
# 2. CREATION FACTURE avec pipeline sémantique automatique
# ═══════════════════════════════════════════════════════════════

@app.post("/facture", response_model=schemas.FactureOut)
def create_facture(payload: schemas.FactureWithItems, db: Session = Depends(get_db), force: bool = False):
    # Gestion concession
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

    # Date
    if payload.facture.date_facture and isinstance(payload.facture.date_facture, str):
        parsed = parse_date(payload.facture.date_facture)
        if parsed is None:
            raise HTTPException(status_code=400, detail="Format de date invalide")
        payload.facture.date_facture = parsed

    # Hash de contenu
    all_items = []
    if payload.items_data:
        all_items = payload.items_data
    elif payload.sections:
        for section in payload.sections:
            all_items.extend(section.items_data)

    normalized_items = []
    for item in all_items:
        desc = item.description.strip()
        sorted_vals = sorted(item.valeurs.items()) if item.valeurs else []
        normalized_items.append({"description": desc, "valeurs": sorted_vals})
    normalized_items.sort(key=lambda x: x["description"])
    content_string = json.dumps(normalized_items, ensure_ascii=False, sort_keys=True)
    content_hash = hashlib.sha256(content_string.encode("utf-8")).hexdigest()

    existing = db.query(models_sql.Facture).filter(models_sql.Facture.hash_contenu == content_hash).first()
    if existing and not force:
        raise HTTPException(status_code=409, detail=f"Facture existante (ID: {existing.id_facture}). Utilisez force=true.")
    if existing and force:
        db.delete(existing)
        db.commit()

    db_facture = crud.create_facture(db, payload.facture)
    db_facture.hash_contenu = content_hash
    db.flush()

    # Matching sémantique
    descriptions = []
    if payload.items_data:
        descriptions = [item.description.strip() for item in payload.items_data if item.description.strip()]
    elif payload.sections:
        for section in payload.sections:
            for item in section.items_data:
                desc = item.description.strip()
                if desc:
                    descriptions.append(desc)

    matches = []
    if descriptions:
        try:
            for desc in descriptions:
                result = _match_description(desc, concession_id, db)
                if result["action"] in ("high_confidence", "exact") and result["item_id"]:
                    matches.append({"description": desc, "item_id": result["item_id"], "confiance": result["score"], "auto_match": "1"})
                elif result["action"] == "needs_validation" and result["item_id"]:
                    matches.append({"description": desc, "item_id": result["item_id"], "confiance": result["score"], "auto_match": "0"})
        except Exception as e:
            _log.error(f"Erreur matching batch: {e}")

    # Insertion des lignes
    if payload.sections:
        crud.create_lignes_facture(db, id_facture=db_facture.id_facture, id_concession=concession_id, matches=matches, sections=payload.sections)
    else:
        crud.create_lignes_facture(db, id_facture=db_facture.id_facture, items_data=payload.items_data or [], id_concession=concession_id, matches=matches)

    invalidate_cache(concession_id)
    return db_facture


# ═══════════════════════════════════════════════════════════════
# 3. LECTURE FACTURES
# ═══════════════════════════════════════════════════════════════

@app.get("/factures", response_model=List[schemas.FactureOut])
def get_all_factures(db: Session = Depends(get_db)):
    return crud.get_all_factures(db)


@app.get("/facture/{facture_id}")
def get_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")
    data = crud.get_fact_data_by_facture(db, facture_id)
    return {"facture": facture, "data": data}


@app.get("/facture/{facture_id}/details")
def get_facture_details(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")
    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    details = []
    for ligne_info in lignes_data:
        for val in ligne_info["valeurs"]:
            details.append({"item": ligne_info["item"], "colonne": val["colonne"], "valeur": val["valeur_brute"]})
    return {"id_facture": facture_id, "details": details}


@app.get("/facture/{facture_id}/sections")
def get_facture_sections(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")

    sections_db = db.query(models_sql.SectionFacture).filter(
        models_sql.SectionFacture.id_facture == facture_id
    ).order_by(models_sql.SectionFacture.section_index).all()

    result = []
    for section in sections_db:
        cols = db.query(models_sql.SectionColonne).filter(
            models_sql.SectionColonne.id_section == section.id_section
        ).order_by(models_sql.SectionColonne.ordre).all()
        headers = [db.query(models_sql.Colonne).get(col.id_colonne).libelle_canonique for col in cols if db.query(models_sql.Colonne).get(col.id_colonne)]

        lignes = db.query(models_sql.LigneFacture).filter(models_sql.LigneFacture.id_section == section.id_section).all()
        items_data = []
        for ligne in lignes:
            item = db.query(models_sql.Item).get(ligne.id_item)
            valeurs = db.query(models_sql.ValeurLigne).filter(models_sql.ValeurLigne.id_ligne == ligne.id_ligne).all()
            valeurs_dict = {}
            for v in valeurs:
                colonne = db.query(models_sql.Colonne).get(v.id_colonne)
                if colonne and colonne.libelle_canonique in headers:
                    valeurs_dict[colonne.libelle_canonique] = v.valeur_brute
            items_data.append({"description": item.libelle_canonique if item else "", "valeurs": valeurs_dict})
        result.append({"titre": section.titre, "headers": headers, "items_data": items_data})

    return {"facture_id": facture_id, "sections": result}


# ═══════════════════════════════════════════════════════════════
# 4. ITEMS & COLONNES
# ═══════════════════════════════════════════════════════════════

@app.get("/items", response_model=List[schemas.ItemOut])
def get_all_items(db: Session = Depends(get_db), id_concession: Optional[int] = Query(None)):
    if id_concession:
        items = db.query(models_sql.Item).filter(
            models_sql.Item.id_concession == id_concession,
            models_sql.Item.statut == "actif"
        ).order_by(models_sql.Item.libelle_canonique).all()
    else:
        items = crud.get_all_items(db)

    from sqlalchemy import func
    counts = dict(
        db.query(models_sql.LigneFacture.id_item, func.count(models_sql.LigneFacture.id_ligne))
        .filter(models_sql.LigneFacture.id_item.in_([i.id_item for i in items]))
        .group_by(models_sql.LigneFacture.id_item).all()
    ) if items else {}

    for item in items:
        item.usage_count = counts.get(item.id_item, 0)
    return items


@app.get("/colonnes", response_model=List[schemas.ColonneOut])
def get_all_colonnes(db: Session = Depends(get_db), id_concession: Optional[int] = Query(None)):
    if id_concession:
        colonnes = db.query(models_sql.Colonne).filter(models_sql.Colonne.id_concession == id_concession).all()
    else:
        colonnes = crud.get_all_colonnes(db)
    for colonne in colonnes:
        colonne.usage_count = db.query(models_sql.ValeurLigne).filter(models_sql.ValeurLigne.id_colonne == colonne.id_colonne).count()
    return colonnes


@app.post("/items", response_model=schemas.ItemOut)
def api_create_item(payload: schemas.ItemCreatePayload, db: Session = Depends(get_db)):
    item = crud.create_item_manuel(db, payload.libelle_canonique, payload.id_concession)
    invalidate_cache(payload.id_concession)
    return item


@app.post("/colonnes", response_model=schemas.ColonneOut)
def api_create_colonne(payload: schemas.ColonneCreatePayload, db: Session = Depends(get_db)):
    return crud.create_colonne_manuel(db, payload.libelle_canonique, payload.id_concession)


# ═══════════════════════════════════════════════════════════════
# 5. SUGGESTION SEMANTIQUE
# ═══════════════════════════════════════════════════════════════

@app.get("/suggest", response_model=schemas.SuggestionResponse)
def suggest_item(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    if result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {"item_id": result["item_id"], "libelle_canonique": item.libelle_canonique if item else None, "confiance": result["score"]}
    return {"item_id": None, "libelle_canonique": None, "confiance": None}


@app.get("/suggest/confirm")
def suggest_with_confirmation(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    if result["action"] in ("high_confidence", "exact") and result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {"auto_match": True, "item_id": result["item_id"], "libelle": item.libelle_canonique if item else "", "confiance": result["score"], "needs_confirmation": False}
    elif result["action"] == "needs_validation" and result["item_id"]:
        item = db.query(models_sql.Item).get(result["item_id"])
        return {"auto_match": False, "suggested_item": {"item_id": result["item_id"], "libelle": item.libelle_canonique if item else "", "confiance": result["score"]}, "candidates": result.get("candidates", [])[:5], "needs_confirmation": True, "message": f"Item similaire: '{item.libelle_canonique if item else '?'}' ({result['score']:.0%})"}
    elif result["action"] == "skip":
        return {"auto_match": False, "suggested_item": None, "candidates": [], "needs_confirmation": False, "message": f"Texte ignoré: {result.get('reason', '')}"}
    return {"auto_match": False, "suggested_item": None, "candidates": result.get("candidates", [])[:5], "needs_confirmation": False, "message": "Aucun item similaire trouvé."}


@app.get("/semantic/test")
def test_semantic(description: str, id_concession: int, db: Session = Depends(get_db)):
    result = _match_description(description, id_concession, db)
    item = db.query(models_sql.Item).get(result["item_id"]) if result["item_id"] else None
    return {"matched": result["item_id"] is not None, "item_id": result["item_id"], "item_label": item.libelle_canonique if item else None, "score": result["score"], "level": result.get("niveau"), "candidates": result.get("candidates", [])[:3]}


# ═══════════════════════════════════════════════════════════════
# 6. CONCESSIONS
# ═══════════════════════════════════════════════════════════════

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
        return {"matched": True, "concession_id": best_match.id_concession, "concession_nom": best_match.nom, "score": best_score}
    return {"matched": False, "concession_id": None, "concession_nom": None, "score": best_score}


# ═══════════════════════════════════════════════════════════════
# 7. SUPPRESSION
# ═══════════════════════════════════════════════════════════════

@app.delete("/facture/{facture_id}")
def delete_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404)
    db.delete(facture)
    db.commit()
    invalidate_cache(facture.id_concession)
    return {"message": "Facture supprimee"}


@app.delete("/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models_sql.Item).get(item_id)
    if not item:
        raise HTTPException(status_code=404)
    cid = item.id_concession
    db.delete(item)
    db.commit()
    invalidate_cache(cid)
    return {"message": f"Item {item_id} supprime"}


@app.delete("/items")
def api_delete_items(item_ids: List[int], db: Session = Depends(get_db)):
    deleted, refused = crud.delete_items(db, item_ids)
    if deleted > 0:
        invalidate_cache()
    return {"deleted": deleted, "refused": refused}


# ═══════════════════════════════════════════════════════════════
# 8. RESUME
# ═══════════════════════════════════════════════════════════════

@app.post("/facture/{facture_id}/resume", response_model=schemas.ResumeOut)
def get_resume_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404)
    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    items_dict = {}
    for ligne_info in lignes_data:
        for val in ligne_info["valeurs"]:
            items_dict.setdefault(ligne_info["item"], {})[val["colonne"]] = val["valeur_brute"]
    items_list = [{"description": k, "valeurs": v} for k, v in items_dict.items()]
    concession_nom = facture.concession.nom if facture.concession else ""
    return resume.generate_resume({"id_facture": facture.id_facture, "date_facture": facture.date_facture.isoformat() if facture.date_facture else None, "concession": concession_nom, "devise": facture.devise, "items": items_list, "date_insertion": facture.date_extraction.isoformat() if facture.date_extraction else None, "fournisseur": concession_nom})


# ═══════════════════════════════════════════════════════════════
# 9. DEBUG
# ═══════════════════════════════════════════════════════════════

@app.post("/debug/rebuild")
def rebuild(db: Session = Depends(get_db)):
    invalidate_cache()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
# 10. ANALYSES COMPARATIVES
# ═══════════════════════════════════════════════════════════════

class AnalyseRequest(BaseModel):
    id_concession: int
    annee: Optional[int] = None
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    mois: Optional[int] = None
    trimestre: Optional[int] = None


@app.get("/analyses/comparaison")
def get_comparaison_analyses(id_concession: int, annee: Optional[int] = None, date_debut: Optional[date] = None, date_fin: Optional[date] = None, mois: Optional[int] = None, trimestre: Optional[int] = None, db: Session = Depends(get_db)):
    concession = db.query(models_sql.Concession).get(id_concession)
    if not concession:
        raise HTTPException(status_code=404)

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
        raise HTTPException(status_code=400)

    factures = db.query(models_sql.Facture).filter(models_sql.Facture.id_concession == id_concession, models_sql.Facture.date_facture >= plage_debut, models_sql.Facture.date_facture <= plage_fin).all()
    if not factures:
        return {"concession": concession.nom, "plage": {"debut": str(plage_debut), "fin": str(plage_fin)}, "nb_factures": 0, "kpi": None, "totaux_mensuels": [], "articles_comparaison": [], "anomalies": ["Aucune facture trouvee"], "repartition_articles": [], "comparaison_n1": None}

    total_facture = sum(f.total_montant or 0 for f in factures)
    nb_factures = len(factures)
    totaux_mensuels = [0.0] * 12
    for f in factures:
        if f.date_facture:
            totaux_mensuels[f.date_facture.month - 1] += f.total_montant or 0

    return {"concession": concession.nom, "plage": {"debut": str(plage_debut), "fin": str(plage_fin)}, "nb_factures": nb_factures, "kpi": {"total_facture": round(total_facture, 2), "nb_factures": nb_factures, "panier_moyen": round(total_facture / nb_factures, 2) if nb_factures else 0}, "totaux_mensuels": totaux_mensuels, "articles_comparaison": [], "anomalies": [], "repartition_articles": [], "comparaison_n1": None}


@app.get("/analyses/export-excel")
def export_analyse_excel(id_concession: int, annee: Optional[int] = None, date_debut: Optional[date] = None, date_fin: Optional[date] = None, mois: Optional[int] = None, trimestre: Optional[int] = None, db: Session = Depends(get_db)):
    data = get_comparaison_analyses(id_concession=id_concession, annee=annee, date_debut=date_debut, date_fin=date_fin, mois=mois, trimestre=trimestre, db=db)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analyse"
    ws.append(["Analyse pour", data["concession"], f"{data['plage']['debut']} a {data['plage']['fin']}"])
    if data["kpi"]:
        ws.append(["Total facture", data["kpi"]["total_facture"]])
        ws.append(["Nombre factures", data["kpi"]["nb_factures"]])
    ws.append([])
    ws.append(["Mois", "Total"])
    for i, t in enumerate(data["totaux_mensuels"]):
        ws.append([i+1, t])
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=analyse_doccore.xlsx"})


# ═══════════════════════════════════════════════════════════════
# 11. SSE - Upload avec logs temps réel
# ═══════════════════════════════════════════════════════════════

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
            import threading as th
            try:
                t0 = time_module.time()
                log_queue.put(json.dumps({"step": "upload", "message": "Fichier recu, demarrage...", "progress": 2, "elapsed": 0}))
                time_module.sleep(0.3)
                log_queue.put(json.dumps({"step": "preprocess", "message": "Analyse qualite image...", "progress": 5, "elapsed": round(time_module.time() - t0, 1)}))
                time_module.sleep(0.3)
                log_queue.put(json.dumps({"step": "language", "message": "Detection langue...", "progress": 8, "elapsed": round(time_module.time() - t0, 1)}))
                time_module.sleep(0.3)
                log_queue.put(json.dumps({"step": "ocr_select", "message": "Selection moteur OCR...", "progress": 12, "elapsed": round(time_module.time() - t0, 1)}))
                ocr_start = time_module.time()
                ocr_running = True
                last_progress = 12
                def update_ocr():
                    nonlocal last_progress
                    while ocr_running:
                        time_module.sleep(1)
                        if not ocr_running:
                            break
                        elapsed = round(time_module.time() - t0, 1)
                        p = min(12 + (round(time_module.time() - ocr_start, 1) / 180) * 48, 60)
                        if p > last_progress:
                            last_progress = p
                        log_queue.put(json.dumps({"step": "ocr", "message": "OCR en cours...", "progress": round(last_progress, 1), "elapsed": elapsed, "ocr_elapsed": round(time_module.time() - ocr_start, 1)}))
                th.Thread(target=update_ocr, daemon=True).start()
                raw_result = extract_invoice(tmp_path, max_pages=10)
                ocr_running = False
                ocr_total = round(time_module.time() - ocr_start, 1)
                total = round(time_module.time() - t0, 1)
                log_queue.put(json.dumps({"step": "ocr_done", "message": f"OCR termine en {ocr_total}s", "progress": 65, "elapsed": total, "ocr_elapsed": ocr_total}))
                time_module.sleep(0.3)
                log_queue.put(json.dumps({"step": "postprocess", "message": "Post-processing...", "progress": 78, "elapsed": round(time_module.time() - t0, 1)}))
                structured = process_from_dict(raw_result)
                time_module.sleep(0.3)
                log_queue.put(json.dumps({"step": "correct", "message": "Correction intelligente...", "progress": 92, "elapsed": round(time_module.time() - t0, 1)}))
                total = round(time_module.time() - t0, 1)
                log_queue.put(json.dumps({"step": "done", "message": f"Extraction terminee en {total}s ! {len(structured.get('items', []))} articles", "progress": 100, "elapsed": total, "ocr_elapsed": ocr_total, "item_count": len(structured.get('items', [])), "result": structured}))
            except Exception as e:
                log_queue.put(json.dumps({"step": "error", "message": f"Erreur : {str(e)}", "progress": 0, "error": True}))
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
            yield f"data: {json.dumps({'error': 'Tache non trouvee'})}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")
    log_queue = extraction_logs[task_id]
    async def event_generator():
        try:
            while True:
                try:
                    msg = log_queue.get(timeout=0.1)
                    if msg is None:
                        yield f"data: {json.dumps({'step': 'complete', 'message': 'Termine'})}\n\n"
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
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ═══════════════════════════════════════════════════════════════
# Frontend statique
# ═══════════════════════════════════════════════════════════════

frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend-doc")
if os.path.isdir(frontend_path):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")