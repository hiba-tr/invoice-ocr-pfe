from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
from .base import VLMProcessor

class BLIPProcessor(VLMProcessor):
    def __init__(self):
        self.processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        self.model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        self._model_name = "blip-base"

    def describe(self, image: Image, prompt: str = None) -> str:
        if prompt:
            inputs = self.processor(image, prompt, return_tensors="pt")
            out = self.model.generate(**inputs)
        else:
            inputs = self.processor(image, return_tensors="pt")
            out = self.model.generate(**inputs)
        return self.processor.decode(out[0], skip_special_tokens=True)

    @property
    def model_name(self):
        return self._model_name