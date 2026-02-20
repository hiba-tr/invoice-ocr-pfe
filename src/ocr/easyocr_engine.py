import easyocr
from PIL import Image
import numpy as np

class EasyOCREngine:
    def __init__(self, lang_list=None):
        if lang_list is None:
            lang_list = ['fr', 'en']
        self.reader = easyocr.Reader(lang_list)

    def extract_text_from_image(self, image_source):
        if isinstance(image_source, (str, Path)):
            result = self.reader.readtext(str(image_source))
        else:
            # Convert PIL to numpy
            img_np = np.array(image_source)
            result = self.reader.readtext(img_np)
        return " ".join([item[1] for item in result])