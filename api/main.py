from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import tempfile
from pathlib import Path
import os
import time
import gc
from datetime import datetime
from typing import List

from api.database import get_db, engine, Base
from api import models_sql, schemas, crud, semantic, resume
from main import extract_invoice_complete
from postprocess import postprocess_invoice
from api.semantic import normalize_text

Base.metadata.create_all(bind=engine)
app = FastAPI(title="DocCore Invoice API")


@app.post("/upload", response_model=schemas.ExtractionResult)
async def upload_facture(file: UploadFile = File(...)):
    content = await file.read()
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.close()
        raw_result = extract_invoice_complete(tmp_path, max_pages=10)
        structured = postprocess_invoice(raw_result)
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
    return structured


def compute_hash(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()


@app.post("/facture", response_model=schemas.FactureOut)
def create_facture(
    payload: schemas.FactureWithItems,
    db: Session = Depends(get_db),
    force: bool = False,
):
    existing = db.query(models_sql.Facture).filter(
        models_sql.Facture.nom_fichier == payload.facture.nom_fichier
    ).first()
    if existing and not force:
        raise HTTPException(status_code=409, detail="La facture existe déjà. Utilisez force=true.")
    if existing and force:
        db.delete(existing)
        db.commit()

    facture_data = payload.facture
    # Conversion date
    if facture_data.date_facture and isinstance(facture_data.date_facture, str):
        parsed = parse_date(facture_data.date_facture)
        if parsed is None:
            raise HTTPException(status_code=400, detail="Format de date invalide")
        facture_data.date_facture = parsed

    db_facture = crud.create_facture(db, facture_data)
    crud.create_fact_data(db, db_facture.id_facture, [i.dict() for i in payload.items_data])
    semantic.invalidate_cache()
    return db_facture


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
    
    # Récupérer UNIQUEMENT les items liés à cette facture (via fact_data)
    items_de_cette_facture = (
        db.query(models_sql.Item)
        .join(models_sql.FactData, models_sql.FactData.id_item == models_sql.Item.id_item)
        .filter(models_sql.FactData.id_facture == facture_id)
        .distinct()
        .all()
    )

    # Récupérer UNIQUEMENT les colonnes qui existent pour cette facture
    colonnes_utilisees = (
        db.query(models_sql.Colonne)
        .join(models_sql.FactData, models_sql.FactData.id_colonne == models_sql.Colonne.id_colonne)
        .filter(models_sql.FactData.id_facture == facture_id)
        .distinct()
        .all()
    )

    fact_data = db.query(models_sql.FactData).filter(models_sql.FactData.id_facture == facture_id).all()
    valeurs_map = {(fd.id_item, fd.id_colonne): fd.valeur for fd in fact_data}

    details = []
    for item in items_de_cette_facture:
        for col in colonnes_utilisees:
            valeur = valeurs_map.get((item.id_item, col.id_colonne), None)
            details.append({
                "item": item.nom_item,
                "colonne": col.nom_colonne,
                "valeur": valeur
            })
            
    return {"id_facture": facture_id, "details": details}


@app.get("/items", response_model=List[schemas.ItemOut])
def get_all_items(db: Session = Depends(get_db)):
    return crud.get_all_items(db)


@app.get("/colonnes", response_model=List[schemas.ColonneOut])
def get_all_colonnes(db: Session = Depends(get_db)):
    return crud.get_all_colonnes(db)


@app.get("/suggest", response_model=schemas.SuggestionResponse)
def suggest_item(description: str, db: Session = Depends(get_db)):
    result = semantic.find_similar_item(db, description)
    if result:
        item_id, confidence = result
        item = db.query(models_sql.Item).filter(models_sql.Item.id_item == item_id).first()
        if item:  # Vérification que l'item existe bien
            return {"item_id": item_id, "nom_item": item.nom_item, "confiance": confidence}
    return {"item_id": None, "nom_item": None, "confiance": None}


@app.get("/fact_data")
def get_all_fact_data(db: Session = Depends(get_db)):
    return db.query(models_sql.FactData).all()


@app.put("/fact_data", response_model=schemas.FactDataOut)
def update_fact_data(
    facture_id: int,
    item_id: int,
    colonne_id: int,
    nouvelle_valeur: float,
    db: Session = Depends(get_db)
):
    fd = crud.update_fact_data(db, facture_id, item_id, colonne_id, nouvelle_valeur)
    if not fd:
        raise HTTPException(status_code=404, detail="Entrée non trouvée")
    return fd


@app.delete("/fact_data")
def delete_fact_data(
    facture_id: int,
    item_id: int,
    colonne_id: int,
    db: Session = Depends(get_db)
):
    deleted = crud.delete_fact_data(db, facture_id, item_id, colonne_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entrée non trouvée")
    return {"message": "Supprimé"}


@app.post("/facture/{facture_id}/resume", response_model=schemas.ResumeOut)
def get_resume_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    fact_data = crud.get_fact_data_by_facture(db, facture_id)
    items_dict = {}
    for fd in fact_data:
        item = db.query(models_sql.Item).filter(models_sql.Item.id_item == fd.id_item).first()
        colonne = db.query(models_sql.Colonne).filter(models_sql.Colonne.id_colonne == fd.id_colonne).first()
        if item and colonne:
            if item.nom_item not in items_dict:
                items_dict[item.nom_item] = {}
            items_dict[item.nom_item][colonne.nom_colonne] = fd.valeur

    items_list = [{"description": k, "valeurs": v} for k, v in items_dict.items()]
    facture_dict = {
        "id_facture": facture.id_facture,
        "date_facture": facture.date_facture.isoformat() if facture.date_facture else None,
        "concession": facture.concession,
        "devise": facture.devise,
        "items": items_list,
        "date_insertion": facture.date_creation.isoformat() if facture.date_creation else None,
        "fournisseur": facture.concession,
        "client": facture.client,
        "objet": facture.objet,
    }
    return resume.generate_resume(facture_dict)


@app.delete("/facture/{facture_id}")
def delete_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    db.delete(facture)
    db.commit()
    return {"message": "Facture supprimée"}



@app.post("/debug/rebuild")
def rebuild(db: Session = Depends(get_db)):
    semantic.invalidate_cache()
    semantic._ensure_index(db)
    return {"status": "ok"}

@app.delete("/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models_sql.Item).filter(models_sql.Item.id_item == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item non trouvé")
    # Supprimer d'abord les références dans fact_data
    db.query(models_sql.FactData).filter(models_sql.FactData.id_item == item_id).delete()
    db.delete(item)
    db.commit()
    semantic.invalidate_cache()  # Reconstruire l'index FAISS
    return {"message": f"Item {item_id} supprimé"}

@app.delete("/items")
def delete_items(item_ids: List[int], db: Session = Depends(get_db)):
    for item_id in item_ids:
        item = db.query(models_sql.Item).filter(models_sql.Item.id_item == item_id).first()
        if item:
            db.query(models_sql.FactData).filter(models_sql.FactData.id_item == item_id).delete()
            db.delete(item)
    db.commit()
    semantic.invalidate_cache()
    return {"deleted": len(item_ids)}