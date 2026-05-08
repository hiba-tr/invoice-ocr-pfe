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

    # Relations
    items = relationship("Item", back_populates="concession", cascade="all, delete-orphan")
    colonnes = relationship("Colonne", back_populates="concession", cascade="all, delete-orphan")
    factures = relationship("Facture", back_populates="concession", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('nom_normalise', name='uniq_concession_nom_norm'),
        Index('idx_concession_nom', 'nom'),
    )


# ------------------------------------------------------------------------------
# 2. ITEM
# ------------------------------------------------------------------------------
class Item(Base):
    __tablename__ = "item"

    id_item = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    libelle_canonique = Column(String(300), nullable=False)
    libelle_recherche = Column(String(300), nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)

    # Relations
    concession = relationship("Concession", back_populates="items")
    lignes_facture = relationship("LigneFacture", back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('id_concession', 'libelle_canonique', name='uniq_item_concession_libelle'),
        Index('idx_item_recherche', 'id_concession', 'libelle_recherche'),
    )


# ------------------------------------------------------------------------------
# 3. COLONNE
# ------------------------------------------------------------------------------
class Colonne(Base):
    __tablename__ = "colonne"

    id_colonne = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    libelle_canonique = Column(String(200), nullable=False)
    libelle_recherche = Column(String(200), nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)

    # Relations
    concession = relationship("Concession", back_populates="colonnes")
    valeurs_ligne = relationship("ValeurLigne", back_populates="colonne", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('id_concession', 'libelle_canonique', name='uniq_colonne_concession_libelle'),
        Index('idx_colonne_recherche', 'id_concession', 'libelle_recherche'),
    )


# ------------------------------------------------------------------------------
# 4. FACTURE
# ------------------------------------------------------------------------------
class Facture(Base):
    __tablename__ = "facture"

    id_facture = Column(Integer, primary_key=True, autoincrement=True)
    id_concession = Column(Integer, ForeignKey("concession.id_concession"), nullable=False)
    numero_facture = Column(String(50))
    date_facture = Column(DateTime)
    date_extraction = Column(DateTime, default=datetime.utcnow)
    total_montant = Column(Float)
    total_quantite = Column(Integer)
    devise = Column(String(3), default="EUR")
    fichier_source = Column(String(500))
    hash_contenu = Column(String(64), unique=True, nullable=True, index=True)
    valide = Column(String(1), default='0')          # '0' ou '1'

    # Relations
    concession = relationship("Concession", back_populates="factures")
    lignes_facture = relationship("LigneFacture", back_populates="facture", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("valide IN ('0','1')", name='chk_facture_valide'),
        Index('uniq_facture_import', 'id_concession', 'numero_facture', 'date_facture', unique=True),
    )


# ------------------------------------------------------------------------------
# 5. LIGNE_FACTURE
# ------------------------------------------------------------------------------
class LigneFacture(Base):
    __tablename__ = "ligne_facture"

    id_ligne = Column(Integer, primary_key=True, autoincrement=True)
    id_facture = Column(Integer, ForeignKey("facture.id_facture"), nullable=False)
    id_item = Column(Integer, ForeignKey("item.id_item"), nullable=False)

    # Relations
    facture = relationship("Facture", back_populates="lignes_facture")
    item = relationship("Item", back_populates="lignes_facture")
    valeurs = relationship("ValeurLigne", back_populates="ligne", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_ligne_facture_fk', 'id_facture'),
        Index('idx_ligne_item_fk', 'id_item'),
    )


# ------------------------------------------------------------------------------
# 6. VALEUR_LIGNE
# ------------------------------------------------------------------------------
class ValeurLigne(Base):
    __tablename__ = "valeur_ligne"

    id_valeur = Column(Integer, primary_key=True, autoincrement=True)
    id_ligne = Column(Integer, ForeignKey("ligne_facture.id_ligne"), nullable=False)
    id_colonne = Column(Integer, ForeignKey("colonne.id_colonne"), nullable=False)
    valeur_brute = Column(String(100), nullable=False)

    # Relations
    ligne = relationship("LigneFacture", back_populates="valeurs")
    colonne = relationship("Colonne", back_populates="valeurs_ligne")

    __table_args__ = (
        UniqueConstraint('id_ligne', 'id_colonne', name='uniq_valeur_ligne_colonne'),
        Index('idx_valeur_ligne_fk', 'id_ligne'),
        Index('idx_valeur_colonne_fk', 'id_colonne'),
    )


# ------------------------------------------------------------------------------
# 7. AUDIT_LOG (conservé, peut rester inchangé ou être adapté)
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