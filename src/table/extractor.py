from transformers import TableTransformerForObjectDetection, DetrImageProcessor
import torch
from PIL import Image
from typing import List, Dict, Any

class TableExtractor:
    def __init__(self, model_name="microsoft/table-transformer-detection"):
        self.processor = DetrImageProcessor.from_pretrained(model_name)
        self.model = TableTransformerForObjectDetection.from_pretrained(model_name)
        self.model_name = model_name

    def extract(self, image: Image) -> List[Dict[str, Any]]:
        inputs = self.processor(images=image, return_tensors="pt")
        outputs = self.model(**inputs)
        target_sizes = torch.tensor([image.size[::-1]])
        results = self.processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.7)[0]

        tables = []
        for box, score, label in zip(results["boxes"], results["scores"], results["labels"]):
            if self.model.config.id2label[label.item()] == "table":
                bbox = box.tolist()
                tables.append({
                    'bbox': {'x1': bbox[0], 'y1': bbox[1], 'x2': bbox[2], 'y2': bbox[3]},
                    'confidence': score.item(),
                    'data': []
                })
        return tables