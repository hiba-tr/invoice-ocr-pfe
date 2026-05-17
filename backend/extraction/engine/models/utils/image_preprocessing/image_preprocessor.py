# models/utils/image_preprocessor.py
import cv2
import numpy as np
from PIL import Image
import logging
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quality assessment
# ---------------------------------------------------------------------------

def assess_image_quality(pil_image: Image.Image) -> dict:
    """
    Retourne blur_score (plus haut = plus net)
    - > 1000 : image parfaitement nette
    - 200-1000 : qualite moyenne
    - 50-200 : floue
    - < 50 : tres floue
    """
    gray = np.array(pil_image.convert("L"))
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    return {
        "blur_score": blur_score,
        "brightness": brightness,
        "contrast": contrast
    }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class PreprocessConfig:
    target_dpi: int = 300
    assumed_source_dpi: int = 72
    enable_deskew: bool = True
    deskew_max_angle: float = 10.0
    denoise_strength: float = 10.0
    denoise_template_window: int = 7
    denoise_search_window: int = 21
    sharpen_amount: float = 1.5
    sharpen_radius: int = 1
    binarisation: str = "adaptive"
    sauvola_window: int = 25
    sauvola_k: float = 0.2
    clahe_clip_limit: float = 2.0
    clahe_tile_size: int = 8
    upscale_factor: float = 2.0
    contrast_boost: float = 2.0

    sr_scale_factor: int = 3
    sr_unsharp_amount: float = 2.0
    sr_unsharp_radius: int = 2
    sr_denoise_before: float = 8.0
    sr_denoise_after: float = 5.0
    sr_clahe_clip: float = 3.0
    sr_clahe_tile: int = 8
    sr_dnn_model: Optional[str] = "fsrcnn"
    sr_dnn_model_path: Optional[str] = None

    @classmethod
    def from_options(cls, options) -> "PreprocessConfig":
        if options is None:
            return cls()
        return cls(
            target_dpi=getattr(options, 'target_dpi', 300),
            assumed_source_dpi=getattr(options, 'assumed_source_dpi', 72),
            denoise_strength=getattr(options, 'denoise_strength', 10.0),
            denoise_template_window=getattr(options, 'denoise_template_window', 7),
            denoise_search_window=getattr(options, 'denoise_search_window', 21),
            sharpen_amount=getattr(options, 'sharpen_amount', 1.5),
            sharpen_radius=getattr(options, 'sharpen_radius', 1),
            clahe_clip_limit=getattr(options, 'clahe_clip_limit', 2.0),
            clahe_tile_size=getattr(options, 'clahe_tile_size', 8),
            sr_scale_factor=getattr(options, 'sr_scale_factor', 3),
            sr_unsharp_amount=getattr(options, 'sr_unsharp_amount', 2.0),
            sr_unsharp_radius=getattr(options, 'sr_unsharp_radius', 2),
            sr_denoise_before=getattr(options, 'sr_denoise_before', 8.0),
            sr_denoise_after=getattr(options, 'sr_denoise_after', 5.0),
        )


# ---------------------------------------------------------------------------
# Super-resolution helpers
# ---------------------------------------------------------------------------

def _dnn_upscale(gray: np.ndarray, cfg: PreprocessConfig) -> Optional[np.ndarray]:
    if cfg.sr_dnn_model is None or cfg.sr_dnn_model_path is None:
        return None
    try:
        from cv2 import dnn_superres
        sr = dnn_superres.DnnSuperResImpl_create()
        sr.readModel(cfg.sr_dnn_model_path)
        sr.setModel(cfg.sr_dnn_model.lower(), cfg.sr_scale_factor)
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        upscaled_bgr = sr.upsample(bgr)
        upscaled_gray = cv2.cvtColor(upscaled_bgr, cv2.COLOR_BGR2GRAY)
        _log.debug("DNN SR applied (%s x%d)", cfg.sr_dnn_model, cfg.sr_scale_factor)
        return upscaled_gray
    except Exception as e:
        _log.debug("DNN SR unavailable (%s) -> OpenCV fallback", e)
        return None


def _opencv_superres(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = cfg.sr_scale_factor
    upscaled = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
    clahe = cv2.createCLAHE(clipLimit=cfg.sr_clahe_clip, tileGridSize=(cfg.sr_clahe_tile, cfg.sr_clahe_tile))
    upscaled = clahe.apply(upscaled)
    radius = cfg.sr_unsharp_radius * 2 + 1
    blurred = cv2.GaussianBlur(upscaled, (radius, radius), 0)
    upscaled = cv2.addWeighted(upscaled, 1.0 + cfg.sr_unsharp_amount, blurred, -cfg.sr_unsharp_amount, 0)
    blurred2 = cv2.GaussianBlur(upscaled, (3, 3), 0)
    upscaled = cv2.addWeighted(upscaled, 1.15, blurred2, -0.15, 0)
    upscaled = cv2.fastNlMeansDenoising(upscaled, None, h=cfg.sr_denoise_after, templateWindowSize=5, searchWindowSize=13)
    return upscaled


def _super_resolve(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    result = _dnn_upscale(gray, cfg)
    return result if result is not None else _opencv_superres(gray, cfg)


# ---------------------------------------------------------------------------
# Binarisation adaptative
# ---------------------------------------------------------------------------

def _adaptive_binarize(gray: np.ndarray, method: str = "otsu") -> np.ndarray:
    """Binarisation adaptative pour ameliorer la lisibilite du texte."""
    if method == "otsu":
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "sauvola":
        window = 25
        mean = cv2.blur(gray.astype(np.float32), (window, window))
        mean_sq = cv2.blur((gray.astype(np.float32) ** 2), (window, window))
        std = np.sqrt(mean_sq - mean ** 2)
        std[std < 1] = 1
        threshold = mean * (1 + 0.2 * (std / 128 - 1))
        binary = np.where(gray > threshold, 255, 0).astype(np.uint8)
    else:
        threshold = np.mean(gray) * 0.75
        binary = np.where(gray < threshold, 0, 255).astype(np.uint8)
    return binary


# ---------------------------------------------------------------------------
# Main preprocessor
# ---------------------------------------------------------------------------

class ImagePreprocessor:
    """
    Pipeline adaptatif - 5 niveaux :
    Tier 0 : Image nette -> upscale + binarisation (NOUVEAU)
    Tier 1 : blur > 1000 -> passthrough
    Tier 2 : 200-1000 -> light enhance
    Tier 3 : 50-200 -> full enhance
    Tier 4 : < 50 -> super-resolution
    """

    _instance = None

    def __new__(cls, config: Optional[PreprocessConfig] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[PreprocessConfig] = None):
        if getattr(self, '_initialized', False) and config is None:
            return
        self.cfg = config or PreprocessConfig()
        self._initialized = True

    def get_enhanced_image(self, image: Image.Image) -> Image.Image:
        quality = assess_image_quality(image)
        blur = quality["blur_score"]
        contrast = quality.get("contrast", 0)

        _log.debug("Quality: blur=%.1f, contrast=%.1f", blur, contrast)

        try:
            # Tier 0 : Image nette -> upscale + binarisation
            if blur > 1000:
                if contrast < 50:
                    _log.debug("Tier 0: Image nette mais faible contraste -> upscale + binarisation")
                    return self._enhance_for_ocr(image)
                else:
                    _log.debug("Tier 1: Image parfaite -> passthrough")
                    return image
            elif blur > 200:
                _log.debug("Tier 2: Qualite moyenne -> light enhance")
                return self._light_enhance(image)
            elif blur > 50:
                _log.debug("Tier 3: Floue -> full enhance")
                return self._full_enhance(image)
            else:
                _log.debug("Tier 4: Tres floue -> super-resolution")
                return self._super_resolution_enhance(image)
        except Exception as e:
            _log.warning("ImagePreprocessor error (%s) -> original returned", e)
            return image

    def _enhance_for_ocr(self, image: Image.Image) -> Image.Image:
        """Tier 0 : Optimisation pour OCR sur image nette."""
        img_array = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # Upscale si l'image est petite
        h, w = gray.shape[:2]
        if w < 2000:
            scale = self.cfg.upscale_factor
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)

        # CLAHE pour contraste local
        clahe = cv2.createCLAHE(clipLimit=self.cfg.clahe_clip_limit, tileGridSize=(self.cfg.clahe_tile_size, self.cfg.clahe_tile_size))
        gray = clahe.apply(gray)

        # Debruitage leger
        gray = cv2.fastNlMeansDenoising(gray, None, h=3, templateWindowSize=5, searchWindowSize=11)

        # Nettete
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        gray = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)

        # Binarisation adaptative
        gray = _adaptive_binarize(gray, method="otsu")

        return Image.fromarray(gray)

    def _light_enhance(self, image: Image.Image) -> Image.Image:
        img = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, h=6, templateWindowSize=7, searchWindowSize=15)
        blurred = cv2.GaussianBlur(denoised, (3, 3), 0)
        sharpened = cv2.addWeighted(denoised, 1.3, blurred, -0.3, 0)
        return Image.fromarray(sharpened)

    def _full_enhance(self, image: Image.Image) -> Image.Image:
        img = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        scale = self.cfg.target_dpi / self.cfg.assumed_source_dpi
        if scale > 1.0:
            h, w = img.shape[:2]
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=self.cfg.clahe_clip_limit, tileGridSize=(self.cfg.clahe_tile_size, self.cfg.clahe_tile_size))
        gray = clahe.apply(gray)
        gray = cv2.fastNlMeansDenoising(gray, None, h=self.cfg.denoise_strength,
                                         templateWindowSize=self.cfg.denoise_template_window,
                                         searchWindowSize=self.cfg.denoise_search_window)
        radius = self.cfg.sharpen_radius * 2 + 1
        blurred = cv2.GaussianBlur(gray, (radius, radius), 0)
        gray = cv2.addWeighted(gray, 1 + self.cfg.sharpen_amount, blurred, -self.cfg.sharpen_amount, 0)
        return Image.fromarray(gray)

    def _super_resolution_enhance(self, image: Image.Image) -> Image.Image:
        img_rgb = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        h_orig, w_orig = gray.shape[:2]
        gray = cv2.fastNlMeansDenoising(gray, None, h=self.cfg.sr_denoise_before,
                                         templateWindowSize=self.cfg.denoise_template_window,
                                         searchWindowSize=self.cfg.denoise_search_window)
        clahe = cv2.createCLAHE(clipLimit=self.cfg.sr_clahe_clip, tileGridSize=(self.cfg.sr_clahe_tile, self.cfg.sr_clahe_tile))
        gray = clahe.apply(gray)
        gray_sr = _super_resolve(gray, self.cfg)
        h_sr, w_sr = gray_sr.shape[:2]
        scale_applied = h_sr / h_orig
        desired_scale = max(self.cfg.target_dpi / max(self.cfg.assumed_source_dpi, 1), 1.0)
        if scale_applied > desired_scale * 1.25:
            new_h = int(h_orig * desired_scale)
            new_w = int(w_orig * desired_scale)
            gray_sr = cv2.resize(gray_sr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        _log.info("SR complete: %dx%d -> %dx%d (x%.1f)", w_orig, h_orig, gray_sr.shape[1], gray_sr.shape[0], gray_sr.shape[0] / h_orig)
        return Image.fromarray(gray_sr)