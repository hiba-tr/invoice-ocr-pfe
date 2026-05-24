"""
startup.py — Point d'entrée unique pour pré-charger tous les modèles lourds.
À appeler UNE SEULE FOIS au démarrage du serveur.

Exemple FastAPI :
    from backend.semantic.startup import preload_all

    @app.on_event("startup")
    async def on_startup():
        preload_all()

Exemple Django / WSGI :
    # Dans AppConfig.ready() :
    from backend.semantic.startup import preload_all
    preload_all()
"""
import logging
import threading

_log = logging.getLogger(__name__)
_preloaded = False
_lock      = threading.Lock()


def preload_all() -> None:
    """
    Lance en arrière-plan (threads daemons) le chargement de :
      1. SentenceTransformer (embedder)
      2. MarianMT EN→FR et FR→EN (translator)
      3. Cache words_to_number (numbers) — déjà lancé à l'import

    Aucun appel ne bloque le thread principal.
    Les modèles seront prêts en ~5–10 s selon le matériel.
    """
    global _preloaded
    with _lock:
        if _preloaded:
            return
        _preloaded = True

    _log.info("🚀 Pré-chargement des modèles sémantiques en arrière-plan…")

    # 1. Embedding (SentenceTransformer)
    try:
        from .embeddings.embedder import _preload_model_background
        _preload_model_background()
    except Exception as e:
        _log.warning(f"Pré-chargement embedder ignoré : {e}")

    # 2. Traducteurs MarianMT
    try:
        from .preprocessing.translator import preload_translators_background
        preload_translators_background()
    except Exception as e:
        _log.warning(f"Pré-chargement traducteurs ignoré : {e}")

    # 3. Cache words_to_number — déjà lancé automatiquement à l'import de numbers.py
    _log.info("✅ Pré-chargement lancé (modèles disponibles dans ~5-10 s)")