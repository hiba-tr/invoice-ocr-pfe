"""
ocr_corrector.py — Correction post-OCR universelle
Apprend du document et corrige sans aucun mot-clé codé en dur.
"""
import re
import logging
from typing import List, Dict, Tuple, Optional
from collections import Counter
import unicodedata

_log = logging.getLogger(__name__)


class OcrCorrector:
    """
    Correcteur post-OCR universel.
    
    Fonctionnalités :
    - Apprentissage automatique du vocabulaire du document
    - Correction par similarité de Levenshtein + Jaccard
    - Fusion intelligente des lignes coupées
    - Normalisation des formats de nombres
    - Détection et correction des confusions OCR fréquentes
    """

    def __init__(self):
        self._vocabulary = None
        
        # Confusions OCR universelles (indépendantes du document)
        self._ocr_confusions = {
            '0': 'O', 'O': '0',
            '1': 'l', 'l': '1', 'I': '1',
            '2': 'Z', 'Z': '2',
            '5': 'S', 'S': '5',
            '8': 'B', 'B': '8',
            '|': 'I',
            '[': '(', ']': ')',
            '{': '(', '}': ')',
        }

    def learn_document(self, text: str) -> None:
        """
        Apprend le vocabulaire et les patterns du document.
        Doit être appelé avant correct_text() pour de meilleurs résultats.
        """
        # Extraire tous les mots de 3+ lettres
        words = re.findall(r'\b[A-Za-zÀ-ÿ0-9/&.-]{3,}\b', text)
        
        # Filtrer les mots qui ressemblent à du vrai texte (pas du bruit)
        real_words = [
            w for w in words 
            if not re.match(r'^[0-9./-]+$', w)  # Pas que des chiffres/symboles
        ]
        
        self._vocabulary = Counter(w.lower() for w in real_words)
        
        # Garder seulement les mots qui apparaissent au moins 2 fois
        self._vocabulary = Counter({
            w: c for w, c in self._vocabulary.items() if c >= 2
        })
        
        _log.info("Vocabulaire appris : %d mots fréquents", len(self._vocabulary))

    def correct_text(self, text: str) -> str:
        """
        Corrige un texte en utilisant le vocabulaire appris.
        """
        if not text:
            return text
        
        # 1. Normaliser les caractères Unicode
        text = unicodedata.normalize('NFKC', text)
        
        # 2. Corriger les mots mal lus
        if self._vocabulary and len(self._vocabulary) > 0:
            text = self._correct_words_with_vocabulary(text)
        
        # 3. Corriger le format des nombres
        text = self._correct_number_format(text)
        
        # 4. Nettoyer les espaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 5. Corriger la ponctuation
        text = self._fix_punctuation_spacing(text)
        
        return text

    def _correct_words_with_vocabulary(self, text: str) -> str:
        """
        Corrige les mots mal lus en les comparant au vocabulaire du document.
        Utilise la similarité de chaînes pour trouver la meilleure correspondance.
        """
        words = re.findall(r'\b[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9]{2,}\b', text)
        words_lower = [w.lower() for w in words]
        
        corrected = {}
        
        for i, word in enumerate(words_lower):
            # Chercher dans le vocabulaire par similarité
            best_match = self._find_similar_word(word)
            
            if best_match and best_match != word:
                # Retrouver la casse originale
                if words[i].isupper():
                    corrected[words[i]] = best_match.upper()
                elif words[i][0].isupper():
                    corrected[words[i]] = best_match.capitalize()
                else:
                    corrected[words[i]] = best_match
        
        # Appliquer les corrections
        for wrong, right in corrected.items():
            if wrong != right:
                text = text.replace(wrong, right)
                _log.debug("Corrigé : '%s' → '%s'", wrong, right)
        
        return text

    def _find_similar_word(self, word: str, threshold: float = 0.65) -> Optional[str]:
        """
        Trouve le mot le plus similaire dans le vocabulaire.
        """
        if not self._vocabulary or word in self._vocabulary:
            return word
        
        best_match = None
        best_score = threshold
        
        for vocab_word in self._vocabulary:
            # Calculer la similarité
            similarity = self._word_similarity(word, vocab_word)
            
            # Bonus de fréquence
            freq_bonus = min(self._vocabulary[vocab_word] / 20, 0.15)
            score = similarity + freq_bonus
            
            if score > best_score:
                best_score = score
                best_match = vocab_word
        
        return best_match

    def _word_similarity(self, word1: str, word2: str) -> float:
        """
        Calcule la similarité entre deux mots.
        Combine similarité de Levenshtein et similarité de bigrammes (Jaccard).
        """
        if word1 == word2:
            return 1.0
        if abs(len(word1) - len(word2)) > 3:
            return 0.0
        
        max_len = max(len(word1), len(word2))
        if max_len == 0:
            return 0.0
        
        # Distance de Levenshtein
        distance = self._levenshtein(word1, word2)
        levenshtein_sim = 1 - (distance / max_len)
        
        # Similarité de Jaccard sur les bigrammes
        bigrams1 = set(word1[i:i+2] for i in range(len(word1)-1))
        bigrams2 = set(word2[i:i+2] for i in range(len(word2)-1))
        
        if not bigrams1 or not bigrams2:
            return levenshtein_sim
        
        intersection = bigrams1 & bigrams2
        union = bigrams1 | bigrams2
        jaccard_sim = len(intersection) / len(union) if union else 0
        
        # Pondération : 60% Levenshtein, 40% Jaccard
        return 0.6 * levenshtein_sim + 0.4 * jaccard_sim

    def _levenshtein(self, s1: str, s2: str) -> int:
        """Distance de Levenshtein optimisée."""
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        prev = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(
                    prev[j + 1] + 1,      # insertion
                    curr[j] + 1,            # deletion
                    prev[j] + (c1 != c2)    # substitution
                ))
            prev = curr
        
        return prev[-1]

    def _correct_number_format(self, text: str) -> str:
        """
        Corrige les formats de nombres mal lus par l'OCR.
        Ex: "148.271.43" → "148,271.43"
        """
        def fix_number(match):
            num = match.group(0)
            
            # Si plusieurs points, le dernier est probablement le séparateur décimal
            if num.count('.') > 1 and ',' not in num:
                last_dot = num.rfind('.')
                before = num[:last_dot].replace('.', ',')
                after = num[last_dot:]
                return before + after
            
            # Parenthèses → montant négatif
            if num.startswith('(') and num.endswith(')'):
                inner = num[1:-1]
                return '-' + inner
            
            return num
        
        # Pattern : nombre avec points et éventuelles parenthèses
        pattern = re.compile(r'\(?\d{1,3}(?:\.\d{3})+(?:\.\d{2})?\)?')
        return pattern.sub(fix_number, text)

    def _fix_punctuation_spacing(self, text: str) -> str:
        """Corrige l'espacement autour de la ponctuation."""
        # Espace après virgule/point si collé à un mot
        text = re.sub(r'([.,;:!?])(\w)', r'\1 \2', text)
        # Pas d'espace avant la ponctuation
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        return text

    def merge_broken_lines(self, lines: List[str]) -> List[str]:
        """
        Fusionne les lignes coupées par l'OCR.
        Critères :
        - Ligne qui commence par une minuscule
        - Ligne très courte (1-2 mots)
        - Ligne qui commence par un nombre
        """
        if not lines:
            return []
        
        merged = []
        buffer = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                if buffer:
                    merged.append(buffer)
                    buffer = ""
                continue
            
            should_merge = False
            
            if buffer:
                # Règle 1 : commence par une minuscule → suite de phrase
                if len(line) > 0 and line[0].islower():
                    should_merge = True
                # Règle 2 : ligne très courte (1-2 tokens)
                elif len(line.split()) <= 2 and not self._is_section_or_header(line):
                    should_merge = True
                # Règle 3 : ligne qui commence par un nombre
                elif re.match(r'^\d', line) and len(line.split()) <= 3:
                    should_merge = True
            
            if should_merge:
                buffer += " " + line
            else:
                if buffer:
                    merged.append(buffer)
                buffer = line
        
        if buffer:
            merged.append(buffer)
        
        return merged

    def _is_section_or_header(self, text: str) -> bool:
        """Détecte si une ligne est probablement un en-tête ou une section."""
        # Ligne courte en majuscules
        if text.isupper() and len(text) > 3:
            return True
        # Ligne numérotée
        if re.match(r'^[\d]+[.)]\s', text):
            return True
        return False

    def extract_line_items(self, lines: List[str]) -> List[Dict]:
        """
        Extrait les items (description + valeurs) de chaque ligne.
        """
        items = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Séparer description et valeurs
            description, valeurs = self._split_description_values(line)
            
            if description:
                items.append({
                    'description': description,
                    'valeurs': valeurs,
                    'is_section': self._is_section_or_header(description),
                })
        
        return items

    def _split_description_values(self, line: str) -> Tuple[str, List[float]]:
        tokens = line.split()
        
        description_parts = []
        valeurs = []
        i = 0
        
        while i < len(tokens):
            token = tokens[i]
            
            # Essayer de parser le token seul
            num = self._parse_number(token)
            
            if num is not None:
                valeurs.append(num)
                i += 1
            elif token.startswith('(') and not token.endswith(')'):
                # Parenthese ouvrante -> chercher la fermeture
                combined = token
                j = i + 1
                while j < len(tokens) and not tokens[j].endswith(')'):
                    combined += tokens[j]
                    j += 1
                if j < len(tokens):
                    combined += tokens[j]
                    num = self._parse_number(combined)
                    if num is not None:
                        valeurs.append(num)
                        i = j + 1
                        continue
                description_parts.append(token)
                i += 1
            else:
                description_parts.append(token)
                i += 1
        
        description = ' '.join(description_parts).strip()
        return description, valeurs

    def _parse_number(self, token: str) -> Optional[float]:
        if not token:
            return None
        
        original = token.strip()
        token = original
        
        # Detecter le signe negatif
        is_negative = False
        if token.startswith('(') and token.endswith(')'):
            is_negative = True
            token = token[1:-1]
        elif token.startswith('-'):
            is_negative = True
            token = token[1:]
        
        # Supprimer les symboles monetaires
        token = re.sub(r'[€$£¥]', '', token).strip()
        
        # Verifier si c'est un nombre (peut contenir des chiffres, points, virgules, espaces)
        if not re.match(r'^[\d.,\s]+$', token):
            return None
        
        # Nettoyer
        token = token.replace(' ', '').replace('\u00a0', '')
        
        # Gerer les formats
        if token.count('.') > 1 and token.count(',') == 0:
            token = token.replace('.', '')
        elif token.count(',') > 1 and token.count('.') == 0:
            token = token.replace(',', '')
        elif '.' in token and ',' in token:
            if token.rfind(',') > token.rfind('.'):
                token = token.replace('.', '').replace(',', '.')
            else:
                token = token.replace(',', '')
        elif ',' in token and '.' not in token:
            parts = token.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                token = token.replace(',', '.')
            else:
                token = token.replace(',', '')
        
        # Essayer de parser des parties separement (cas: "148, 43")
        # Si le token contient encore une virgule avec espace avant
        if not token or token == original:
            return None
        
        try:
            value = float(token)
            return -value if is_negative else value
        except ValueError:
            return None
        