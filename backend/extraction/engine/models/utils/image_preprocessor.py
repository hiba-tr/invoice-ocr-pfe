# models/utils/image_preprocessor.py
import cv2
import numpy as np
from PIL import Image
import logging
import threading  
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quality assessment
# ---------------------------------------------------------------------------

def assess_image_quality(pil_image: Image.Image) -> dict:
    """
    Retourne blur_score (plus haut = plus net)
    - > 1000 : image parfaitement nette (pas de preprocessing)
    - 200-1000 : qualité moyenne (light enhance)
    - 50-200 : floue (full enhance)
    - < 50 : très floue (super-resolution)
    """
    gray = np.array(pil_image.convert("L"))
    # Laplacian variance (plus haut = plus net)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    return {"blur_score": blur_score, "brightness": brightness}


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
    binarisation: str = "none"   # DEFAULT: no binarisation — safer for most invoices
    sauvola_window: int = 25
    sauvola_k: float = 0.2
    clahe_clip_limit: float = 2.0
    clahe_tile_size: int = 8

    # ── Super-resolution settings (blur_score < 50) ─────────────────────────
    sr_scale_factor: int = 3          # upscale factor (2 or 3 recommended)
    sr_unsharp_amount: float = 2.0    # unsharp mask strength after upscale
    sr_unsharp_radius: int = 2        # unsharp mask kernel radius (px, before *2+1)
    sr_denoise_before: float = 8.0    # denoising strength applied BEFORE SR
    sr_denoise_after: float = 5.0     # light denoising applied AFTER SR
    sr_clahe_clip: float = 3.0        # CLAHE clip limit for pre-SR contrast boost
    sr_clahe_tile: int = 8
    # Optional DNN model (requires cv2.dnn_superres + model weights file).
    # Supported: "edsr", "espcn", "fsrcnn", "lapsrn"
    # Set sr_dnn_model_path=None to always use the pure-OpenCV fallback.
    sr_dnn_model: Optional[str] = "fsrcnn"
    sr_dnn_model_path: Optional[str] = None  # e.g. "models/fsrcnn_x3.pb"
    
    @classmethod
    def from_options(cls, options) -> "PreprocessConfig":
        """Crée une PreprocessConfig depuis des PreprocessOptions."""
        if options is None:
            return cls()
        return cls(
            target_dpi=options.target_dpi,
            assumed_source_dpi=options.assumed_source_dpi,
            denoise_strength=options.denoise_strength,
            denoise_template_window=options.denoise_template_window,
            denoise_search_window=options.denoise_search_window,
            sharpen_amount=options.sharpen_amount,
            sharpen_radius=options.sharpen_radius,
            clahe_clip_limit=options.clahe_clip_limit,
            clahe_tile_size=options.clahe_tile_size,
            sr_scale_factor=options.sr_scale_factor,
            sr_unsharp_amount=options.sr_unsharp_amount,
            sr_unsharp_radius=options.sr_unsharp_radius,
            sr_denoise_before=options.sr_denoise_before,
            sr_denoise_after=options.sr_denoise_after,
        )

# ---------------------------------------------------------------------------
# Super-resolution helpers
# ---------------------------------------------------------------------------

def _dnn_upscale(gray: np.ndarray, cfg: PreprocessConfig) -> Optional[np.ndarray]:
    """
    Attempt DNN super-resolution via OpenCV's dnn_superres module.
    Returns upscaled grayscale ndarray, or None if unavailable/failed.
    """
    if cfg.sr_dnn_model is None or cfg.sr_dnn_model_path is None:
        return None
    try:
        from cv2 import dnn_superres  # type: ignore
        sr = dnn_superres.DnnSuperResImpl_create()
        sr.readModel(cfg.sr_dnn_model_path)
        sr.setModel(cfg.sr_dnn_model.lower(), cfg.sr_scale_factor)
        # dnn_superres expects a BGR 3-channel image
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        upscaled_bgr = sr.upsample(bgr)
        upscaled_gray = cv2.cvtColor(upscaled_bgr, cv2.COLOR_BGR2GRAY)
        _log.debug("DNN SR applied (%s ×%d)", cfg.sr_dnn_model, cfg.sr_scale_factor)
        return upscaled_gray
    except Exception as e:
        _log.debug("DNN SR unavailable (%s) → OpenCV fallback", e)
        return None


def _opencv_superres(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """
    Pure-OpenCV super-resolution fallback (no neural network required).

    Pipeline:
      1. Lanczos ×scale upscale
      2. CLAHE local contrast enhancement
      3. Two-pass unsharp mask  (strong pass + gentle pass)
      4. Light denoising to remove sharpening jaggies

    Achieves ~70-80 % of DNN quality for text-heavy invoice images.
    """
    h, w = gray.shape[:2]
    scale = cfg.sr_scale_factor

    # 1. Lanczos upscale
    upscaled = cv2.resize(gray, (w * scale, h * scale),
                          interpolation=cv2.INTER_LANCZOS4)

    # 2. CLAHE — local contrast
    clahe = cv2.createCLAHE(clipLimit=cfg.sr_clahe_clip,
                              tileGridSize=(cfg.sr_clahe_tile, cfg.sr_clahe_tile))
    upscaled = clahe.apply(upscaled)

    # 3a. Strong unsharp mask — recover edges lost during blur
    radius = cfg.sr_unsharp_radius * 2 + 1
    blurred = cv2.GaussianBlur(upscaled, (radius, radius), 0)
    upscaled = cv2.addWeighted(upscaled, 1.0 + cfg.sr_unsharp_amount,
                                blurred, -cfg.sr_unsharp_amount, 0)

    # 3b. Gentle second pass for sub-pixel detail
    blurred2 = cv2.GaussianBlur(upscaled, (3, 3), 0)
    upscaled = cv2.addWeighted(upscaled, 1.15, blurred2, -0.15, 0)

    # 4. Light denoising
    upscaled = cv2.fastNlMeansDenoising(
        upscaled, None,
        h=cfg.sr_denoise_after,
        templateWindowSize=5,
        searchWindowSize=13,
    )
    return upscaled


def _super_resolve(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """DNN first, OpenCV fallback."""
    result = _dnn_upscale(gray, cfg)
    return result if result is not None else _opencv_superres(gray, cfg)


# ---------------------------------------------------------------------------
# Main preprocessor
# ---------------------------------------------------------------------------

class ImagePreprocessor:
    """
    Adaptive preprocessing pipeline — 4 quality tiers.
    Pattern Singleton pour éviter les recréations.
    """

    _instance = None

    def __new__(cls, config: Optional[PreprocessConfig] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[PreprocessConfig] = None):
        if self._initialized and config is None:
            return
        self.cfg = config or PreprocessConfig()
        self._initialized = True

    # ── Public API ───────────────────────────────────────────────────────────

    def get_enhanced_image(self, image: Image.Image) -> Image.Image:
        quality = assess_image_quality(image)
        blur = quality["blur_score"]
        
        _log.debug("Quality: blur=%.1f", blur)
        try:
            if blur > 1000:
                _log.debug("Tier 1: Image parfaite → passthrough")
                return image
            elif blur > 200:
                _log.debug("Tier 2: Qualité moyenne → light enhance")
                return self._light_enhance(image)
            elif blur > 50:
                _log.debug("Tier 3: Floue → full enhance")
                return self._full_enhance(image)
            else:
                _log.debug("Tier 4: Très floue → super-resolution")
                return self._super_resolution_enhance(image)
        except Exception as e:
            _log.warning("ImagePreprocessor error (%s) → original returned", e)
            return image

    # ── Tier 2 ───────────────────────────────────────────────────────────────

    def _light_enhance(self, image: Image.Image) -> Image.Image:
        """Denoise + mild sharpen. No binarisation, no upscale."""
        img = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, h=6,
                                             templateWindowSize=7,
                                             searchWindowSize=15)
        blurred = cv2.GaussianBlur(denoised, (3, 3), 0)
        sharpened = cv2.addWeighted(denoised, 1.3, blurred, -0.3, 0)
        return Image.fromarray(sharpened)

    # ── Tier 3 ───────────────────────────────────────────────────────────────

    def _full_enhance(self, image: Image.Image) -> Image.Image:
        """Full pipeline: upscale to target DPI, CLAHE, denoise, sharpen."""
        img = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)

        scale = self.cfg.target_dpi / self.cfg.assumed_source_dpi
        if scale > 1.0:
            h, w = img.shape[:2]
            img = cv2.resize(img, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_LANCZOS4)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=self.cfg.clahe_clip_limit,
                                  tileGridSize=(self.cfg.clahe_tile_size,
                                                self.cfg.clahe_tile_size))
        gray = clahe.apply(gray)

        gray = cv2.fastNlMeansDenoising(gray, None,
                                         h=self.cfg.denoise_strength,
                                         templateWindowSize=self.cfg.denoise_template_window,
                                         searchWindowSize=self.cfg.denoise_search_window)

        radius = self.cfg.sharpen_radius * 2 + 1
        blurred = cv2.GaussianBlur(gray, (radius, radius), 0)
        gray = cv2.addWeighted(gray, 1 + self.cfg.sharpen_amount,
                                blurred, -self.cfg.sharpen_amount, 0)

        return Image.fromarray(gray)

    # ── Tier 4: Super-resolution ─────────────────────────────────────────────

    def _super_resolution_enhance(self, image: Image.Image) -> Image.Image:
        """
        Super-resolution pipeline for very blurry images (blur_score < 50).

        Steps:
          1. Pre-denoise  — remove noise BEFORE upscaling (prevents amplification)
          2. Pre-SR CLAHE — boost local contrast so SR has more edge signal
          3. SR upscale   — DNN (fsrcnn/edsr/…) or OpenCV Lanczos fallback
          4. DPI clamp    — downscale if SR output exceeds target_dpi resolution
        """
        img_rgb = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        h_orig, w_orig = gray.shape[:2]

        # 1. Pre-denoise
        gray = cv2.fastNlMeansDenoising(
            gray, None,
            h=self.cfg.sr_denoise_before,
            templateWindowSize=self.cfg.denoise_template_window,
            searchWindowSize=self.cfg.denoise_search_window,
        )

        # 2. CLAHE
        clahe = cv2.createCLAHE(
            clipLimit=self.cfg.sr_clahe_clip,
            tileGridSize=(self.cfg.sr_clahe_tile, self.cfg.sr_clahe_tile),
        )
        gray = clahe.apply(gray)

        # 3. SR upscale
        gray_sr = _super_resolve(gray, self.cfg)
        h_sr, w_sr = gray_sr.shape[:2]

        # 4. DPI clamp — avoid unnecessarily huge outputs
        scale_applied = h_sr / h_orig
        desired_scale = max(self.cfg.target_dpi / max(self.cfg.assumed_source_dpi, 1), 1.0)
        if scale_applied > desired_scale * 1.25:
            new_h = int(h_orig * desired_scale)
            new_w = int(w_orig * desired_scale)
            gray_sr = cv2.resize(gray_sr, (new_w, new_h), interpolation=cv2.INTER_AREA)
            _log.debug("SR output clamped: %.1f× → %.1f× (DPI target)", scale_applied, desired_scale)

        _log.info("SR complete: %dx%d → %dx%d (×%.1f)",
                  w_orig, h_orig, gray_sr.shape[1], gray_sr.shape[0],
                  gray_sr.shape[0] / h_orig)
        return Image.fromarray(gray_sr)