import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import tempfile

class PDFReader:
    def __init__(self, tesseract_path=None):
        """
        Initialize the PDF reader.
        
        Args:
            tesseract_path (str, optional): Path to Tesseract executable
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

    def _create_temp_dir(self):
        """Create a temporary directory for page images"""
        self.temp_dir = tempfile.mkdtemp()

    def _cleanup_temp_dir(self):
        """Clean up temporary image directory"""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            for file_name in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file_name)
                os.unlink(file_path)
            os.rmdir(self.temp_dir)

    def extract_text_from_pdf(self, pdf_path, use_ocr=False):
        """
        Extract text from a PDF file.
        
        Args:
            pdf_path (str): Path to the PDF file
            use_ocr (bool): Whether to use OCR for text extraction
            
        Returns:
            list: List of dictionaries containing page number and text
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        doc = fitz.open(pdf_path)
        pages_content = []
        self._create_temp_dir()
        
        for page_num, page in enumerate(doc):
            if use_ocr:
                # Extract as image and use OCR
                pix = page.get_pixmap()
                image_path = os.path.join(self.temp_dir, f"page_{page_num + 1}.png")
                pix.save(image_path)
                image = Image.open(image_path)
                text = pytesseract.image_to_string(image)
            else:
                # Extract text directly (if PDF has text layer)
                text = page.get_text()
                
                # If no text was extracted, fall back to OCR
                if not text.strip() and use_ocr is False:
                    return self.extract_text_from_pdf(pdf_path, use_ocr=True)
            
            pages_content.append({
                "page_num": page_num + 1,
                "text": text,
                "image_path": image_path if use_ocr else None
            })
            
        return pages_content

    def identify_document_boundaries(self, pages_content, ai_processor=None):
        """
        Identify boundaries between different documents in a single PDF using
        visual analysis with Llava or simple heuristics.

        Args:
            pages_content (list): List of dictionaries with page content
            ai_processor (AIProcessor, optional): Instance of AIProcessor for using Llava/heuristics
                                                  If None, only simple heuristics are used.

        Returns:
            list: List of document boundaries (start page, end page)
        """
        documents = []
        if not pages_content:
            return documents

        current_doc_start = 0

        # Always consider first page as start of the first document
        for i in range(1, len(pages_content)):
            page = pages_content[i]
            is_new_doc = False

            # Use Llava/AIProcessor if available and not None
            if ai_processor:
                # Check if ai_processor has the method before calling
                if hasattr(ai_processor, 'is_new_document_page') and callable(getattr(ai_processor, 'is_new_document_page')):
                     is_new_doc = ai_processor.is_new_document_page(
                         page.get("image_path", ""), # Use .get for safety
                         page.get("text", "")
                     )
                else:
                    # Fallback to simple heuristic if method is missing in AIProcessor
                    lines = page.get("text", "").strip().split('\n')
                    if lines and (len(lines[0]) < 100 and lines[0].isupper()):
                        is_new_doc = True
            else:
                # Simple heuristic fallback if ai_processor is None
                lines = page.get("text", "").strip().split('\n')
                if lines and (len(lines[0]) < 100 and lines[0].isupper()):
                    is_new_doc = True

            if is_new_doc:
                # End the previous document
                documents.append({
                    "start_page": current_doc_start,
                    "end_page": i - 1,
                    "pages": pages_content[current_doc_start:i]
                })
                current_doc_start = i

        # Add the last document
        if current_doc_start < len(pages_content):
            documents.append({
                "start_page": current_doc_start,
                "end_page": len(pages_content) - 1,
                "pages": pages_content[current_doc_start:]
            })

        return documents

    def __del__(self):
        """Cleanup on object destruction"""
        self._cleanup_temp_dir()