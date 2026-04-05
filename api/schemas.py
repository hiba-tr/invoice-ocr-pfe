from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ── Facture ──────────────────────────────────────────────────────────────────

class FactureBase(BaseModel):
    nom_fichier: Optional[str] = None
    date_facture: Optional[datetime] = None
    concession: Optional[str] = None
    devise: Optional[str] = "USD"


class FactureCreate(FactureBase):
    pass


class FactureOut(FactureBase):
    id_facture: int

    class Config:
        from_attributes = True


# ── Item ─────────────────────────────────────────────────────────────────────

class ItemBase(BaseModel):
    nom_item: str


class ItemCreate(ItemBase):
    pass


class ItemOut(ItemBase):
    id_item: int

    class Config:
        from_attributes = True


# ── Colonne ───────────────────────────────────────────────────────────────────

class ColonneBase(BaseModel):
    nom_colonne: str


class ColonneCreate(ColonneBase):
    pass


class ColonneOut(ColonneBase):
    id_colonne: int

    class Config:
        from_attributes = True


# ── FactData ──────────────────────────────────────────────────────────────────

class FactDataBase(BaseModel):
    id_facture: int
    id_item: int
    id_colonne: int
    valeur: Optional[float] = None


class FactDataOut(FactDataBase):
    date_insertion: datetime

    class Config:
        from_attributes = True


# ── Extraction (sortie de postprocess) ───────────────────────────────────────

class ExtractionItem(BaseModel):
    description: str
    valeurs: Dict[str, Optional[float]]  # nom_colonne -> valeur


class ExtractionMetadata(BaseModel):
    company: Optional[str] = None
    concession: Optional[str] = None
    date: Optional[str] = None
    currency: Optional[str] = "USD"


class ExtractionResult(BaseModel):
    metadata: ExtractionMetadata
    items: List[ExtractionItem]


# ── Payload unifié POST /facture ──────────────────────────────────────────────

class FactureItemPayload(BaseModel):
    description: str
    valeurs: Dict[str, Optional[float]]


class FactureWithItems(BaseModel):
    facture: FactureCreate
    items_data: List[FactureItemPayload]


# ── Suggestion sémantique ─────────────────────────────────────────────────────

class SuggestionResponse(BaseModel):
    item_id: Optional[int] = None
    nom_item: Optional[str] = None
    confiance: Optional[float] = None  # score réel entre 0 et 1


# ── Résumé ────────────────────────────────────────────────────────────────────

class ResumeDetail(BaseModel):
    nom_fichier: Optional[str] = None
    numero: Optional[int] = None
    date: Optional[str] = None
    fournisseur: Optional[str] = None
    devise: Optional[str] = None
    total: float = 0.0
    nb_items: int = 0
    modifications: List[Any] = []


class ResumeOut(BaseModel):
    resume: ResumeDetail