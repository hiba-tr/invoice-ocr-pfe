def ocr_engines():
    from models.stages.ocr.auto_ocr_model import OcrAutoModel
    from models.stages.ocr.easyocr_model import EasyOcrModel
    from models.stages.ocr.ocr_mac_model import OcrMacModel
    from models.stages.ocr.rapid_ocr_model import RapidOcrModel

    return {
        "ocr_engines": [
            OcrAutoModel,
            EasyOcrModel,
            OcrMacModel,
            RapidOcrModel,
            
        ]
    }




def layout_engines():
    from experimental.models.table_crops_layout_model import (
        TableCropsLayoutModel,
    )
    from models.stages.layout.layout_model import LayoutModel
    from models.stages.layout.layout_object_detection_model import (
        LayoutObjectDetectionModel,
    )

    return {
        "layout_engines": [
            LayoutObjectDetectionModel,
            LayoutModel,
            TableCropsLayoutModel,
        ]
    }


def table_structure_engines():
    from models.stages.table_structure.table_structure_model import (
        TableStructureModel,
    )

    return {
        "table_structure_engines": [
            TableStructureModel,
        ]
    }
