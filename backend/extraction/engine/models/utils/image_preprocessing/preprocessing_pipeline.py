"""
preprocessing_pipeline.py — Pipeline de preprocessing complet
Combine image_preprocessor + invoice_enhancer + ocr_corrector
"""
import logging
from typing import  Dict, Any
from PIL import Image

from .image_preprocessor import ImagePreprocessor, assess_image_quality
from .invoice_enhancer import InvoiceEnhancer
from .ocr_corrector import OcrCorrector
from .financial_nlp import FinancialNLP

_log = logging.getLogger(__name__)


class PreprocessingPipeline:
    """
    Pipeline complet de preprocessing pour factures.
    
    Étapes :
    1. Évaluation de la qualité d'image
    2. Amélioration spécifique facture (deskew, contraste)
    3. Preprocessing adaptatif (débruitage, netteté, SR)
    4. Correction post-OCR intelligente
    5. Extraction structurée des items
    """

    def __init__(self):
        self.image_preprocessor = ImagePreprocessor()
        self.invoice_enhancer = InvoiceEnhancer()
        self.ocr_corrector = OcrCorrector()
        self.financial_nlp = FinancialNLP()

    def process_image(self, image: Image.Image) -> Image.Image:
        """
        Traite une image pour optimiser l'OCR.
        """
        quality = assess_image_quality(image)
        blur = quality['blur_score']
        _log.info("Qualité image : blur=%.1f, brightness=%.1f", blur, quality['brightness'])
        
        # Toujours appliquer l'amélioration facture
        enhanced = self.invoice_enhancer.enhance_for_ocr(image)
        
        # Preprocessing adaptatif selon la qualité
        if blur > 1000:
            _log.info("Image nette → pas de preprocessing supplémentaire")
        else:
            enhanced = self.image_preprocessor.get_enhanced_image(enhanced)
        
        return enhanced

    def process_text(self, text: str, learn: bool = True) -> Dict[str, Any]:
        if learn:
            self.ocr_corrector.learn_document(text)
        
        corrected_text = self.ocr_corrector.correct_text(text)
        raw_lines = corrected_text.split('\n')
        merged_lines = self.ocr_corrector.merge_broken_lines(raw_lines)
        items = self.ocr_corrector.extract_line_items(merged_lines)
        items = [item for item in items if item['description']]
        
        # NLP : identifier les colonnes et extraire
        columns_info = self.financial_nlp.identify_columns(merged_lines)
        structured_items = self.financial_nlp.extract_items(merged_lines) if merged_lines else items
        
        return {
            'corrected_text': corrected_text,
            'lines': merged_lines,
            'items': structured_items or items,
            'vocabulary_size': len(self.ocr_corrector._vocabulary) if self.ocr_corrector._vocabulary else 0,
            'columns': [c['name'] for c in columns_info] if columns_info else [],
        }