from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class FactureBase(BaseModel):
    nom_fichier: Optional[str] = None
    date_facture: Optional[datetime] = None
    concession: Optional[str] = None
    devise: Optional[str] = "USD"
    client: Optional[str] = None
    objet: Optional[str] = None


class FactureCreate(FactureBase):
    pass


class FactureOut(FactureBase):
    id_facture: int
    date_creation: Optional[datetime] = None

    class Config:
        from_attributes = True


class ItemBase(BaseModel):
    nom_item: str


class ItemCreate(ItemBase):
    pass


class ItemOut(ItemBase):
    id_item: int

    class Config:
        from_attributes = True


class ColonneBase(BaseModel):
    nom_colonne: str


class ColonneCreate(ColonneBase):
    pass


class ColonneOut(ColonneBase):
    id_colonne: int

    class Config:
        from_attributes = True


class FactDataBase(BaseModel):
    id_facture: int
    id_item: int
    id_colonne: int
    valeurs: Dict[str, Optional[Any]]



class FactDataOut(FactDataBase):
    date_insertion: datetime

    class Config:
        from_attributes = True


class ExtractionItem(BaseModel):
    description: str
    valeurs: Dict[str, Optional[Any]]



class ExtractionMetadata(BaseModel):
    company: Optional[str] = None
    concession: Optional[str] = None
    date: Optional[str] = None
    currency: Optional[str] = "USD"
    first_column_name: Optional[str] = "Description"


class ExtractionResult(BaseModel):
    metadata: ExtractionMetadata
    items: List[ExtractionItem]


class FactureItemPayload(BaseModel):
    description: str
    valeurs: Dict[str, Optional[Any]]



class FactureWithItems(BaseModel):
    facture: FactureCreate
    items_data: List[FactureItemPayload]


class SuggestionResponse(BaseModel):
    item_id: Optional[int] = None
    nom_item: Optional[str] = None
    confiance: Optional[float] = None


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
    resume_texte: Optional[str] = None   # NOUVEAU : texte formaté

class ResumeOut(BaseModel):
    resume: ResumeDetail
    
class FactureCreate(BaseModel):
    nom_fichier: str
    date_facture: Optional[str] = None
    concession: Optional[str] = None
    devise: Optional[str] = None
    client: Optional[str] = None
    objet: Optional[str] = None

    