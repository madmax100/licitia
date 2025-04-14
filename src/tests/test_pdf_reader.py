import unittest
from utils.pdf_reader import read_pdf

class TestPDFReader(unittest.TestCase):

    def test_read_pdf_valid(self):
        # Test reading a valid PDF file
        pdf_path = 'data/input/sample.pdf'
        text, page_count = read_pdf(pdf_path)
        self.assertIsInstance(text, str)
        self.assertGreater(page_count, 0)

    def test_read_pdf_invalid(self):
        # Test reading an invalid PDF file
        pdf_path = 'data/input/invalid.pdf'
        with self.assertRaises(Exception):
            read_pdf(pdf_path)

    def test_read_pdf_empty(self):
        # Test reading an empty PDF file
        pdf_path = 'data/input/empty.pdf'
        text, page_count = read_pdf(pdf_path)
        self.assertEqual(text, "")
        self.assertEqual(page_count, 0)

if __name__ == '__main__':
    unittest.main()