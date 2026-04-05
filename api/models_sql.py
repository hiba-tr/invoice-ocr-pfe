from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from api.database import Base


class Facture(Base):
    __tablename__ = "facture"
    id_facture = Column(Integer, primary_key=True, autoincrement=True)
    nom_fichier = Column(String(500))
    date_facture = Column(DateTime)
    concession = Column(String(255))
    devise = Column(String(10), default="USD")

    fact_data = relationship("FactData", back_populates="facture", cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "item"
    id_item = Column(Integer, primary_key=True, autoincrement=True)
    nom_item = Column(String(500), unique=True, nullable=False)

    fact_data = relationship("FactData", back_populates="item")


class Colonne(Base):
    __tablename__ = "colonne"
    id_colonne = Column(Integer, primary_key=True, autoincrement=True)
    nom_colonne = Column(String(500), unique=True, nullable=False)

    fact_data = relationship("FactData", back_populates="colonne")


class FactData(Base):
    __tablename__ = "fact_data"
    id_facture = Column(Integer, ForeignKey("facture.id_facture"), primary_key=True)
    id_item = Column(Integer, ForeignKey("item.id_item"), primary_key=True)
    id_colonne = Column(Integer, ForeignKey("colonne.id_colonne"), primary_key=True)
    valeur = Column(Float, nullable=True)
    date_insertion = Column(DateTime, default=datetime.utcnow)

    facture = relationship("Facture", back_populates="fact_data")
    item = relationship("Item", back_populates="fact_data")
    colonne = relationship("Colonne", back_populates="fact_data")

    __table_args__ = (
        PrimaryKeyConstraint('id_facture', 'id_item', 'id_colonne'),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id_audit = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(50), nullable=False)
    action = Column(String(10), nullable=False)   # INSERT | UPDATE | DELETE
    record_id = Column(Integer)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)        # nullable pour DELETE
    modified_by = Column(String(100), default="system")
    modified_at = Column(DateTime, default=datetime.utcnow)