from ultralytics import YOLO
from PIL import Image
from .detector import LayoutDetector
from config import settings

class YOLOXDetector(LayoutDetector):
    def __init__(self):
        model_path = settings.LAYOUT_CONFIG['yolox']['model_path']
        self.model = YOLO(model_path) if model_path.exists() else None
        self._model_name = "yolov8-layout"

    def detect(self, image: Image) -> List[Dict[str, Any]]:
        if self.model is None:
            return []
        results = self.model(image)[0]
        blocks = []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            blocks.append({
                'bbox': [x1, y1, x2, y2],
                'type': results.names[cls_id],
                'confidence': conf
            })
        return blocks

    @property
    def model_name(self):
        return self._model_name