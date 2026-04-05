from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import tempfile
from pathlib import Path
import json
from typing import List
from datetime import datetime

from api.database import get_db, engine, Base
from api import models_sql, schemas, crud, semantic, resume
# FIXME ORIGINAL: "from main import extract_invoice_complete" → circular import
# extract_invoice_complete doit être dans un module séparé, ex: api/extractor.py
# Pour l'instant on importe depuis le bon chemin :
from main import extract_invoice_complete
from postprocess import postprocess_invoice

Base.metadata.create_all(bind=engine)
app = FastAPI(title="DocCore Invoice API")


@app.post("/upload", response_model=schemas.ExtractionResult)
async def upload_facture(file: UploadFile = File(...)):
    content = await file.read()
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        raw_result = extract_invoice_complete(tmp_path, max_pages=10)
        structured = postprocess_invoice(raw_result)  # passe dict directement, pas de fichier tmp
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return structured


# Ajoutez cette fonction si elle n'existe pas
def compute_hash(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()

# Modifiez le endpoint create_facture
@app.post("/facture", response_model=schemas.FactureOut)
def create_facture(
    payload: schemas.FactureWithItems,
    db: Session = Depends(get_db),
    force: bool = False,  # paramètre optionnel (ex: ?force=true)
):
    # Vérifier si une facture avec le même nom existe déjà
    existing = db.query(models_sql.Facture).filter(
        models_sql.Facture.nom_fichier == payload.facture.nom_fichier
    ).first()
    if existing and not force:
        raise HTTPException(
            status_code=409,
            detail=f"La facture '{payload.facture.nom_fichier}' existe déjà. Utilisez force=true pour écraser."
        )
    if existing and force:
        # Supprimer l'ancienne facture (cascade supprime les fact_data)
        db.delete(existing)
        db.commit()

    # Convertir la date si nécessaire
    facture_data = payload.facture
    if facture_data.date_facture and isinstance(facture_data.date_facture, str):
        try:
            facture_data.date_facture = datetime.strptime(facture_data.date_facture, "%Y-%m-%d")
        except ValueError:
            facture_data.date_facture = None

    db_facture = crud.create_facture(db, facture_data)
    crud.create_fact_data(db, db_facture.id_facture, [i.dict() for i in payload.items_data])
    semantic.invalidate_cache()  # invalider le cache FAISS
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
    items_dict: dict = {}
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
        "nom_fichier": facture.nom_fichier,
        "date_facture": facture.date_facture.isoformat() if facture.date_facture else None,
        "concession": facture.concession,
        "devise": facture.devise,
        "items": items_list
    }
    return resume.generate_resume(facture_dict)

# api/main.py (ajout à la fin)

@app.delete("/facture/{facture_id}")
def delete_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    db.delete(facture)
    db.commit()
    return {"message": "Facture supprimée"}
