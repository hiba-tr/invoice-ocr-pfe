from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime,
    CheckConstraint, UniqueConstraint, Index, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.api.database import Base


# ------------------------------------------------------------------------------
# 1. CONCESSION
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
    fournisseurs = relationship("Fournisseur", back_populates="concession", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('nom_normalise', name='uniq_concession_nom_norm'),
        Index('idx_concession_nom', 'nom'),
    )


# ------------------------------------------------------------------------------
# 2. FOURNISSEUR
# ------------------------------------------------------------------------------
class Fournisseur(Base):
    __tablename__ = "fournisseurs"

    id_fournisseur = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String(255), nullable=False, unique=True)
    nom_normalise = Column(String(255), nullable=False)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    concession = relationship("Concession", back_populates="fournisseurs")
    factures = relationship("Facture", back_populates="fournisseur_rel")

    __table_args__ = (
        Index('idx_fournisseur_nom', 'nom'),
        Index('idx_fournisseur_nom_normalise', 'nom_normalise'),
    )


# ------------------------------------------------------------------------------
# 3. ITEM
# ------------------------------------------------------------------------------
class Item(Base):
    __tablename__ = "item"

    id_item = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    libelle_canonique = Column(String(300), nullable=False)
    libelle_recherche = Column(String(300), nullable=False)
    statut = Column(String(20), default="actif")
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_derniere_util = Column(DateTime, nullable=True)
    fusionne_avec = Column(Integer, nullable=True)

    concession = relationship("Concession", back_populates="items")
    lignes_facture = relationship("LigneFacture", back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('id_concession', 'libelle_canonique', name='uniq_item_conc_lib'),
        Index('idx_item_recherche', 'id_concession', 'libelle_recherche'),
        Index('idx_item_statut', 'statut'),
    )


# ------------------------------------------------------------------------------
# 4. COLONNE
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
# 5. FACTURE
# ------------------------------------------------------------------------------
class Facture(Base):
    __tablename__ = "facture"

    id_facture = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    id_fournisseur = Column(Integer, ForeignKey("fournisseurs.id_fournisseur"), nullable=True)
    numero_facture = Column(String(100))
    date_facture = Column(DateTime)
    date_extraction = Column(DateTime, default=datetime.utcnow)
    total_montant = Column(Float)
    total_quantite = Column(Float)
    devise = Column(String(10), default="EUR")
    fichier_source = Column(String(500))
    hash_contenu = Column(String(200), unique=True, nullable=True)
    valide = Column(String(1), default='0')
    statut = Column(String(20), default="traite")
    fournisseur = Column(String(300))       # champ texte libre conservé pour compatibilité
    confiance_ocr = Column(Float)

    concession = relationship("Concession", back_populates="factures")
    fournisseur_rel = relationship("Fournisseur", back_populates="factures")
    lignes_facture = relationship("LigneFacture", back_populates="facture", cascade="all, delete-orphan")
    sections = relationship("SectionFacture", back_populates="facture", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("valide IN ('0','1')", name='chk_facture_valide'),
        Index('uniq_facture_import', 'id_concession', 'numero_facture', 'date_facture', unique=True),
        Index('idx_facture_concession', 'id_concession'),
        Index('idx_facture_fournisseur', 'id_fournisseur'),
        Index('idx_facture_date', 'date_facture'),
        Index('idx_facture_hash', 'hash_contenu'),
        Index('idx_facture_statut', 'statut'),
    )


# ------------------------------------------------------------------------------
# 6. SECTION_FACTURE
# ------------------------------------------------------------------------------
class SectionFacture(Base):
    __tablename__ = "section_facture"

    id_section = Column(Integer, primary_key=True, autoincrement=True)
    id_facture = Column(Integer, ForeignKey("facture.id_facture", ondelete="CASCADE"), nullable=False)
    section_index = Column(Integer, nullable=False)
    titre = Column(String(200), nullable=False)

    facture = relationship("Facture", back_populates="sections")
    colonnes_section = relationship("SectionColonne", back_populates="section", cascade="all, delete-orphan")
    lignes = relationship("LigneFacture", back_populates="section", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('id_facture', 'section_index', name='uniq_section_order'),
        Index('idx_section_facture', 'id_facture'),
    )


# ------------------------------------------------------------------------------
# 7. SECTION_COLONNE
# ------------------------------------------------------------------------------
class SectionColonne(Base):
    __tablename__ = "section_colonne"

    id_section = Column(Integer, ForeignKey("section_facture.id_section", ondelete="CASCADE"), primary_key=True)
    id_colonne = Column(Integer, ForeignKey("colonne.id_colonne"), primary_key=True)
    ordre = Column(Integer, nullable=False)

    section = relationship("SectionFacture", back_populates="colonnes_section")
    colonne = relationship("Colonne", back_populates="sections_colonnes")

    __table_args__ = (
        Index('idx_sectioncolonne_section', 'id_section'),
        Index('idx_sectioncolonne_colonne', 'id_colonne'),
    )


# ------------------------------------------------------------------------------
# 8. LIGNE_FACTURE
# ------------------------------------------------------------------------------
class LigneFacture(Base):
    __tablename__ = "ligne_facture"

    id_ligne = Column(Integer, primary_key=True, autoincrement=True)
    id_facture = Column(Integer, ForeignKey("facture.id_facture"), nullable=False)
    id_item = Column(Integer, ForeignKey("item.id_item"), nullable=False)
    id_section = Column(Integer, ForeignKey("section_facture.id_section"), nullable=False)
    confiance = Column(Float, default=1.0)
    auto_match = Column(String(1), default='1')

    facture = relationship("Facture", back_populates="lignes_facture")
    item = relationship("Item", back_populates="lignes_facture")
    section = relationship("SectionFacture", back_populates="lignes")
    valeurs = relationship("ValeurLigne", back_populates="ligne", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_ligne_facture_fk', 'id_facture'),
        Index('idx_ligne_item_fk', 'id_item'),
        Index('idx_ligne_section_fk', 'id_section'),
    )


# ------------------------------------------------------------------------------
# 9. VALEUR_LIGNE
# ------------------------------------------------------------------------------
class ValeurLigne(Base):
    __tablename__ = "valeur_ligne"

    id_valeur = Column(Integer, primary_key=True, autoincrement=True)
    id_ligne = Column(Integer, ForeignKey("ligne_facture.id_ligne"), nullable=False)
    id_colonne = Column(Integer, ForeignKey("colonne.id_colonne"), nullable=False)
    valeur_brute = Column(String(500), nullable=False)
    valeur_numerique = Column(Float, nullable=True)

    ligne = relationship("LigneFacture", back_populates="valeurs")
    colonne = relationship("Colonne", back_populates="valeurs_ligne")

    __table_args__ = (
        UniqueConstraint('id_ligne', 'id_colonne', name='uniq_valeur_ligne_colonne'),
        Index('idx_valeur_ligne_fk', 'id_ligne'),
        Index('idx_valeur_colonne_fk', 'id_colonne'),
    )


# ------------------------------------------------------------------------------
# 10. AUDIT_LOG
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