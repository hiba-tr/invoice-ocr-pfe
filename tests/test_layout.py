import unittest
from pathlib import Path
from PIL import Image
from src.layout.layoutparser_model import LayoutParserDetector

class TestLayout(unittest.TestCase):
    def test_detection(self):
        detector = LayoutParserDetector()
        img = Image.new('RGB', (100, 100))
        blocks = detector.detect(img)
        self.assertIsInstance(blocks, list)

if __name__ == '__main__':
    unittest.main()