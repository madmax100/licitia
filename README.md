# PDF Document Analyzer

## Overview
The PDF Document Analyzer is a Python application designed to read and analyze PDF files containing multiple grouped documents. It utilizes a local artificial intelligence model from Ollama and Tesseract for optical character recognition (OCR) to extract and process information from the documents.

## Features
- Extracts individual documents from a grouped PDF.
- Identifies document titles, creation dates, and page numbers.
- Generates brief descriptions of the documents.
- Utilizes Tesseract for OCR on images within the PDF.
- Processes text using an AI model to derive insights.

## Project Structure
```
pdf-document-analyzer
├── src
│   ├── main.py                # Entry point of the application
│   ├── config.py              # Configuration settings
│   ├── models
│   │   ├── ai_processor.py     # AI model interaction
│   │   ├── document_extractor.py # Document extraction logic
│   │   └── metadata_analyzer.py # Metadata analysis
│   ├── utils
│   │   ├── pdf_reader.py       # PDF reading functions
│   │   ├── ocr_helper.py       # OCR functions using Tesseract
│   │   └── text_processor.py    # Text processing functions
│   └── tests
│       ├── test_pdf_reader.py  # Unit tests for PDF reading
│       ├── test_ai_processor.py # Unit tests for AI processing
│       └── test_metadata_analyzer.py # Unit tests for metadata analysis
├── data
│   ├── input                   # Directory for input PDF files
│   └── output                  # Directory for output results
├── requirements.txt            # Project dependencies
├── .env.example                # Environment variable template
└── README.md                   # Project documentation
```

## Installation
1. Clone the repository:
   ```
   git clone <repository-url>
   cd pdf-document-analyzer
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables by copying `.env.example` to `.env` and updating the values as needed.

## Usage
1. Place your input PDF files in the `data/input` directory.
2. Run the application:
   ```
   python src/main.py
   ```
3. The output will be saved in the `data/output` directory, containing the identified titles, summaries, and metadata.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.