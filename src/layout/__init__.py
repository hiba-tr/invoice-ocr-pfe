from .detector import LayoutDetector

class DummyLayoutDetector(LayoutDetector):
    """Détecteur factice qui ne retourne rien."""
    def detect(self, image):
        return []
    @property
    def model_name(self):
        return "dummy"

__all__ = ["LayoutDetector", "DummyLayoutDetector"]