from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import tempfile
from pathlib import Path
import os
import time
import gc
from datetime import datetime
from typing import List, Optional

from backend.api.database import get_db, engine, Base
from backend.api import models_sql, schemas, crud, resume
from backend.extraction.main import extract_invoice_complete
from backend.extraction.postprocess import postprocess_invoice   # déjà bon dans votre code
from backend.semantic import semantic                            # déjà bon
from backend.semantic.semantic import normalize_text
from fastapi.staticfiles import StaticFiles
import hashlib
import json

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

Base.metadata.create_all(bind=engine)
app = FastAPI(title="DocCore Invoice API")

# --- Configuration CORS pour autoriser le frontend ---
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, remplacez par l'URL exacte du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# 1. UPLOAD & EXTRACTION (inchangé pour le moment)
# ------------------------------------------------------------------------------
@app.post("/upload", response_model=schemas.ExtractionResponse)
async def upload_facture(file: UploadFile = File(...)):
    content = await file.read()
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.close()
        raw_result = extract_invoice_complete(tmp_path, max_pages=50)
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

    # Si le postprocess retourne une liste -> plusieurs factures
    if isinstance(structured, list):
        return {"invoices": structured}
    else:
        # Une seule facture : on retourne les champs directement (compatibilité)
        return {
            "metadata": structured.get("metadata"),
            "columns": structured.get("columns"),
            "items": structured.get("items"),
            "invoices": None
        }


# ------------------------------------------------------------------------------
# 2. CRÉATION D'UNE FACTURE (avec hash de contenu)
# ------------------------------------------------------------------------------
@app.post("/facture", response_model=schemas.FactureOut)
def create_facture(
    payload: schemas.FactureWithItems,
    db: Session = Depends(get_db),
    force: bool = False,
):
    # ---------- 1. Gestion de la concession ----------
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
    else:
        raise HTTPException(status_code=400, detail="Paramètres de concession invalides")

    payload.facture.id_concession = concession_id

    # ---------- 2. Conversion de la date ----------
    if payload.facture.date_facture and isinstance(payload.facture.date_facture, str):
        parsed = parse_date(payload.facture.date_facture)
        if parsed is None:
            raise HTTPException(status_code=400, detail="Format de date invalide")
        payload.facture.date_facture = parsed

    # ---------- 3. Calcul du hash de contenu ----------
    # Normaliser les items : trier par description, puis pour chaque item trier les valeurs
    normalized_items = []
    for item in payload.items_data:
        desc = item.description.strip()
        # Trier les clés des valeurs alphabétiquement
        sorted_vals = sorted(item.valeurs.items()) if item.valeurs else []
        normalized_items.append({
            "description": desc,
            "valeurs": sorted_vals
        })
    # Trier les items par description
    normalized_items.sort(key=lambda x: x["description"])
    # Sérialiser en JSON trié et stable
    content_string = json.dumps(normalized_items, ensure_ascii=False, sort_keys=True)
    content_hash = hashlib.sha256(content_string.encode("utf-8")).hexdigest()

    # ---------- 4. Vérifier l'existence d'une facture avec le même hash ----------
    existing = db.query(models_sql.Facture).filter(
        models_sql.Facture.hash_contenu == content_hash
    ).first()

    if existing and not force:
        raise HTTPException(
            status_code=409,
            detail="Une facture avec le même contenu existe déjà. Utilisez force=true pour écraser."
        )
    if existing and force:
        # Supprimer l'ancienne facture et toutes ses dépendances (cascade)
        db.delete(existing)
        db.commit()

    # ---------- 5. Créer la nouvelle facture ----------
    db_facture = crud.create_facture(db, payload.facture)
    # Assigner le hash après la création (champ nullable, unique)
    db_facture.hash_contenu = content_hash
    db.flush()

    # ---------- 6. Insérer les lignes et valeurs brutes ----------
    crud.create_lignes_facture(
        db,
        id_facture=db_facture.id_facture,
        items_data=payload.items_data,
        id_concession=concession_id
    )

    # Invalider le cache sémantique
    semantic.invalidate_cache(concession_id=concession_id)

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
    # Récupérer les lignes et valeurs associées
    data = crud.get_fact_data_by_facture(db, facture_id)
    return {"facture": facture, "data": data}


@app.get("/facture/{facture_id}/details")
def get_facture_details(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    # Utiliser la nouvelle fonction pour obtenir les lignes/valeurs
    lignes_data = crud.get_fact_data_by_facture(db, facture_id)

    # Reconstruire un format compatible avec l'ancien frontend (tableau à plat)
    details = []
    for ligne_info in lignes_data:
        item_name = ligne_info["item"]
        for val in ligne_info["valeurs"]:
            details.append({
                "item": item_name,
                "colonne": val["colonne"],
                "valeur": val["valeur_brute"]
            })

    return {"id_facture": facture_id, "details": details}


# ------------------------------------------------------------------------------
# 4. GESTION DES ITEMS & COLONNES
# ------------------------------------------------------------------------------
@app.get("/items", response_model=List[schemas.ItemOut])
def get_all_items(
    db: Session = Depends(get_db),
    id_concession: Optional[int] = Query(None, description="Filtrer par concession")
):
    if id_concession:
        return db.query(models_sql.Item).filter(models_sql.Item.id_concession == id_concession).all()
    return crud.get_all_items(db)


@app.get("/colonnes", response_model=List[schemas.ColonneOut])
def get_all_colonnes(
    db: Session = Depends(get_db),
    id_concession: Optional[int] = Query(None, description="Filtrer par concession")
):
    if id_concession:
        return db.query(models_sql.Colonne).filter(models_sql.Colonne.id_concession == id_concession).all()
    return crud.get_all_colonnes(db)


# ------------------------------------------------------------------------------
# 5. SUGGESTION SÉMANTIQUE (avec concession)
# ------------------------------------------------------------------------------
@app.get("/suggest", response_model=schemas.SuggestionResponse)
def suggest_item(
    description: str,
    id_concession: int,
    db: Session = Depends(get_db)
):
    result = semantic.find_similar_item(db, description, id_concession)
    if result:
        item_id, confidence = result
        item = db.query(models_sql.Item).get(item_id)
        if item:
            return {
                "item_id": item_id,
                "libelle_canonique": item.libelle_canonique,
                "confiance": confidence
            }
    return {"item_id": None, "libelle_canonique": None, "confiance": None}


# ------------------------------------------------------------------------------
# 6. CONCESSIONS
# ------------------------------------------------------------------------------
@app.post("/concessions", response_model=schemas.ConcessionOut)
def get_or_create_concession(
    nom: str,
    db: Session = Depends(get_db)
):
    """Recherche ou crée une concession à partir de son nom brut."""
    concession = crud.get_or_create_concession(db, nom)
    db.commit() 
    return concession


@app.get("/concessions", response_model=List[schemas.ConcessionOut])
def list_concessions(db: Session = Depends(get_db)):
    return db.query(models_sql.Concession).all()

@app.get("/match-concession")
def match_concession(
    nom_extrait: str,
    db: Session = Depends(get_db)
):
    """
    Recherche la concession la plus proche du nom extrait par matching flou.
    Retourne l'ID et le nom si le score >= seuil (0.8), sinon indique aucun match.
    """
    from rapidfuzz import fuzz  # ou autre librairie de fuzzy matching

    concessions = db.query(models_sql.Concession).all()
    best_match = None
    best_score = 0.0

    nom_norm = normalize_text(nom_extrait)

    for c in concessions:
        # Comparaison sur le nom normalisé ou le nom brut
        score = fuzz.ratio(nom_norm.lower(), c.nom_normalise.lower()) / 100.0
        if score > best_score:
            best_score = score
            best_match = c

    threshold = 0.8
    if best_score >= threshold and best_match:
        return {
            "matched": True,
            "concession_id": best_match.id_concession,
            "concession_nom": best_match.nom,
            "score": best_score
        }
    else:
        return {
            "matched": False,
            "concession_id": None,
            "concession_nom": None,
            "score": best_score
        }
# ------------------------------------------------------------------------------
# 7. SUPPRESSION & MISE À JOUR (adaptées)
# ------------------------------------------------------------------------------
@app.delete("/facture/{facture_id}")
def delete_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    id_concession = facture.id_concession
    db.delete(facture)
    db.commit()
    semantic.invalidate_cache(concession_id=id_concession)
    return {"message": "Facture supprimée"}


@app.delete("/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models_sql.Item).get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item non trouvé")
    id_concession = item.id_concession
    # Supprimer les références dans ligne_facture (cascade configurée dans les relations)
    db.delete(item)
    db.commit()
    semantic.invalidate_cache(concession_id=id_concession)
    return {"message": f"Item {item_id} supprimé"}


@app.delete("/items")
def delete_items(item_ids: List[int], db: Session = Depends(get_db)):
    concession_ids = set()
    for item_id in item_ids:
        item = db.query(models_sql.Item).get(item_id)
        if item:
            concession_ids.add(item.id_concession)
            db.delete(item)
    db.commit()
    for cid in concession_ids:
        semantic.invalidate_cache(concession_id=cid)
    return {"deleted": len(item_ids)}


# ------------------------------------------------------------------------------
# 8. RÉSUMÉ (à adapter plus tard)
# ------------------------------------------------------------------------------
@app.post("/facture/{facture_id}/resume", response_model=schemas.ResumeOut)
def get_resume_facture(facture_id: int, db: Session = Depends(get_db)):
    facture = crud.get_facture_by_id(db, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    lignes_data = crud.get_fact_data_by_facture(db, facture_id)
    items_dict = {}
    for ligne_info in lignes_data:
        item_name = ligne_info["item"]
        if item_name not in items_dict:
            items_dict[item_name] = {}
        for val in ligne_info["valeurs"]:
            items_dict[item_name][val["colonne"]] = val["valeur_brute"]

    items_list = [{"description": k, "valeurs": v} for k, v in items_dict.items()]
    concession_nom = facture.concession.nom if facture.concession else ""
    facture_dict = {
        "id_facture": facture.id_facture,
        "date_facture": facture.date_facture.isoformat() if facture.date_facture else None,
        "concession": concession_nom,
        "devise": facture.devise,
        "items": items_list,
        "date_insertion": facture.date_extraction.isoformat() if facture.date_extraction else None,
        "fournisseur": concession_nom,
        "client": None,   # Ces champs n'existent plus dans la nouvelle base
        "objet": None,
    }
    return resume.generate_resume(facture_dict)


# ------------------------------------------------------------------------------
# 9. DEBUG
# ------------------------------------------------------------------------------
@app.post("/debug/rebuild")
def rebuild(db: Session = Depends(get_db)):
    semantic.invalidate_cache()  # vide tout
    # Reconstruire pour toutes les concessions ? On peut laisser le lazy loading
    return {"status": "ok"}






#comprsion et analyse 


# ------------------------------------------------------------------------------
# 10. ANALYSES COMPARATIVES
# ------------------------------------------------------------------------------
@app.get("/analyses/comparaison")
def get_comparaison_analyses(
    id_concession: int,
    annee: int,
    db: Session = Depends(get_db)
):
    """
    Retourne les données agrégées pour les graphiques d'analyse d'une concession sur une année.
    """
    from sqlalchemy import extract, func
    from datetime import datetime

    # Vérifier que la concession existe
    concession = db.query(models_sql.Concession).get(id_concession)
    if not concession:
        raise HTTPException(status_code=404, detail="Concession non trouvée")

    # Récupérer toutes les factures de l'année pour cette concession
    factures = db.query(models_sql.Facture).filter(
        models_sql.Facture.id_concession == id_concession,
        extract('year', models_sql.Facture.date_facture) == annee
    ).all()

    if not factures:
        return {"message": "Aucune facture trouvée pour cette période", "data": None}

    # Agrégation des totaux par mois
    totaux_mensuels = {mois: 0.0 for mois in range(1, 13)}
    for f in factures:
        if f.date_facture and f.total_montant:
            mois = f.date_facture.month
            totaux_mensuels[mois] += f.total_montant

    # Récupération détaillée de toutes les lignes de toutes les factures
    # (pour l'analyse des articles et prix unitaires)
    details_items = []
    for f in factures:
        lignes_data = crud.get_fact_data_by_facture(db, f.id_facture)
        for ligne_info in lignes_data:
            item_name = ligne_info["item"]
            valeurs = {v["colonne"]: v["valeur_brute"] for v in ligne_info["valeurs"]}
            # On suppose qu'il y a une colonne "Prix Unitaire" ou "Montant" identifiable
            # À adapter selon les colonnes réelles de vos factures
            montant = None
            for col_name, val in valeurs.items():
                if "prix" in col_name.lower() or "montant" in col_name.lower() or "total" in col_name.lower():
                    try:
                        montant = float(val.replace(',', '.').strip())
                        break
                    except:
                        pass
            details_items.append({
                "facture_id": f.id_facture,
                "date_facture": f.date_facture.isoformat() if f.date_facture else None,
                "item": item_name,
                "montant": montant,
                "valeurs": valeurs
            })

    # Regrouper les articles pour comparer leurs prix
    articles_stats = {}
    for d in details_items:
        item = d["item"]
        if item not in articles_stats:
            articles_stats[item] = {"occurrences": 0, "montants": []}
        articles_stats[item]["occurrences"] += 1
        if d["montant"] is not None:
            articles_stats[item]["montants"].append(d["montant"])

    # Calculer moyenne, min, max pour chaque article
    articles_comparaison = []
    for article, stats in articles_stats.items():
        if stats["montants"]:
            articles_comparaison.append({
                "article": article,
                "occurrences": stats["occurrences"],
                "prix_moyen": sum(stats["montants"]) / len(stats["montants"]),
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

    return {
        "concession": concession.nom,
        "annee": annee,
        "totaux_mensuels": [totaux_mensuels[m] for m in range(1, 13)],
        "articles_comparaison": articles_comparaison,
        "nb_factures": len(factures)
    }

# ------ Servir le frontend (statique) ------
import os
frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")