import pytesseract
from PIL import Image
from pathlib import Path
from config import settings

class TesseractEngine:
    def __init__(self, lang: str = None):
        self.lang = lang or "+".join(settings.OCR_LANGUAGES)
        if settings.TESSERACT_CMD != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    def extract_text_from_image(self, image_source):
        if isinstance(image_source, (str, Path)):
            img = Image.open(image_source)
        else:
            img = image_source
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, lang=self.lang, config=custom_config)
        return text.strip()