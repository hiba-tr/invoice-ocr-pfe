import layoutparser as lp
import numpy as np
from PIL import Image
from .detector import LayoutDetector
from config import settings

class LayoutParserDetector(LayoutDetector):
    def __init__(self):
        config_path = settings.LAYOUT_CONFIG['layoutparser']['config_path']
        self.model = lp.Detectron2LayoutModel(
            config_path,
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
            label_map={0: "text", 1: "title", 2: "list", 3: "table", 4: "figure"}
        )
        self._model_name = "layoutparser-publaynet"

    def detect(self, image: Image) -> List[Dict[str, Any]]:
        image_np = np.array(image)
        layout = self.model.detect(image_np)
        blocks = []
        for block in layout:
            x1, y1, x2, y2 = block.coordinates
            blocks.append({
                'bbox': [x1, y1, x2, y2],
                'type': block.type,
                'confidence': block.score if hasattr(block, 'score') else 1.0
            })
        return blocks

    @property
    def model_name(self):
        return self._model_name