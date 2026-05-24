"""
Configuration centralisée du module sémantique.
CORRECTION : seuils alignés avec les valeurs réelles utilisées dans engine.py
"""
from dataclasses import dataclass


@dataclass
class SemanticConfig:
    """Configuration du matching sémantique."""

    # Modèle d'embedding
    model_name:           str   = "all-MiniLM-L6-v2"
    embedding_dimension:  int   = 384
    embedding_batch_size: int   = 64     # était 32 → 64 (aligné avec embedder.py)

    # Seuils de matching (alignés avec MatchingEngine dans engine.py)
    threshold_fuzzy:      int   = 70     # était 85 → 70 (cohérent avec engine.py)
    threshold_embedding:  float = 0.60   # était 0.70 → 0.60 (cohérent avec engine.py)
    threshold_auto_match: float = 0.85   # décision automatique (pipeline.py)
    threshold_validation: float = 0.55   # demande validation humaine (pipeline.py)

    # Cache FAISS
    cache_ttl_seconds:     int  = 600    # 10 minutes
    cache_max_age_seconds: int  = 3600   # 1 heure

    # Synonymes
    synonym_threshold:    float = 0.70   # seuil similarité cosinus
    max_synonym_variants: int   = 10     # max variantes par texte

    # Traduction
    enable_translation: bool = True      # activée (translate_en_to_fr est cachée)

    # Performance
    precompute_vocab:   bool = True      # pré-calculer les embeddings au démarrage


# Instance par défaut
config = SemanticConfig()