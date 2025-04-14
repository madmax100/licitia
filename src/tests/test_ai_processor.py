import unittest
from models.ai_processor import AIProcessor
from utils.pdf_reader import read_pdf

class TestAIProcessor(unittest.TestCase):

    def setUp(self):
        self.processor = AIProcessor()
        self.sample_text = "Sample Document Title\nThis is a brief description of the document.\nDate: 2023-01-01\n"
        self.expected_title = "Sample Document Title"
        self.expected_description = "This is a brief description of the document."
        self.expected_date = "2023-01-01"
    
    def test_process_document(self):
        result = self.processor.process_document(self.sample_text)
        self.assertEqual(result['title'], self.expected_title)
        self.assertEqual(result['description'], self.expected_description)
        self.assertEqual(result['creation_date'], self.expected_date)

    def test_process_empty_document(self):
        result = self.processor.process_document("")
        self.assertIsNone(result['title'])
        self.assertIsNone(result['description'])
        self.assertIsNone(result['creation_date'])

if __name__ == '__main__':
    unittest.main()