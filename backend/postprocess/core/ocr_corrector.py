"""
postprocess/core/ocr_corrector.py
==================================
Correction générique des artefacts OCR et normalisation du texte.

Fonctionnalités :
  - Normalisation Unicode + compactage des espaces
  - Correction intelligente des erreurs de reconnaissance (O→0, I→1, etc.),
    uniquement lorsque le texte est un montant ou un code numérique
  - Suppression itérative des artefacts de fusion (plusieurs préfixes empilés)
  - Traitement spécifique du bug "ff Prod" de Docling, protégé par des frontières de mot
  - Nettoyage des montants qui préserve la structure décimale
  - Logging détaillé pour debug et audits

Tous les traitements sont **indépendants du domaine** et s'appliquent à tout type de facture.
"""

import re
import unicodedata
import logging
from typing import Optional, List

_log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 1. Normalisation des caractères Unicode
# ----------------------------------------------------------------------
_UNICODE_MAP = {
    "\u00a0": " ",     # espace insécable
    "\u2013": "-",     # tiret demi‑cadratin
    "\u2014": "-",     # tiret cadratin
    "\u2019": "'",     # apostrophe typographique
    "\u202f": " ",     # espace fine insécable
    "\u00b0": " deg ", # symbole degré
}
_WHITESPACE_RE = re.compile(r"\s{2,}")

def clean_text(text: str) -> str:
    """Normalise l'unicode et compacte les espaces multiples."""
    if not text:
        return ""
    original = text
    text = unicodedata.normalize("NFC", text)
    for src, dst in _UNICODE_MAP.items():
        text = text.replace(src, dst)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if text != original:
        _log.debug(f"clean_text: '{original}' → '{text}'")
    return text

# ----------------------------------------------------------------------
# 2. Correction intelligente des erreurs OCR
# ----------------------------------------------------------------------
# Dictionnaire des confusions classiques dans les montants/codes.
_OCR_FIXES = {
    'O': '0',   # O confondu avec 0
    'I': '1',   # I confondu avec 1
    'l': '1',   # l confondu avec 1
    'S': '5',   # S confondu avec 5
    'B': '8',   # B confondu avec 8
}

def _looks_like_numeric(text: str) -> bool:
    """
    Vérifie si le texte est très probablement un montant ou un code numérique.
    On accepte : chiffres, lettres de l'OCR fix, signes, séparateurs, espaces.
    Cela évite de corriger des mots comme "BUDGET".
    """
    return bool(re.fullmatch(r"[\dOIlSB\s\.\,\-\(\)€$£%/:+A-Z]+", text))

def fix_common_ocr_errors(text: str) -> str:
    """
    Remplace les caractères mal reconnus par leur équivalent numérique,
    uniquement si le texte semble être un montant ou un code.
    """
    if not text:
        return text
    # On n'agit que sur des chaînes à fort contenu numérique
    if not _looks_like_numeric(text):
        return text
    fixed = text
    for wrong, right in _OCR_FIXES.items():
        fixed = fixed.replace(wrong, right)
    if fixed != text:
        _log.debug(f"fix_ocr_errors: '{text}' → '{fixed}'")
    return fixed

# ----------------------------------------------------------------------
# 3. Suppression itérative des artefacts de fusion
# ----------------------------------------------------------------------
_ARTIFACT_PATTERNS = [
    # Numérotation parasite en début de ligne
    re.compile(r"^\d{1,4}\s*[-–—]\s*"),
    # Labels techniques (ex: "C01 ", "L002:")
    re.compile(r"^[A-Z]{1,2}\d{2,4}[\s:]+", re.I),
    # Résidus de pagination
    re.compile(r"^(?:Page\s+\d+[\s:]+|Continued\s*)", re.I),
    # Puces et symboles isolés
    re.compile(r"^[\*\-\•\>\|\/]{1,3}\s+"),
    # Préfixes de colonne explicites
    re.compile(r"^(?:Description|Desc|Designation|Libellé)\s*[:;]\s*", re.I),
    # Staff Prod (variante)
    re.compile(r"^Staff\s+Prod\s+\S+\s+", re.I),
]

def remove_artifacts(text: str, custom_patterns: Optional[List[re.Pattern]] = None) -> str:
    """
    Supprime itérativement tous les préfixes parasites reconnus.
    Continue tant que la chaîne change.
    """
    if not text:
        return ""
    patterns = custom_patterns if custom_patterns is not None else _ARTIFACT_PATTERNS
    cleaned = clean_text(text)
    changed = True
    while changed:
        changed = False
        for pat in patterns:
            m = pat.search(cleaned)
            if m:
                _log.debug(f"Artifact removed with '{pat.pattern}': '{m.group()}'")
                cleaned = cleaned[m.end():].strip()
                changed = True
                break   # réessayer depuis le début avec la chaîne modifiée
    return cleaned

# ----------------------------------------------------------------------
# 4. Traitement spécifique de l'artefact "ff Prod" (Docling)
# ----------------------------------------------------------------------
# Utilisation de \b pour éviter de matcher "Office Product"
_FF_PROD_RE = re.compile(r"\bff\s+[Pp]rod\b\s+")

def _remove_ff_prod_artifact(text: str) -> str:
    """Supprime tout ce qui précède la dernière occurrence de 'ff Prod'."""
    matches = list(_FF_PROD_RE.finditer(text))
    if matches:
        return text[matches[-1].end():].strip()
    return text

def clean_description(text: str) -> str:
    """
    Nettoie une description de ligne de tableau :
    1. Suppression itérative des artefacts généraux
    2. Correction du bug 'ff Prod'
    """
    if not text:
        return ""
    cleaned = remove_artifacts(text)
    cleaned = _remove_ff_prod_artifact(cleaned)
    # Nettoyage final des espaces résiduels
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned

# ----------------------------------------------------------------------
# 5. Normalisation des montants (texte brut → forme propre)
# ----------------------------------------------------------------------
def normalize_amount_text(text: str) -> str:
    """
    Prépare un texte susceptible d'être un montant pour conversion numérique.
    - Corrige les erreurs OCR courantes
    - Supprime les espaces superflus (car MonetaryAmount les gérera)
    - Conserve les séparateurs décimaux
    """
    if not text:
        return "-"
    t = text.strip()
    if re.match(r"^-\s*-$", t):      # cellule vide représentée par "--"
        return "-"
    # Correction OCR ciblée
    t = fix_common_ocr_errors(t)
    # Suppression des espaces uniquement si la chaîne est majoritairement numérique
    if _looks_like_numeric(t):
        t = re.sub(r"\s+", "", t)
    else:
        # Pour les textes non numériques, on garde les espaces mais on compacte
        t = _WHITESPACE_RE.sub(" ", t).strip()
    _log.debug(f"normalize_amount: '{text}' → '{t}'")
    return t