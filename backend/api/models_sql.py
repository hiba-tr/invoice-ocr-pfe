from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime,
    CheckConstraint, UniqueConstraint, Index, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.api.database import Base
from sqlalchemy import func
from sqlalchemy import Identity
# ------------------------------------------------------------------------------
# 1. CONCESSION (identique)
# ------------------------------------------------------------------------------
class Concession(Base):
    __tablename__ = "concession"

    id_concession = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String(200), nullable=False)
    nom_normalise = Column(String(200), nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)

    items = relationship("Item", back_populates="concession", cascade="all, delete-orphan")
    colonnes = relationship("Colonne", back_populates="concession", cascade="all, delete-orphan")
    factures = relationship("Facture", back_populates="concession", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('nom_normalise', name='uniq_concession_nom_norm'),
        Index('idx_concession_nom', 'nom'),
    )


# ------------------------------------------------------------------------------
# 2. ITEM (fusionné : colonnes de la binôme ajoutées)
# ------------------------------------------------------------------------------
class Item(Base):
    __tablename__ = "item"

    id_item = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    libelle_canonique = Column(String(300), nullable=False)
    libelle_recherche = Column(String(300), nullable=False)

    # Colonnes ajoutées par la binôme
    statut = Column(String(20), default="actif")
    date_creation = Column(DateTime, default=datetime.utcnow)   # déjà présent (fusion)
    date_derniere_util = Column(DateTime, nullable=True)
    fusionne_avec = Column(Integer, nullable=True)

    concession = relationship("Concession", back_populates="items")
    lignes_facture = relationship("LigneFacture", back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('id_concession', 'libelle_canonique', name='uniq_item_conc_lib'),
        Index('idx_item_recherche', 'id_concession', 'libelle_recherche'),
        Index('idx_item_statut', 'statut'),   # ajout binôme
    )


# ------------------------------------------------------------------------------
# 3. COLONNE (identique)
# ------------------------------------------------------------------------------
class Colonne(Base):
    __tablename__ = "colonne"

    id_colonne = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    libelle_canonique = Column(String(200), nullable=False)
    libelle_recherche = Column(String(200), nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)
    
    concession = relationship("Concession", back_populates="colonnes")
    valeurs_ligne = relationship("ValeurLigne", back_populates="colonne", cascade="all, delete-orphan")
    sections_colonnes = relationship("SectionColonne", back_populates="colonne", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('id_concession', 'libelle_canonique', name='uniq_col_conc_lib'),
        Index('idx_colonne_recherche', 'id_concession', 'libelle_recherche'),
    )


# ------------------------------------------------------------------------------
# 4. FACTURE (fusion complexe : on garde les colonnes des deux)
# ------------------------------------------------------------------------------
class Facture(Base):
    __tablename__ = "facture"

    id_facture = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    numero_facture = Column(String(100))            # élargi (binôme)
    date_facture = Column(DateTime)
    date_extraction = Column(DateTime, default=datetime.utcnow)
    total_montant = Column(Float)
    total_quantite = Column(Float)                  # Float de la binôme (au lieu d'Integer)
    devise = Column(String(10), default="EUR")      # élargi (binôme)
    fichier_source = Column(String(500))
    hash_contenu = Column(String(200), unique=True, nullable=True)  # élargi (binôme)

    # Colonne historique (ta version)
    valide = Column(String(1), default='0')         # conservé
    # Colonnes ajoutées par la binôme
    statut = Column(String(20), default="traite")
    fournisseur = Column(String(300))
    confiance_ocr = Column(Float)
    extra_metadata = Column(Text) 
    concession = relationship("Concession", back_populates="factures")
    lignes_facture = relationship("LigneFacture", back_populates="facture", cascade="all, delete-orphan")
    sections = relationship("SectionFacture", back_populates="facture", cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("valide IN ('0','1')", name='chk_facture_valide'),   # ta contrainte
        Index('uniq_facture_import', 'id_concession', 'numero_facture', 'date_facture', unique=True),  # ton index unique
        Index('idx_facture_concession', 'id_concession'),          # binôme
        Index('idx_facture_date', 'date_facture'),                # binôme
        Index('idx_facture_hash', 'hash_contenu'),                # binôme
        Index('idx_facture_statut', 'statut'),                    # binôme
    )


# ------------------------------------------------------------------------------
# 5. SECTION_FACTURE (NOUVEAU)
# ------------------------------------------------------------------------------
class SectionFacture(Base):
    __tablename__ = "section_facture"

    id_section = Column(Integer, primary_key=True, autoincrement=True)
    id_facture = Column(Integer, ForeignKey("facture.id_facture", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)   # ordre dans la facture (0,1,2...)
    titre = Column(String(200), nullable=False)       # ex: "Main d'œuvre", "Matériel"

    facture = relationship("Facture", back_populates="sections")
    colonnes_section = relationship("SectionColonne", back_populates="section", cascade="all, delete-orphan")
    lignes = relationship("LigneFacture", back_populates="section", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('id_facture', 'section_index', name='uniq_section_order'),
        Index('idx_section_facture', 'id_facture'),
    )


# ------------------------------------------------------------------------------
# 6. SECTION_COLONNE (NOUVEAU)
# ------------------------------------------------------------------------------
class SectionColonne(Base):
    __tablename__ = "section_colonne"

    id_section = Column(Integer, ForeignKey("section_facture.id_section", ondelete="CASCADE"), primary_key=True)
    id_colonne = Column(Integer, ForeignKey("colonne.id_colonne"), primary_key=True)
    ordre = Column(Integer, nullable=False)  # position dans le tableau (0,1,2...)

    section = relationship("SectionFacture", back_populates="colonnes_section")
    colonne = relationship("Colonne", back_populates="sections_colonnes")

    __table_args__ = (
        Index('idx_sectioncolonne_section', 'id_section'),
        Index('idx_sectioncolonne_colonne', 'id_colonne'),
    )


# ------------------------------------------------------------------------------
# 7. LIGNE_FACTURE (ajout id_section)
# ------------------------------------------------------------------------------
class LigneFacture(Base):
    __tablename__ = "ligne_facture"

    id_ligne = Column(Integer, primary_key=True, autoincrement=True)
    id_facture = Column(Integer, ForeignKey("facture.id_facture"), nullable=False)
    id_item = Column(Integer, ForeignKey("item.id_item"), nullable=False)
    # *** AJOUT ***
    id_section = Column(Integer, ForeignKey("section_facture.id_section"), nullable=False)

    confiance = Column(Float, default=1.0)
    auto_match = Column(String(1), default='1')

    facture = relationship("Facture", back_populates="lignes_facture")
    item = relationship("Item", back_populates="lignes_facture")
    valeurs = relationship("ValeurLigne", back_populates="ligne", cascade="all, delete-orphan")
    # *** AJOUT ***
    section = relationship("SectionFacture", back_populates="lignes")

    __table_args__ = (
        Index('idx_ligne_facture_fk', 'id_facture'),
        Index('idx_ligne_item_fk', 'id_item'),
        Index('idx_ligne_section_fk', 'id_section'),   # nouvel index
    )

# ------------------------------------------------------------------------------
# 6. VALEUR_LIGNE (ajout valeur_numerique)
# ------------------------------------------------------------------------------
class ValeurLigne(Base):
    __tablename__ = "valeur_ligne"

    id_valeur = Column(Integer, primary_key=True, autoincrement=True)
    id_ligne = Column(Integer, ForeignKey("ligne_facture.id_ligne"), nullable=False)
    id_colonne = Column(Integer, ForeignKey("colonne.id_colonne"), nullable=False)
    valeur_brute = Column(String(500), nullable=False)
    valeur_numerique = Column(Float, nullable=True)   # ajout binôme

    ligne = relationship("LigneFacture", back_populates="valeurs")
    colonne = relationship("Colonne", back_populates="valeurs_ligne")

    __table_args__ = (
        UniqueConstraint('id_ligne', 'id_colonne', name='uniq_valeur_ligne_colonne'),
        Index('idx_valeur_ligne_fk', 'id_ligne'),
        Index('idx_valeur_colonne_fk', 'id_colonne'),
    )

class Fournisseur(Base):
    __tablename__ = "fournisseurs"
    id_fournisseur = Column(Integer, Identity(start=1), primary_key=True)   
    nom = Column(String(255), nullable=False, unique=True)
    nom_normalise = Column(String(255), nullable=False)  # version nettoyée pour le matching
    # Lien éventuel avec une concession (peut être NULL si non lié)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=True)
    concession = relationship("Concession", backref="fournisseurs")
    created_at = Column(DateTime, server_default=func.now())

# ------------------------------------------------------------------------------
# 7. AUDIT_LOG (identique)
# ------------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"
    id_audit = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(50), nullable=False)
    action = Column(String(10), nullable=False)
    record_id = Column(Integer)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    modified_by = Column(String(100), default="system")
    modified_at = Column(DateTime, default=datetime.utcnow)