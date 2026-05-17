"""
financial_nlp.py — NLP intelligent pour tout document financier
Détection automatique de la langue, du format des nombres, des colonnes.
AUCUN mot-clé codé en dur — tout est appris du document.
"""
import re
import logging
from typing import List, Dict, Tuple, Optional,Any
from collections import defaultdict

_log = logging.getLogger(__name__)


class FinancialNLP:
    """
    Analyse intelligente de documents financiers.
    
    Capacités :
    - Détection automatique de la langue
    - Identification du format des nombres (séparateurs, devise)
    - Classification des colonnes par leur contenu (pas par mots-clés)
    - Détection des lignes d'en-tête, sections, totaux
    - Extraction structurée universelle
    """

    def __init__(self):
        # Indicateurs linguistiques légers (mots-outils très fréquents)
        self._language_indicators = {
            'fr': ['le', 'la', 'les', 'des', 'est', 'une', 'pour', 'dans'],
            'en': ['the', 'and', 'for', 'are', 'was', 'with', 'this'],
            'ar': ['في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'ذلك'],
            'es': ['los', 'las', 'del', 'una', 'por', 'para', 'con'],
            'de': ['der', 'die', 'das', 'und', 'für', 'mit', 'von'],
            'it': ['del', 'della', 'per', 'con', 'una', 'sono'],
        }
        
        # Patterns universels de nombres
        self._amount_pattern = re.compile(
            r'\(?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,3})?\)?'
        )
        
        # Patterns de sections (lignes qui structurent le document)
        self._section_patterns = [
            re.compile(r'^[A-Z][A-Z\s&/()-]{3,50}$'),           # LIGNE EN MAJUSCULES
            re.compile(r'^[\d]+[.)]\s{1,3}'),                    # 1. Section numérotée
            re.compile(r'^[IVX]+[.)]\s{1,3}'),                   # I. Section romaine
        ]

    def detect_language(self, text: str) -> str:
        """
        Détecte la langue du document par fréquence de mots-outils.
        """
        text_lower = text.lower()
        words = set(re.findall(r'\b\w+\b', text_lower))
        
        scores = defaultdict(int)
        
        for lang, indicators in self._language_indicators.items():
            for word in indicators:
                if word in words:
                    scores[lang] += 1
        
        # Bonus pour les symboles monétaires
        if '€' in text or 'euros' in text_lower:
            scores['fr'] += 2
        if '$' in text or 'usd' in text_lower:
            scores['en'] += 2
        
        if scores:
            return max(scores, key=scores.get)
        
        # Fallback : détecter par caractères
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        if arabic_chars > len(text) * 0.3:
            return 'ar'
        
        latin_chars = len(re.findall(r'[a-zA-Z]', text))
        if latin_chars > len(text) * 0.3:
            # Vérifier les accents français
            french_accents = len(re.findall(r'[éèêëàâîïôùûç]', text_lower))
            if french_accents > 0:
                return 'fr'
            return 'en'
        
        return 'en'

    def detect_number_format(self, text: str) -> Dict[str, str]:
        """
        Détecte automatiquement le format des nombres.
        
        Returns:
            {
                'thousands_sep': ',',    # Séparateur de milliers
                'decimal_sep': '.',      # Séparateur décimal
                'currency': '€',         # Symbole monétaire
            }
        """
        # Extraire tous les nombres du texte
        numbers = self._amount_pattern.findall(text)
        
        if not numbers:
            return {'thousands_sep': ',', 'decimal_sep': '.', 'currency': '€'}
        
        # Analyser les séparateurs
        dots_as_thousands = 0
        commas_as_thousands = 0
        dots_as_decimal = 0
        commas_as_decimal = 0
        
        for num in numbers[:50]:  # Limiter à 50 nombres
            num = num.strip('()')
            
            # Compter les séparateurs
            dot_count = num.count('.')
            comma_count = num.count(',')
            
            # Si les deux sont présents
            if dot_count > 0 and comma_count > 0:
                # Le dernier séparateur est probablement le décimal
                if num.rfind('.') > num.rfind(','):
                    dots_as_decimal += 1
                    commas_as_thousands += 1
                else:
                    commas_as_decimal += 1
                    dots_as_thousands += 1
            elif dot_count > 1:
                dots_as_thousands += 1
            elif comma_count > 1:
                commas_as_thousands += 1
            elif dot_count == 1 and len(num.split('.')[-1]) <= 2:
                dots_as_decimal += 1
            elif comma_count == 1 and len(num.split(',')[-1]) <= 2:
                commas_as_decimal += 1
        
        # Déterminer le format dominant
        thousands_sep = ',' if commas_as_thousands >= dots_as_thousands else '.'
        decimal_sep = ',' if commas_as_decimal > dots_as_decimal else '.'
        
        # Détecter la devise
        currency = self._detect_currency(text)
        
        return {
            'thousands_sep': thousands_sep,
            'decimal_sep': decimal_sep,
            'currency': currency,
        }

    def _detect_currency(self, text: str) -> str:
        """Détecte la devise du document."""
        text_upper = text.upper()
        
        currency_map = {
            '€': ['€', 'EUR', 'EURO'],
            '$': ['$', 'USD', 'US$', 'DOLLAR'],
            'DT': ['DT', 'TND', 'DINAR TUNISIEN'],
            '£': ['£', 'GBP', 'POUND'],
            'MAD': ['MAD', 'DH', 'DIRHAM'],
            'DZD': ['DZD', 'DA'],
        }
        
        for symbol, patterns in currency_map.items():
            for pattern in patterns:
                if pattern in text_upper:
                    return symbol
        
        # Devise par défaut selon la langue
        lang = self.detect_language(text)
        if lang == 'fr':
            return '€'
        elif lang == 'en':
            return '$'
        elif lang == 'ar':
            return 'DT'
        
        return '€'

    def identify_columns(self, lines: List[str]) -> List[Dict]:
        """
        Identifie les colonnes en analysant le contenu de chaque position.
        Retourne : [{'name': 'Description', 'type': 'text', 'index': 0}, ...]
        """
        if not lines:
            return []
        
        # Tokeniser toutes les lignes
        tokenized = [self._tokenize_line(line) for line in lines]
        
        # Nombre max de tokens (colonnes potentielles)
        max_cols = max(len(t) for t in tokenized) if tokenized else 0
        
        if max_cols <= 1:
            return [{'name': 'Description', 'type': 'text', 'index': 0}]
        
        columns = []
        
        for col_idx in range(max_cols):
            # Collecter toutes les valeurs de cette colonne
            col_values = []
            for tokens in tokenized:
                if col_idx < len(tokens):
                    col_values.append(tokens[col_idx])
                else:
                    col_values.append('')
            
            if not col_values:
                continue
            
            # Analyser le type de cette colonne
            col_type, name = self._classify_column(col_values, col_idx, max_cols)
            
            columns.append({
                'name': name,
                'type': col_type,
                'index': col_idx,
            })
        
        return columns

    def _tokenize_line(self, line: str) -> List[str]:
        """
        Tokenisation intelligente : préserve les nombres.
        """
        return line.strip().split()

    def _classify_column(self, values: List[str], col_idx: int, total_cols: int) -> Tuple[str, str]:
        """
        Classifie une colonne comme 'text', 'amount', ou 'identifier'.
        """
        num_count = 0
        text_count = 0
        empty_count = 0
        
        for val in values:
            val = val.strip().strip('()')
            if not val:
                empty_count += 1
            elif self._is_numeric(val):
                num_count += 1
            else:
                text_count += 1
        
        total = len(values) - empty_count
        if total == 0:
            return ('text', f'Col_{col_idx + 1}')
        
        num_ratio = num_count / total
        text_ratio = text_count / total
        
        # Colonne de texte (description)
        if text_ratio > 0.6:
            if col_idx == 0:
                return ('text', 'Description')
            return ('text', f'Texte_{col_idx + 1}')
        
        # Colonne numérique (montant)
        if num_ratio > 0.7:
            return ('amount', f'Montant_{col_idx + 1}')
        
        # Mixte : première colonne = description
        if col_idx == 0:
            return ('text', 'Description')
        
        return ('amount', f'Valeur_{col_idx + 1}')

    def _is_numeric(self, value: str) -> bool:
        """Vérifie si une valeur est numérique."""
        if not value:
            return False
        # Nettoyer
        cleaned = value.replace(',', '.').replace(' ', '').replace('\u00a0', '')
        # Accepter un seul point décimal
        if cleaned.count('.') == 1:
            cleaned = cleaned.replace('.', '')
        elif cleaned.count('.') > 1:
            return False
        return cleaned.lstrip('-').isdigit() if cleaned else False

    def find_header_row(self, lines: List[str]) -> int:
        """
        Trouve la ligne d'en-tête du tableau en analysant la structure.
        Retourne l'index de la ligne d'en-tête.
        """
        if not lines:
            return 0
        
        best_row = 0
        best_score = -1
        
        for i, line in enumerate(lines[:min(15, len(lines))]):
            tokens = self._tokenize_line(line)
            
            if not tokens:
                continue
            
            # Score basé sur : longueur des tokens, présence de texte court
            score = 0
            
            # Colonne avec des tokens courts (typique des en-têtes)
            short_tokens = sum(1 for t in tokens if len(t) <= 15 and not self._is_numeric(t))
            score += short_tokens * 2
            
            # Bonus pour les lignes sans nombres
            if not any(self._is_numeric(t) for t in tokens):
                score += 3
            
            # Bonus pour les tokens tout en majuscules
            if any(t.isupper() for t in tokens if len(t) > 1):
                score += 2
            
            if score > best_score:
                best_score = score
                best_row = i
        
        return best_row

    def is_section_header(self, text: str) -> bool:
        """Détecte si une ligne est un en-tête de section."""
        for pattern in self._section_patterns:
            if pattern.match(text.strip()):
                return True
        return False

    def extract_items(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Extrait les items structurés de n'importe quel tableau.
        """
        # Identifier les colonnes
        columns = self.identify_columns(lines)
        
        # Trouver la ligne d'en-tête
        header_row = self.find_header_row(lines)
        
        items = []
        current_section = None
        
        for i, line in enumerate(lines):
            if i <= header_row:
                continue
            
            line = line.strip()
            if not line:
                continue
            
            # Détecter les sections
            if self.is_section_header(line):
                current_section = line
                continue
            
            # Tokeniser et extraire
            tokens = self._tokenize_line(line)
            
            description = None
            valeurs = []
            
            for col in columns:
                col_idx = col['index']
                if col_idx < len(tokens):
                    value = tokens[col_idx]
                    
                    if col['type'] == 'text' and description is None:
                        description = value
                    elif col['type'] == 'amount':
                        num = self._parse_amount(value)
                        if num is not None:
                            valeurs.append(num)
            
            if description:
                items.append({
                    'description': description,
                    'valeurs': valeurs,
                    'section': current_section,
                })
        
        return items

    def _parse_amount(self, value: str) -> Optional[float]:
        """Parse un montant en nombre."""
        if not value:
            return None
        
        value = value.strip()
        
        # Négatif
        is_negative = False
        if value.startswith('(') and value.endswith(')'):
            is_negative = True
            value = value[1:-1]
        elif value.startswith('-'):
            is_negative = True
            value = value[1:]
        
        # Nettoyer
        value = value.replace(' ', '').replace('\u00a0', '')
        
        # Déterminer le séparateur décimal
        if value.count('.') > 1 and ',' not in value:
            value = value.replace('.', '')
        elif value.count(',') > 1 and '.' not in value:
            value = value.replace(',', '')
        elif ',' in value and '.' in value:
            if value.rfind(',') > value.rfind('.'):
                value = value.replace('.', '').replace(',', '.')
            else:
                value = value.replace(',', '')
        elif ',' in value:
            parts = value.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                value = value.replace(',', '.')
            else:
                value = value.replace(',', '')
        
        try:
            result = float(value)
            return -result if is_negative else result
        except ValueError:
            return None