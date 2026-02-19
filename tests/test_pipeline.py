import unittest
from pathlib import Path
from src.core.pipeline import DocumentProcessor

class TestPipeline(unittest.TestCase):
    def test_processor_init(self):
        proc = DocumentProcessor()
        self.assertIsNotNone(proc)

if __name__ == '__main__':
    unittest.main()