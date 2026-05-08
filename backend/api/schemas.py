from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ------------------------------------------------------------------------------
# CONCESSION
# ------------------------------------------------------------------------------
class ConcessionBase(BaseModel):
    nom: str
    nom_normalise: Optional[str] = None  # Sera calculé automatiquement


class ConcessionCreate(ConcessionBase):
    pass


class ConcessionOut(ConcessionBase):
    id_concession: int
    date_creation: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# ITEM (lié à une concession)
# ------------------------------------------------------------------------------
class ItemBase(BaseModel):
    libelle_canonique: str
    libelle_recherche: Optional[str] = None  # Sera calculé automatiquement


class ItemCreate(ItemBase):
    id_concession: int


class ItemOut(ItemBase):
    id_item: int
    id_concession: Optional[int] = None   # autorise les items sans concession
    date_creation: datetime
    usage_count: int = 0                  # ajouté pour l'interface

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# COLONNE (liée à une concession)
# ------------------------------------------------------------------------------
class ColonneBase(BaseModel):
    libelle_canonique: str
    libelle_recherche: Optional[str] = None


class ColonneCreate(ColonneBase):
    id_concession: int


class ColonneOut(ColonneBase):
    id_colonne: int
    id_concession: Optional[int] = None   # autorise les colonnes sans concession
    date_creation: datetime
    usage_count: int = 0                  # ajouté pour l'interface

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# FACTURE (liée à une concession)
# ------------------------------------------------------------------------------
class FactureBase(BaseModel):
    id_concession: Optional[int] = None 
    numero_facture: Optional[str] = None
    date_facture: Optional[datetime] = None
    devise: Optional[str] = "EUR"
    fichier_source: Optional[str] = None
    valide: Optional[str] = "0"
    total_montant: Optional[float] = None


class FactureCreate(FactureBase):
    nom_concession: Optional[str] = None


class FactureOut(FactureBase):
    id_facture: int
    date_extraction: datetime
    total_montant: Optional[float] = None
    total_quantite: Optional[int] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# LIGNE FACTURE
# ------------------------------------------------------------------------------
class LigneFactureBase(BaseModel):
    id_facture: int
    id_item: int


class LigneFactureCreate(LigneFactureBase):
    pass


class LigneFactureOut(LigneFactureBase):
    id_ligne: int

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# VALEUR LIGNE (valeur brute d'une colonne pour une ligne)
# ------------------------------------------------------------------------------
class ValeurLigneBase(BaseModel):
    id_colonne: int
    valeur_brute: str


class ValeurLigneCreate(ValeurLigneBase):
    pass


class ValeurLigneOut(ValeurLigneBase):
    id_valeur: int
    id_ligne: int

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# Schémas pour l'extraction (inchangés pour l'instant)
# ------------------------------------------------------------------------------
class ExtractionMetadata(BaseModel):
    company: Optional[str] = None
    concession: Optional[str] = None
    date: Optional[str] = None
    currency: Optional[str] = "USD"
    first_column_name: Optional[str] = "Description"


class ExtractionItem(BaseModel):
    description: str
    valeurs: Dict[str, Optional[Any]]   # Les valeurs seront des chaînes brutes


class ExtractionResult(BaseModel):
    metadata: dict
    columns: List[str]
    items: List[dict]

class ExtractionResponse(BaseModel):
    # Si une seule facture, ces champs sont remplis
    metadata: Optional[dict] = None
    columns: Optional[List[str]] = None
    items: Optional[List[dict]] = None
    # Si plusieurs factures, ce champ contient la liste
    invoices: Optional[List[ExtractionResult]] = None

# ------------------------------------------------------------------------------
# Payload pour création de facture avec lignes et valeurs brutes
# ------------------------------------------------------------------------------
class LigneFacturePayload(BaseModel):
    """Une ligne d'article avec ses valeurs brutes par colonne."""
    description: str
    valeurs: Dict[str, str]   # clé = nom de colonne, valeur = chaîne brute


class FactureWithItems(BaseModel):
    """Payload complet envoyé par le frontend pour enregistrer une facture."""
    facture: FactureCreate
    items_data: List[LigneFacturePayload]


# ------------------------------------------------------------------------------
# Suggestion sémantique (doit maintenant prendre en compte la concession)
# ------------------------------------------------------------------------------
class SuggestionResponse(BaseModel):
    item_id: Optional[int] = None
    libelle_canonique: Optional[str] = None
    confiance: Optional[float] = None


# ------------------------------------------------------------------------------
# Résumé (peut rester similaire, à adapter selon les besoins)
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



    # ajouter pour daschboard

    # ------------------------------------------------------------------------------
# Schémas pour la gestion via l'interface Base de données
# ------------------------------------------------------------------------------
class ItemCreatePayload(BaseModel):
    """Payload pour créer un item manuellement."""
    libelle_canonique: str
    id_concession: Optional[int] = None


class ColonneCreatePayload(BaseModel):
    """Payload pour créer une colonne manuellement."""
    libelle_canonique: str
    id_concession: Optional[int] = None


class ConcessionCreatePayload(BaseModel):
    """Payload pour créer une concession via JSON."""
    nom: str