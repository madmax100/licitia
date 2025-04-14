import unittest
from models.metadata_analyzer import MetadataAnalyzer

class TestMetadataAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = MetadataAnalyzer()

    def test_analyze_metadata_title(self):
        text = "Title: Sample Document\nDate: 2023-10-01\nContent: This is a sample document."
        expected_title = "Sample Document"
        result = self.analyzer.analyze_metadata(text)
        self.assertEqual(result['title'], expected_title)

    def test_analyze_metadata_date(self):
        text = "Title: Sample Document\nDate: 2023-10-01\nContent: This is a sample document."
        expected_date = "2023-10-01"
        result = self.analyzer.analyze_metadata(text)
        self.assertEqual(result['creation_date'], expected_date)

    def test_analyze_metadata_page_numbers(self):
        text = "Title: Sample Document\nDate: 2023-10-01\nContent: This is a sample document."
        start_page = 1
        end_page = 5
        result = self.analyzer.analyze_metadata(text, start_page, end_page)
        self.assertEqual(result['start_page'], start_page)
        self.assertEqual(result['end_page'], end_page)

    def test_analyze_metadata_summary(self):
        text = "Title: Sample Document\nDate: 2023-10-01\nContent: This is a sample document."
        expected_summary = "This is a sample document."
        result = self.analyzer.analyze_metadata(text)
        self.assertEqual(result['summary'], expected_summary)

if __name__ == '__main__':
    unittest.main()