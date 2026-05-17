"""
language_detector.py — Détection rapide de langue pour orienter le choix OCR
"""
import re
from collections import Counter

class LanguageDetector:
    """
    Détecte la langue d'un texte pour choisir le meilleur moteur OCR.
    """

    # Mots-outils très fréquents par langue
    STOPWORDS = {
        'fr': [
            'le', 'la', 'les', 'des', 'est', 'une', 'pour', 'dans', 'sur', 'avec',
            'facture', 'devis', 'montant', 'date', 'client', 'numéro', 'total',
            'du', 'au', 'par', 'en', 'et', 'ou', 'ce', 'il', 'à', 'un',
        ],
        'en': [
            'the', 'and', 'for', 'are', 'was', 'with', 'this', 'that', 'from',
            'invoice', 'amount', 'date', 'customer', 'number', 'total', 'bill',
            'of', 'to', 'in', 'is', 'it', 'as', 'by', 'on', 'be', 'at',
        ],
        'ar': [
            'في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'ذلك', 'كان', 'هي',
            'فاتورة', 'مبلغ', 'تاريخ', 'المجموع', 'رقم', 'ما', 'لا', 'كل',
        ],
    }

    # Patterns de caractères spécifiques
    CHAR_PATTERNS = {
        'ar': re.compile(r'[\u0600-\u06FF]'),
        'fr': re.compile(r'[éèêëàâîïôùûçœæÉÈÊËÀÂÎÏÔÙÛÇ]'),
    }

    def detect(self, text: str) -> str:
        """
        Détecte la langue principale.
        
        Returns: 'fr', 'en', 'ar', ou 'unknown'
        """
        if not text or len(text.strip()) < 20:
            return 'unknown'

        text_lower = text.lower()

        # 1. Détection par caractères (prioritaire pour l'arabe)
        for lang, pattern in self.CHAR_PATTERNS.items():
            matches = pattern.findall(text)
            if lang == 'ar' and len(matches) > len(text) * 0.15:
                return 'ar'

        # 2. Détection par mots-outils
        scores = {}
        words = set(re.findall(r'\b\w+\b', text_lower))

        for lang, stopwords in self.STOPWORDS.items():
            score = sum(1 for w in stopwords if w in words)
            if score > 0:
                scores[lang] = score

        # Bonus pour les accents français
        fr_accents = self.CHAR_PATTERNS.get('fr', re.compile(r'')).findall(text)
        if len(fr_accents) > 0:
            scores['fr'] = scores.get('fr', 0) + len(fr_accents)

        if scores:
            return max(scores, key=scores.get)

        # 3. Fallback : fréquence des lettres
        return self._fallback_detect(text_lower)

    def _fallback_detect(self, text: str) -> str:
        """Détection par fréquence de lettres."""
        letters = re.findall(r'[a-zà-ÿ]', text)
        if not letters:
            return 'unknown'

        freq = Counter(letters)
        total = sum(freq.values())
        fr_chars = sum(freq.get(c, 0) for c in 'éèêëàâîïôùûç')
        fr_ratio = fr_chars / total if total > 0 else 0

        return 'fr' if fr_ratio > 0.01 else 'en'

    def choose_ocr_engine(self, text: str) -> str:
        """
        Choisit le meilleur moteur OCR selon la langue.
        
        Returns: 'easyocr', 'rapidocr', 'tesseract'
        """
        lang = self.detect(text)

        mapping = {
            'fr': 'easyocr',       # EasyOCR pour le français
            'ar': 'easyocr',       # EasyOCR pour l'arabe
            'en': 'rapidocr',      # RapidOCR pour l'anglais
            'unknown': 'easyocr',  # Fallback
        }

        return mapping.get(lang, 'easyocr')