"""
Configuration centralisée du module sémantique.
"""
from dataclasses import dataclass


@dataclass
class SemanticConfig:
    """Configuration du matching sémantique."""
    
    # Modèle d'embedding
    model_name: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_batch_size: int = 32
    
    # Seuils de matching
    threshold_fuzzy: int = 85          # RapidFuzz (0-100)
    threshold_embedding: float = 0.70  # Cosine similarity (0-1)
    threshold_auto_match: float = 0.95 # Décision automatique
    threshold_validation: float = 0.70 # Demande validation humaine
    
    # Cache
    cache_ttl_seconds: int = 600       # 10 minutes
    cache_max_age_seconds: int = 3600  # 1 heure
    
    # Synonymes
    synonym_threshold: float = 0.80    # Seuil similarité cosinus
    max_synonym_variants: int = 12     # Max variantes par texte
    
    # Traduction
    enable_translation: bool = False   # Désactivé (modèle multilingue)
    
    # Performance
    precompute_vocab: bool = True      # Pré-calculer les embeddings


# Instance par défaut
config = SemanticConfig()