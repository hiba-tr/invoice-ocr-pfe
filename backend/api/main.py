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



import re

# ──────────────────────────────────────────────────────────────
# Coller cette fonction AU NIVEAU MODULE (avant les endpoints)
# ──────────────────────────────────────────────────────────────

def _parse_montant(val_brute: str) -> float | None:
    """
    Parse robuste d'une valeur monétaire brute extraite d'une facture.
    Gère : '1 234,56 €', '1234.56', '1,234.56', '-200', '1.234,56', etc.
    Retourne None si non parseable.
    """
    if not val_brute:
        return None
    s = str(val_brute).strip()

    # Supprimer les symboles monétaires et espaces insécables
    s = re.sub(r'[€$£\u00a0\u202f]', '', s).strip()

    # Cas : valeur entre parenthèses → négatif (ex: accounting format)
    negative = s.startswith('(') and s.endswith(')')
    if negative:
        s = s[1:-1]

    # Détecter le format : séparateur décimal = virgule ou point
    # Cas 1 : "1.234,56"  → milliers=point, décimal=virgule
    # Cas 2 : "1,234.56"  → milliers=virgule, décimal=point
    # Cas 3 : "1234,56"   → décimal=virgule (pas de séparateur milliers)
    # Cas 4 : "1234.56"   → décimal=point
    # Cas 5 : "1.234"     → milliers=point (entier), pas de décimale

    if re.search(r'\.\d{3}[,]\d{2}$', s):
        # 1.234,56 → 1234.56
        s = s.replace('.', '').replace(',', '.')
    elif re.search(r',\d{3}[.]\d{2}$', s):
        # 1,234.56 → 1234.56
        s = s.replace(',', '')
    elif ',' in s and '.' not in s:
        # 1234,56 → 1234.56
        s = s.replace(',', '.')
    elif '.' in s and ',' not in s:
        # Peut être milliers (1.234) ou décimal (1.56)
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3:
            # Probablement séparateur de milliers
            s = s.replace('.', '')
        # sinon on garde tel quel (décimal)
    else:
        # Enlever tous les séparateurs de milliers (espaces, apostrophes)
        s = re.sub(r"[\s']", '', s)

    try:
        result = float(s)
        return -result if negative else result
    except ValueError:
        return None


def _is_montant_column(col_name: str) -> bool:
    """
    Détecte si un nom de colonne est susceptible de contenir un montant.
    Priorité haute → faible.
    """
    col_lower = col_name.lower().strip()

    HIGH_PRIORITY = [
        'montant total', 'total ttc', 'total ht', 'total général',
        'total facture', 'montant ttc', 'montant ht',
    ]
    MED_PRIORITY = [
        'montant', 'total', 'amount', 'prix total', 'sous-total',
    ]
    LOW_PRIORITY = [
        'prix', 'tarif', 'prix unitaire', 'pu', 'unit price',
        'valeur', 'coût', 'cost',
    ]
    EXCLUDE = [
        'qté', 'quantité', 'quantity', 'qty', 'réf', 'référence',
        'ref', 'taux', 'tva', 'remise', 'discount', 'code',
    ]

    for ex in EXCLUDE:
        if ex in col_lower:
            return False

    for h in HIGH_PRIORITY:
        if h in col_lower:
            return True
    for m in MED_PRIORITY:
        if m in col_lower:
            return True
    for l in LOW_PRIORITY:
        if l in col_lower:
            return True

    return False

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
    semantic.invalidate_cache()

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
        items = db.query(models_sql.Item).filter(models_sql.Item.id_concession == id_concession).all()
    else:
        items = crud.get_all_items(db)
    for item in items:
        item.usage_count = db.query(models_sql.LigneFacture).filter(
            models_sql.LigneFacture.id_item == item.id_item
        ).count()
    return items


@app.get("/colonnes", response_model=List[schemas.ColonneOut])
def get_all_colonnes(
    db: Session = Depends(get_db),
    id_concession: Optional[int] = Query(None, description="Filtrer par concession")
):
    if id_concession:
        colonnes = db.query(models_sql.Colonne).filter(models_sql.Colonne.id_concession == id_concession).all()
    else:
        colonnes = crud.get_all_colonnes(db)
    for colonne in colonnes:
        colonne.usage_count = db.query(models_sql.ValeurLigne).filter(
            models_sql.ValeurLigne.id_colonne == colonne.id_colonne
        ).count()
    return colonnes

@app.post("/items", response_model=schemas.ItemOut)
def api_create_item(payload: schemas.ItemCreatePayload, db: Session = Depends(get_db)):
    item = crud.create_item_manuel(db, payload.libelle_canonique, payload.id_concession)
    return item

@app.post("/colonnes", response_model=schemas.ColonneOut)
def api_create_colonne(payload: schemas.ColonneCreatePayload, db: Session = Depends(get_db)):
    colonne = crud.create_colonne_manuel(db, payload.libelle_canonique, payload.id_concession)
    return colonne
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
def create_concession(payload: schemas.ConcessionCreatePayload, db: Session = Depends(get_db)):
    concession = crud.get_or_create_concession(db, payload.nom)
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
def api_delete_items(item_ids: List[int], db: Session = Depends(get_db)):
    deleted, refused = crud.delete_items(db, item_ids)
    return {"deleted": deleted, "refused": refused}

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

"""
# ------------------------------------------------------------------------------
# 10. ANALYSES COMPARATIVES
# ------------------------------------------------------------------------------
@app.get("/analyses/comparaison")
def get_comparaison_analyses(
    id_concession: int,
    annee: int,
    db: Session = Depends(get_db)
):

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
"""

# ------------------------------------------------------------------------------
# 10. ANALYSES COMPARATIVES (version enrichie)
# ------------------------------------------------------------------------------
from datetime import date
from typing import Optional, List
from pydantic import BaseModel

class AnalyseRequest(BaseModel):
    id_concession: int
    annee: Optional[int] = None
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    mois: Optional[int] = None          # 1-12, si fourni avec annee : filtre sur ce mois
    trimestre: Optional[int] = None     # 1-4, si fourni avec annee : filtre sur ce trimestre

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
    Retourne une analyse enrichie pour une concession avec KPI, totaux mensuels,
    comparaison N-1, anomalies, et répartition articles.
    """
    from sqlalchemy import extract, func
    from datetime import timedelta

    # Vérifier concession
    concession = db.query(models_sql.Concession).get(id_concession)
    if not concession:
        raise HTTPException(status_code=404, detail="Concession non trouvée")

    # Déterminer la plage de dates
    if date_debut and date_fin:
        plage_debut = date_debut
        plage_fin = date_fin
    elif annee and mois:
        plage_debut = date(annee, mois, 1)
        # dernier jour du mois
        if mois == 12:
            plage_fin = date(annee, 12, 31)
        else:
            plage_fin = date(annee, mois + 1, 1) - timedelta(days=1)
    elif annee and trimestre:
        trim_start_month = (trimestre - 1) * 3 + 1
        plage_debut = date(annee, trim_start_month, 1)
        trim_end_month = trim_start_month + 2
        if trim_end_month == 12:
            plage_fin = date(annee, 12, 31)
        else:
            plage_fin = date(annee, trim_end_month + 1, 1) - timedelta(days=1)
    elif annee:
        plage_debut = date(annee, 1, 1)
        plage_fin = date(annee, 12, 31)
    else:
        raise HTTPException(status_code=400, detail="Veuillez spécifier une plage de dates (annee, date_debut/date_fin, mois, trimestre)")

    # Récupérer les factures dans la plage
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
        lignes_data = crud.get_fact_data_by_facture(db, f.id_facture)
        for ligne_info in lignes_data:
            item_name = ligne_info["item"]
            valeurs = {v["colonne"]: v["valeur_brute"] for v in ligne_info["valeurs"]}

            # Parsing robuste du montant
            montant = None
            # Tri des colonnes par priorité décroissante
            cols_sorted = sorted(
                valeurs.items(),
                key=lambda x: (
                    2 if any(h in x[0].lower() for h in ['total ttc','montant total','total ht']) else
                    1 if _is_montant_column(x[0]) else
                    0
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

    # Top article (par occurrences)
    articles_count = {}
    articles_total = {}
    for d in details_items:
        item = d["item"]
        articles_count[item] = articles_count.get(item, 0) + 1
        if d["montant"] is not None:
            articles_total[item] = articles_total.get(item, 0) + d["montant"]
    top_article = max(articles_count, key=articles_count.get) if articles_count else None

    # KPI final
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
            m = f.date_facture.month - 1
            totaux_mensuels[m] += f.total_montant or 0

    # Comparaison N-1 (même plage mais année précédente)
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
            m = f.date_facture.month - 1
            totaux_mensuels_n1[m] += f.total_montant or 0
    total_n1 = sum(f.total_montant or 0 for f in factures_n1)
    evolution = ((total_facture - total_n1) / total_n1 * 100) if total_n1 else None
    comparaison_n1 = {
        "totaux_mensuels": totaux_mensuels_n1,
        "total": round(total_n1, 2),
        "evolution_pct": round(evolution, 2) if evolution is not None else None
    }

    # Articles comparaison (comme avant)
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

    # Répartition des dépenses par article (top 5 + autres)
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
    # Mois sans facture
    for m in range(12):
        if totaux_mensuels[m] == 0:
            mois_nom = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'][m]
            anomalies.append(f"Aucune facture en {mois_nom} {plage_debut.year}")
    # Articles avec variation de prix > 50%
    for art in articles_comparaison:
        if art["prix_moyen"] and art["prix_min"] and art["prix_max"]:
            if art["prix_min"] > 0 and (art["prix_max"] - art["prix_min"]) / art["prix_min"] > 0.5:
                anomalies.append(f"Variation de prix importante pour '{art['article']}' : min {art['prix_min']} €, max {art['prix_max']} €")
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


# --- Endpoint export Excel ---
from fastapi.responses import StreamingResponse
from io import BytesIO
import openpyxl

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
    ws.append(["Analyse pour", data["concession"], f"{data['plage']['debut']} à {data['plage']['fin']}"])
    ws.append([])
    if data["kpi"]:
        ws.append(["KPI", ""])
        ws.append(["Total facturé", data["kpi"]["total_facture"]])
        ws.append(["Nombre factures", data["kpi"]["nb_factures"]])
        ws.append(["Panier moyen", data["kpi"]["panier_moyen"]])
    ws.append([])
    ws.append(["Mois", "Total", "Total N-1"])
    for mois_idx in range(12):
        ws.append([mois_idx+1, data["totaux_mensuels"][mois_idx], data.get("comparaison_n1", {}).get("totaux_mensuels", [0]*12)[mois_idx]])
    ws.append([])
    ws.append(["Article", "Occurrences", "Prix moyen", "Prix min", "Prix max"])
    for art in data["articles_comparaison"]:
        ws.append([art["article"], art["occurrences"], art["prix_moyen"], art["prix_min"], art["prix_max"]])
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=analyse_doccore.xlsx"}
    )
