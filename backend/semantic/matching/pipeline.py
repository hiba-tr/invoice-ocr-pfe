# backend/semantic/matching/pipeline.py - Version complète et corrigée
"""
Pipeline sémantique complet - Version optimisée pour la vitesse
Garde toutes les fonctionnalités : Intelligent Corrector, expansion sémantique, embeddings, cache
OPTIMISATIONS : imports paresseux, singleton lazy, init différée, éviction cache
CORRECTIONS : # et & ne sont plus considérés comme du bruit OCR
"""
import logging
import re
import hashlib
from functools import lru_cache
from typing import List, Dict, Any, Optional

_log = logging.getLogger(__name__)

# ── Imports paresseux (chargés à la première utilisation réelle) ──────────────
_rfuzz: Optional[Any] = None
_FUZZY_AVAILABLE: Optional[bool] = None

def _get_fuzzy():
    """Charge rapidfuzz uniquement à la première utilisation."""
    global _rfuzz, _FUZZY_AVAILABLE
    if _FUZZY_AVAILABLE is None:
        try:
            from rapidfuzz import fuzz as _rf
            _rfuzz = _rf
            _FUZZY_AVAILABLE = True
        except ImportError:
            _rfuzz = None
            _FUZZY_AVAILABLE = False
            _log.warning("⚠️ RapidFuzz non disponible")
    return _rfuzz

# Modules internes : importés en lazy via fonctions dédiées
_normalizer_mod   = None
_translator_mod   = None
_numbers_mod      = None
_synonyms_mod     = None
_embedder_mod     = None
_engine_mod       = None
_corrector_mod    = None

def _norm():
    global _normalizer_mod
    if _normalizer_mod is None:
        from ..preprocessing.normalizer import normalize_text
        _normalizer_mod = normalize_text
    return _normalizer_mod

def _trans():
    global _translator_mod
    if _translator_mod is None:
        from ..preprocessing.translator import translate_en_to_fr, detect_language
        _translator_mod = (translate_en_to_fr, detect_language)
    return _translator_mod

def _nums():
    global _numbers_mod
    if _numbers_mod is None:
        from ..preprocessing.numbers import get_number_variants, words_to_number
        _numbers_mod = (get_number_variants, words_to_number)
    return _numbers_mod

def _syns():
    global _synonyms_mod
    if _synonyms_mod is None:
        from ..knowledge.synonyms import expand_synonyms, _vocab_cache, precompute_vocab_embeddings
        _synonyms_mod = (expand_synonyms, _vocab_cache, precompute_vocab_embeddings)
    return _synonyms_mod

def _emb():
    global _embedder_mod
    if _embedder_mod is None:
        from ..embeddings.embedder import encode_with_variants, get_or_build_index, EMBEDDING_AVAILABLE
        _embedder_mod = (encode_with_variants, get_or_build_index, EMBEDDING_AVAILABLE)
    return _embedder_mod

def _eng():
    global _engine_mod
    if _engine_mod is None:
        from .engine import MatchingEngine, DBItem
        _engine_mod = (MatchingEngine, DBItem)
    return _engine_mod

def _corr():
    global _corrector_mod
    if _corrector_mod is None:
        from .intelligent_corrector import universal_corrector
        _corrector_mod = universal_corrector
    return _corrector_mod

# Accès pratiques (compatibilité avec le reste du code)
def _get_DBItem():
    return _eng()[1]

def _EMBEDDING_AVAILABLE() -> bool:
    try:
        return _emb()[2]
    except Exception:
        return False

# ── Cache pour les résultats de matching ──────────────────────────────────────
_match_cache: Dict[str, Dict] = {}
_cache_max_size = 2000
_cache_hits = 0
_cache_misses = 0

def get_cache_key(text: str, concession_id: int) -> str:
    return hashlib.md5(f"{text}_{concession_id}".encode()).hexdigest()

def _set_cache(key: str, value: dict) -> None:
    """Insère dans le cache avec éviction FIFO quand la limite est atteinte."""
    global _match_cache
    if len(_match_cache) >= _cache_max_size:
        evict_count = _cache_max_size // 5
        keys_to_delete = list(_match_cache.keys())[:evict_count]
        for k in keys_to_delete:
            del _match_cache[k]
    _match_cache[key] = value

# ── Patterns ──────────────────────────────────────────────────────────────────
_DOC_REF_RE = re.compile(
    r'(devis|facture|avoir|bl|bc|br|bon)\s*(n[°o]?\.?\s*)[\w\-/]+|'
    r'\b[a-zA-Z]{1,4}[/\-]\d{3,}|'
    r'n[°o]\.?\s*\d',
    re.IGNORECASE,
)

def _is_doc_reference(text: str) -> bool:
    return bool(_DOC_REF_RE.search(text))

@lru_cache(maxsize=2000)
def _is_number(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip()
    if re.search(r'\d\s*[/:]\s*\d', t):
        return False
    cleaned = re.sub(r'[\s\u00a0]', '', t)
    cleaned = re.sub(r"[()%€$£\-+]", '', cleaned)
    patterns = [
        r'\d{1,3}(\.\d{3})*(,\d+)?',
        r'\d{1,3}(,\d{3})*(\.\d+)?',
        r'\d+([.,]\d+)?',
    ]
    return any(re.fullmatch(p, cleaned) for p in patterns)

# backend/semantic/matching/pipeline.py - Corriger _is_ocr_noise

def _is_ocr_noise(text: str) -> bool:
    """
    Détection du bruit OCR - version corrigée.
    Accepte les caractères **, #, &, /, etc. dans les descriptions normales
    """
    if not text or len(text) < 2:
        return True
    
    # 🔥 CORRECTION : Seuls les caractères vraiment suspects sont du bruit
    # Enlever ** de la détection (car "ReajustementdeStock ** Application..." est valide)
    special_chars = '|+<>\\[]{}'  # Retiré * car ** peut être dans les titres
    if any(c in text for c in special_chars):
        return True
    
    # Vérifier les consonnes sans voyelles (bruit OCR)
    letters = [c for c in text.lower() if c.isalpha()]
    if letters and len(letters) > 4:
        vowels = sum(1 for c in letters if c in 'aeiouy')
        if vowels == 0 and '#' not in text and '&' not in text and '*' not in text:
            return True
    
    return False

def _classify(text: str) -> str:
    if not text or not text.strip():
        return 'empty'
    if _is_doc_reference(text):
        return 'doc_ref'
    if _is_number(text):
        return 'number'
    if _is_ocr_noise(text):
        return 'noise'
    return 'text'

def decompose_texte_compose(text: str) -> List[str]:
    if not text:
        return [text]
    tokens = text.strip().split()
    variants = [text] + tokens
    for i in range(len(tokens)):
        for length in [2, 3]:
            if i + length <= len(tokens):
                variants.append(" ".join(tokens[i:i + length]))
    return sorted(list(set(variants)), key=len, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticPipeline:
    def __init__(self):
        self._engine = None
        self._executor = None

    @property
    def engine(self):
        if self._engine is None:
            MatchingEngine, _ = _eng()
            self._engine = MatchingEngine(threshold_fuzzy=70, threshold_embedding=0.60)
        return self._engine

    @property
    def executor(self):
        if self._executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self._executor = ThreadPoolExecutor(max_workers=2)
        return self._executor

    def _translate_if_needed(self, text: str) -> str:
        translate_en_to_fr, detect_language = _trans()
        langue = detect_language(text)
        if langue == 'en':
            translated = translate_en_to_fr(text)
            if translated != text:
                return translated
        return text

    def _quick_match(self, text: str, db_items: list) -> Dict[str, Any]:
        """Match rapide sans embeddings (exact, normalisé, nombres, tokens)."""
        normalize_text = _norm()
        get_number_variants, _ = _nums()

        text_clean = text.strip()
        text_lower = text_clean.lower()
        text_norm = normalize_text(text_clean)

        # 1. Exact
        for item in db_items:
            if item.libelle_canonique.lower() == text_lower:
                return {"matched": True, "item": item, "score": 1.0, "level": "exact"}

        # 2. Normalisé
        for item in db_items:
            if item.libelle_recherche == text_norm:
                return {"matched": True, "item": item, "score": 0.95, "level": "normalized"}

        # 3. Nombres
        if _is_number(text_clean):
            variants = get_number_variants(text_clean)
            for item in db_items:
                item_variants = get_number_variants(item.libelle_canonique)
                if set(variants) & set(item_variants):  # set() accepte les tuples
                    return {"matched": True, "item": item, "score": 0.98, "level": "number"}

        # 🔥 4. Recherche par mots-clés (pour "ETAT/ETAP" → "ETAP")
        # Extraire les mots significatifs (ignorer la ponctuation)
        keywords = re.findall(r'[A-Za-zÀ-ÖØ-öø-ÿ]+', text_clean)
        for keyword in keywords:
            if len(keyword) < 3:
                continue
            for item in db_items:
                item_lower = item.libelle_canonique.lower()
                if keyword.lower() in item_lower:
                    # Score basé sur la longueur du mot
                    score = min(len(keyword) / max(len(item_lower), 1) * 1.5, 0.85)
                    if score >= 0.6:
                        return {"matched": True, "item": item, "score": score, "level": "keyword"}
        
        # 🔥 5. Recherche par tokens (splittés)
        tokens = text_clean.lower().split()
        if len(tokens) > 1:
            for item in db_items:
                item_lower = item.libelle_canonique.lower()
                matched_tokens = 0
                for token in tokens:
                    if len(token) > 2 and token in item_lower:
                        matched_tokens += 1
                if matched_tokens > 0:
                    token_ratio = matched_tokens / len(tokens)
                    if token_ratio >= 0.5:
                        score = token_ratio * 0.85
                        return {"matched": True, "item": item, "score": score, "level": "token"}

        return {"matched": False}

    def process_item(
        self,
        text: str,
        db_items: list,
        concession_id: int,
        concession_index=None,
    ) -> Dict[str, Any]:

        global _cache_hits, _cache_misses

        cache_key = get_cache_key(text, concession_id)
        if cache_key in _match_cache:
            _cache_hits += 1
            return _match_cache[cache_key].copy()
        _cache_misses += 1

        text_clean = text.strip()
        text_type = _classify(text_clean)

        result = {
            "texte_original": text_clean,
            "texte_corrige": text_clean,
            "texte_normalise": text_clean,
            "texte_traduit": text_clean,
            "langue_detectee": "unknown",
            "embedding": None,
            "action": "skip",
            "item_id": None,
            "libelle": None,
            "confiance": 0.0,
            "score": 0.0,
            "niveau": None,
            "candidates": [],
            "text_type": text_type,
            "auto_match": False,
            "needs_confirmation": True,
            "message": None,
        }

        # 🔥 CORRECTION : Ne pas ignorer les textes courts comme "Item" ou "Well"
        if text_type == 'empty':
            result["message"] = "vide"
            result["action"] = "skip"
            _set_cache(cache_key, result)
            return result

        if text_type == 'noise':
            result["message"] = "bruit OCR"
            result["action"] = "skip"
            _set_cache(cache_key, result)
            return result

        if text_type == 'doc_ref':
            result["message"] = "référence document"
            result["action"] = "skip"
            _set_cache(cache_key, result)
            return result

        # Match rapide
        quick_result = self._quick_match(text_clean, db_items)
        if quick_result["matched"]:
            item = quick_result["item"]
            result.update({
                "action": "high_confidence",
                "auto_match": True,
                "item_id": item.id_item,
                "libelle": item.libelle_canonique,
                "confiance": quick_result["score"],
                "score": quick_result["score"],
                "needs_confirmation": False,
                "niveau": quick_result["level"],
                "message": None,
            })
            _set_cache(cache_key, result)
            return result

        # Cas nombre
        if text_type == 'number':
            get_number_variants, _ = _nums()
            variants = get_number_variants(text_clean)
            for item in db_items:
                if set(variants) & set(get_number_variants(item.libelle_canonique)):
                    result.update({
                        "action": "high_confidence",
                        "auto_match": True,
                        "item_id": item.id_item,
                        "libelle": item.libelle_canonique,
                        "confiance": 1.0,
                        "score": 1.0,
                        "needs_confirmation": False,
                        "niveau": "exact",
                        "message": None,
                    })
                    _set_cache(cache_key, result)
                    return result
            result["action"] = "create_new"
            result["auto_match"] = False
            result["message"] = "Nombre non trouvé"
            _set_cache(cache_key, result)
            return result

        # Traitement complet (pour les textes longs)
        # 🔥 CORRECTION : Pour les textes courts comme "Item", on ne fait pas le traitement complet
        if len(text_clean) < 4:
            result["action"] = "create_new"
            result["message"] = "Texte trop court"
            _set_cache(cache_key, result)
            return result

        try:
            normalize_text = _norm()
            get_number_variants, words_to_number = _nums()
            expand_synonyms, _vocab_cache, _ = _syns()
            universal_corrector = _corr()

            texte_corrige = universal_corrector.correct_text(text_clean, db_items[:50], concession_id)
            result["texte_corrige"] = texte_corrige

            texte_traduit = self._translate_if_needed(texte_corrige)
            result["texte_traduit"] = texte_traduit

            texte_normalise = normalize_text(texte_traduit)
            result["texte_normalise"] = texte_normalise

            numeric_value = words_to_number(texte_normalise)
            if numeric_value is not None:
                texte_normalise = str(numeric_value)
                result["texte_normalise"] = texte_normalise

            variantes_composees = decompose_texte_compose(texte_normalise)[:5]
            vocab_cache = _vocab_cache.get(concession_id)
            variants = expand_synonyms(texte_normalise, vocab_cache=vocab_cache)[:5]

            if _EMBEDDING_AVAILABLE() and concession_index is not None:
                encode_with_variants, _, _ = _emb()
                emb = encode_with_variants(texte_normalise, variants)
                if emb is not None:
                    result["embedding"] = emb.tobytes()

            match_result = self.engine.match(
                query=text_clean,
                items=db_items[:100],
                normalized_query=texte_normalise,
                concession_index=concession_index if _EMBEDDING_AVAILABLE() else None,
                variants_composees=variantes_composees[:3],
            )

            if match_result.matched and match_result.score >= 0.85:
                action = "high_confidence"
                auto_match = True
                needs_confirmation = False
            elif match_result.matched and match_result.score >= 0.55:
                action = "needs_validation"
                auto_match = False
                needs_confirmation = True
            else:
                action = "create_new"
                auto_match = False
                needs_confirmation = True

            result.update({
                "action": action,
                "auto_match": auto_match,
                "item_id": match_result.item_id if match_result.matched else None,
                "libelle": match_result.item_label if match_result.matched else None,
                "confiance": match_result.score,
                "score": match_result.score,
                "needs_confirmation": needs_confirmation,
                "niveau": match_result.level.value if match_result.matched else None,
                "candidates": match_result.candidates[:3] if match_result.candidates else [],
                "message": (f"Correspondance à {round(match_result.score * 100)}%"
                           if match_result.matched and needs_confirmation else None),
            })

        except Exception as e:
            _log.error(f"❌ Erreur pipeline: {e}")
            result["message"] = f"Erreur: {str(e)[:100]}"
            result["action"] = "error"

        _set_cache(cache_key, result)
        return result

    def process_item_fast(self, text, db_items, concession_id, concession_index=None):
        return self.process_item(text, db_items, concession_id, concession_index)

    def process_batch(self, texts: List[str], db_items: list, concession_id: int) -> List[Dict[str, Any]]:
        expand_synonyms, _vocab_cache, precompute_vocab_embeddings = _syns()

        if db_items and concession_id not in _vocab_cache:
            all_words = [w for item in db_items[:200] for w in item.libelle_recherche.split()]
            precompute_vocab_embeddings(concession_id, all_words[:500])

        concession_index = None
        if _EMBEDDING_AVAILABLE() and db_items:
            _, get_or_build_index, _ = _emb()
            concession_index = get_or_build_index(
                concession_id=concession_id,
                item_ids=[i.id_item for i in db_items[:200]],
                item_texts=[i.libelle_recherche for i in db_items[:200]],
                item_labels=[i.libelle_canonique for i in db_items[:200]],
            )

        return [self.process_item(t, db_items[:200], concession_id, concession_index) for t in texts]


# ── Singleton lazy ─────────────────────────────────────────────────────────────
_pipeline_instance = None

def get_pipeline():
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = SemanticPipeline()
    return _pipeline_instance


class _LazyPipeline:
    def __getattr__(self, name):
        return getattr(get_pipeline(), name)

    def __call__(self, *args, **kwargs):
        return get_pipeline()(*args, **kwargs)


semantic_pipeline = _LazyPipeline()


def get_cache_stats() -> Dict[str, int]:
    return {"hits": _cache_hits, "misses": _cache_misses, "size": len(_match_cache)}

def clear_cache() -> None:
    global _match_cache, _cache_hits, _cache_misses
    _match_cache = {}
    _cache_hits = 0
    _cache_misses = 0