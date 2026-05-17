"""
invoice_enhancer.py — Améliorations d'image spécifiques aux factures
Deskew, contraste adaptatif, détection de zones de tableau.
"""
import cv2
import numpy as np
from PIL import Image
import logging
from typing import List, Tuple

_log = logging.getLogger(__name__)


class InvoiceEnhancer:
    """
    Améliorations pour les images de factures :
    - Correction automatique de l'inclinaison (deskew)
    - Amélioration du contraste local (CLAHE)
    - Netteté adaptative (renforce les chiffres)
    - Détection des zones de tableau
    """

    def __init__(self):
        pass

    def enhance_for_ocr(self, image: Image.Image) -> Image.Image:
        img = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # 1. Deskew
        gray = self._deskew(gray)
        
        # 2. CLAHE (contraste local)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # 3. Debruitage
        gray = cv2.fastNlMeansDenoising(gray, None, h=5, templateWindowSize=7, searchWindowSize=15)
        
        # 4. Nettete adaptative
        gray = self._adaptive_sharpen(gray)
        
        # 5. Binarisation Otsu
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return Image.fromarray(gray)

    def _deskew(self, gray: np.ndarray) -> np.ndarray:
        """
        Corrige l'inclinaison via la transformée de Hough.
        """
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        edges = cv2.Canny(binary, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
        
        if lines is None:
            return gray
        
        angles = []
        for line in lines:
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            if -10 < angle < 10:
                angles.append(angle)
        
        if not angles:
            return gray
        
        median_angle = np.median(angles)
        
        if abs(median_angle) < 0.5:
            return gray
        
        h, w = gray.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        
        _log.debug("Deskew applied: angle=%.2f°", median_angle)
        return rotated

    def _adaptive_sharpen(self, gray: np.ndarray) -> np.ndarray:
        """
        Netteté adaptative : plus forte sur les zones de texte.
        """
        local_std = self._local_contrast(gray, kernel_size=15)
        
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        sharpened_base = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
        
        blurred_strong = cv2.GaussianBlur(gray, (5, 5), 0)
        sharpened_strong = cv2.addWeighted(gray, 2.0, blurred_strong, -1.0, 0)
        
        mask = 1.0 - (local_std / 255.0)
        mask = np.clip(mask, 0, 1)
        
        result = (sharpened_base * (1 - mask) + sharpened_strong * mask).astype(np.uint8)
        return result

    def _local_contrast(self, gray: np.ndarray, kernel_size: int = 15) -> np.ndarray:
        """Calcule l'écart-type local."""
        mean = cv2.blur(gray.astype(np.float32), (kernel_size, kernel_size))
        mean_sq = cv2.blur((gray.astype(np.float32) ** 2), (kernel_size, kernel_size))
        variance = mean_sq - mean ** 2
        variance[variance < 0] = 0
        return np.sqrt(variance)

    def detect_table_regions(self, gray: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Détecte les zones de tableau dans l'image.
        Retourne une liste de (x, y, w, h).
        """
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
        dilated = cv2.dilate(binary, kernel_h, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        min_width = gray.shape[1] * 0.3
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > min_width and h > 20:
                regions.append((x, y, w, h))
        
        return sorted(regions, key=lambda r: r[1])