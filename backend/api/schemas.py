from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


# ------------------------------------------------------------------------------
# CONCESSION
# ------------------------------------------------------------------------------
class ConcessionCreatePayload(BaseModel):
    """Payload pour créer une concession."""
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
    """Payload pour créer un item manuellement."""
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
    """Payload pour créer une colonne manuellement."""
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
    valide: Optional[str] = "0"
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
    total_quantite: Optional[float] = None
    devise: Optional[str] = "EUR"
    fichier_source: Optional[str] = None
    valide: Optional[str] = "0"
    statut: Optional[str] = "traite"
    fournisseur: Optional[str] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# LIGNE FACTURE & VALEUR
# ------------------------------------------------------------------------------
class LigneFactureOut(BaseModel):
    id_ligne: int
    id_facture: int
    id_item: int
    confiance: Optional[float] = 1.0
    auto_match: Optional[str] = '1'

    class Config:
        from_attributes = True


class ValeurLigneOut(BaseModel):
    id_valeur: int
    id_ligne: int
    id_colonne: int
    valeur_brute: str
    valeur_numerique: Optional[float] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# EXTRACTION
# ------------------------------------------------------------------------------
class ExtractionMetadata(BaseModel):
    company: Optional[str] = None
    concession: Optional[str] = None
    date: Optional[str] = None
    currency: Optional[str] = "USD"
    first_column_name: Optional[str] = "Description"


class ExtractionItem(BaseModel):
    description: str
    valeurs: Dict[str, Optional[Any]]


class ExtractionResult(BaseModel):
    metadata: dict
    columns: List[str]
    items: List[dict]


class ExtractionResponse(BaseModel):
    metadata: Optional[dict] = None
    columns: Optional[List[str]] = None
    items: Optional[List[dict]] = None
    invoices: Optional[List[dict]] = None


# ------------------------------------------------------------------------------
# PAYLOAD COMBINÉ POUR LA CRÉATION DE FACTURE
# ------------------------------------------------------------------------------
class LigneFacturePayload(BaseModel):
    """Une ligne d'article avec ses valeurs brutes par colonne."""
    description: str
    valeurs: Dict[str, str]
    semantic_decision: Optional[str] = "new"   # 'link', 'new', 'skip'
    semantic_target_id: Optional[int] = None
    semantic_auto: Optional[str] = "0"


# ------------------------------------------------------------------------------
# SUGGESTION SÉMANTIQUE
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


# ------------------------------------------------------------------------------
# SECTION (gestion multi-tableaux)
# ------------------------------------------------------------------------------
class ColonneSectionPayload(BaseModel):
    """Définition d'une colonne dans une section (nom + ordre)."""
    header: str
    ordre: int


class SectionPayload(BaseModel):
    """Un tableau (section) avec son titre, ses colonnes et ses lignes."""
    titre: str
    colonnes: List[ColonneSectionPayload]
    items_data: List[LigneFacturePayload]


# ------------------------------------------------------------------------------
# FACTURE WITH ITEMS
# ------------------------------------------------------------------------------
class FactureWithItems(BaseModel):
    """Payload complet envoyé par le frontend pour enregistrer une facture.
       Peut contenir soit une liste plate d'items_data (ancien comportement),
       soit une liste de sections avec leurs colonnes et lignes (nouveau).
    """
    facture: FactureCreate
    items_data: Optional[List[LigneFacturePayload]] = None  # rétrocompatibilité
    sections: Optional[List[SectionPayload]] = None         # nouveau mode


# ------------------------------------------------------------------------------
# FOURNISSEUR
# ------------------------------------------------------------------------------
class FournisseurCreate(BaseModel):
    nom: str
    id_concession: Optional[int] = None


class FournisseurOut(BaseModel):
    id_fournisseur: int
    nom: str
    nom_normalise: str
    id_concession: Optional[int]

    class Config:
        from_attributes = True