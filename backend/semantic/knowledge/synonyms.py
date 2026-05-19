"""
Dictionnaire de synonymes métier pour le domaine pétrolier + synonymes généraux.
"""
import logging
from typing import Dict, List, Set, Optional
import numpy as np

from ..embeddings.embedder import _get_model

_log = logging.getLogger(__name__)

# ── Synonymes généraux (anglais/français) ──────────────────────────────────
GENERAL_SYNONYMS: List[Set[str]] = [
    {"laptop", "ordinateur", "portable", "notebook", "pc portable"},
    {"computer", "ordinateur", "pc", "unité centrale"},
    {"phone", "téléphone", "portable", "smartphone"},
    {"printer", "imprimante"},
    {"monitor", "écran", "moniteur"},
    {"keyboard", "clavier"},
    {"mouse", "souris"},
    {"software", "logiciel"},
    {"hardware", "matériel"},
    {"network", "réseau"},
    {"server", "serveur"},
    {"database", "base de données"},
    {"invoice", "facture"},
    {"bill", "facture"},
    {"payment", "paiement", "règlement"},
    {"amount", "montant", "somme"},
    {"total", "total", "montant total", "somme totale"},
    {"tax", "tva", "taxe"},
    {"discount", "remise", "rabais", "réduction"},
    {"good morning", "bonjour", "hello", "salut"},
    {"good afternoon", "bonjour"},
    {"good evening", "bonsoir"},
    {"hello", "bonjour", "salut"},
    {"hi", "bonjour", "salut"},
    {"thanks", "merci"},
    {"thank you", "merci"},
]

# ── Abréviations techniques (base manuelle) ──────────────────────────────────
CORE_SYNONYM_GROUPS: List[Set[str]] = [
    {"d&c", "drilling and completion"},
    {"w/o", "workover"},
    {"ta", "turnaround"},
    {"cpf", "central processing facility"},
    {"esdv", "emergency shutdown valve"},
    {"fgr", "flare gas recovery"},
    {"ytd", "year to date"},
    {"cme", "current month expenditure"},
    {"capex", "capital expenditure"},
    {"opex", "operating expenditure"},
    {"hse", "health safety environment"},
    {"pi", "production information"},
    {"dcs", "distributed control system"},
    {"g&a", "general and administration"},
    # Ajout des abréviations avec contexte
    {"etap", "etap share", "etap share 50%", "etap 50%", "etap 50"},
    {"omv", "omv share", "omv share 50%", "omv 50%", "omv 50"},
    {"jib", "joint interest billing", "joint interest bill"},
]

# Fusionner tous les synonymes
ALL_SYNONYM_GROUPS = GENERAL_SYNONYMS + CORE_SYNONYM_GROUPS

_CORE_INDEX: Dict[str, Set[str]] = {}
for _group in ALL_SYNONYM_GROUPS:
    for _word in _group:
        _CORE_INDEX[_word.lower()] = _group

# ── Cache des synonymes détectés par IA ──────────────────────────────────────
_vocab_cache: Dict[int, Dict[str, np.ndarray]] = {}
_smart_cache: Dict[str, List[str]] = {}
SYNONYM_THRESHOLD = 0.80


def precompute_vocab_embeddings(concession_id: int, words: List[str]) -> None:
    """Pré-calcule les embeddings du vocabulaire d'une concession."""
    if not words:
        return

    model = _get_model()
    if model is None:
        return

    unique_words = list(set(words))
    embeddings = model.encode(
        unique_words,
        convert_to_numpy=True,
        normalize_embeddings=True,
        batch_size=32,
    )
    _vocab_cache[concession_id] = {
        word: emb.astype("float32")
        for word, emb in zip(unique_words, embeddings)
    }
    _log.info(f"Vocabulaire pré-calculé : {len(unique_words)} mots (concession {concession_id})")


def get_synonyms(word: str) -> Set[str]:
    """Retourne les synonymes d'un mot."""
    word_lower = word.lower().strip()

    # 1. Synonymes généraux et abréviations techniques
    core_group = _CORE_INDEX.get(word_lower)
    if core_group:
        return core_group - {word_lower}

    # 2. Cache intelligent (synonymes détectés par IA)
    if word_lower in _smart_cache:
        return set(_smart_cache[word_lower])

    return set()


def expand_synonyms(
    text: str,
    vocab_cache: Optional[Dict[str, np.ndarray]] = None,
    max_variants: int = 12,
) -> List[str]:
    """Retourne le texte original + toutes ses variantes synonymiques."""
    tokens = text.split()
    variants: Set[str] = {text}

    # 1. Synonymes directs (unigrammes)
    for i, token in enumerate(tokens):
        if token in _CORE_INDEX:
            for syn in _CORE_INDEX[token]:
                if len(variants) >= max_variants:
                    break
                variants.add(" ".join(tokens[:i] + [syn] + tokens[i + 1:]))

    # 2. Bigrammes
    if len(variants) < max_variants:
        for i in range(len(tokens) - 1):
            phrase = f"{tokens[i]} {tokens[i+1]}"
            if phrase in _CORE_INDEX:
                for syn in _CORE_INDEX[phrase]:
                    variants.add(" ".join(tokens[:i] + syn.split() + tokens[i + 2:]))

    # 3. Détection IA par similarité cosinus
    if vocab_cache and len(variants) < max_variants:
        for token in tokens:
            if token in _CORE_INDEX or token in _smart_cache:
                continue

            if token in vocab_cache:
                token_emb = vocab_cache[token]
                similarities = []

                for word, emb in vocab_cache.items():
                    if word == token:
                        continue
                    sim = float(np.dot(token_emb, emb))
                    if sim >= SYNONYM_THRESHOLD:
                        similarities.append((word, sim))

                similarities.sort(key=lambda x: -x[1])
                _smart_cache[token] = [w for w, _ in similarities[:5]]

                for syn in _smart_cache[token]:
                    if len(variants) >= max_variants:
                        break
                    idx = tokens.index(token)
                    variants.add(" ".join(tokens[:idx] + [syn] + tokens[idx + 1:]))

    return list(variants)


def add_manual_synonyms(word: str, synonyms: List[str]) -> None:
    """Ajoute manuellement des synonymes pour un mot."""
    _smart_cache[word.lower()] = [s.lower() for s in synonyms]


def clear_cache() -> None:
    """Vide tous les caches."""
    _vocab_cache.clear()
    _smart_cache.clear()