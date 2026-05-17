from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


# ------------------------------------------------------------------------------
# CONCESSION
# ------------------------------------------------------------------------------
class ConcessionCreatePayload(BaseModel):
    nom: str


class ConcessionOut(BaseModel):
    id_concession: int
    nom: str
    nom_normalise: Optional[str] = None
    date_creation: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# ITEM
# ------------------------------------------------------------------------------
class ItemCreatePayload(BaseModel):
    libelle_canonique: str
    id_concession: Optional[int] = None


class ItemOut(BaseModel):
    id_item: int
    id_concession: Optional[int] = None
    libelle_canonique: str
    libelle_recherche: Optional[str] = None
    statut: Optional[str] = "actif"
    date_creation: datetime
    date_derniere_util: Optional[datetime] = None
    usage_count: int = 0

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# COLONNE
# ------------------------------------------------------------------------------
class ColonneCreatePayload(BaseModel):
    libelle_canonique: str
    id_concession: Optional[int] = None


class ColonneOut(BaseModel):
    id_colonne: int
    id_concession: Optional[int] = None
    libelle_canonique: str
    libelle_recherche: Optional[str] = None
    date_creation: datetime
    usage_count: int = 0

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# FACTURE
# ------------------------------------------------------------------------------
class FactureCreate(BaseModel):
    id_concession: Optional[int] = None
    nom_concession: Optional[str] = None
    numero_facture: Optional[str] = None
    date_facture: Optional[datetime] = None
    devise: Optional[str] = "EUR"
    fichier_source: Optional[str] = None
    statut: Optional[str] = "traite"
    total_montant: Optional[float] = None
    fournisseur: Optional[str] = None


class FactureOut(BaseModel):
    id_facture: int
    id_concession: Optional[int] = None
    numero_facture: Optional[str] = None
    date_facture: Optional[datetime] = None
    date_extraction: datetime
    total_montant: Optional[float] = None
    devise: Optional[str] = "EUR"
    fichier_source: Optional[str] = None
    statut: Optional[str] = "traite"
    fournisseur: Optional[str] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# EXTRACTION
# ------------------------------------------------------------------------------
class ExtractionResponse(BaseModel):
    metadata: Optional[dict] = None
    columns: Optional[List[str]] = None
    items: Optional[List[dict]] = None
    invoices: Optional[List[dict]] = None


# ------------------------------------------------------------------------------
# LIGNE FACTURE
# ------------------------------------------------------------------------------
class LigneFacturePayload(BaseModel):
    description: str
    valeurs: Dict[str, str]


class FactureWithItems(BaseModel):
    facture: FactureCreate
    items_data: List[LigneFacturePayload]


# ------------------------------------------------------------------------------
# SUGGESTION
# ------------------------------------------------------------------------------
class SuggestionResponse(BaseModel):
    item_id: Optional[int] = None
    libelle_canonique: Optional[str] = None
    confiance: Optional[float] = None
    needs_confirmation: Optional[bool] = None
    candidates: Optional[List[dict]] = None


# ------------------------------------------------------------------------------
# RÉSUMÉ
# ------------------------------------------------------------------------------
class ResumeDetail(BaseModel):
    numero: Optional[int] = None
    date_emission: Optional[str] = None
    fournisseur: Optional[str] = None
    client: Optional[str] = None
    objet: Optional[str] = None
    nb_articles: int = 0
    categories_principales: List[str] = []
    exemples_articles: List[str] = []
    total_ht: float = 0.0
    tva_taux: float = 0.0
    tva_montant: float = 0.0
    total_ttc: float = 0.0
    devise: str = "USD"
    date_insertion: Optional[str] = None
    resume_texte: Optional[str] = None


class ResumeOut(BaseModel):
    resume: ResumeDetail