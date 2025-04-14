import pytesseract
from PIL import Image
import re
from datetime import datetime

class OCRHelper:
    def __init__(self, tesseract_path=None):
        """
        Initialize the OCR helper.
        
        Args:
            tesseract_path (str, optional): Path to Tesseract executable
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    
    def extract_text_from_image(self, image_path):
        """
        Extract text from an image file.
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            str: Extracted text
        """
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang='por')
            return text
        except Exception as e:
            print(f"Error extracting text from image: {e}")
            return ""
    
    def extract_date(self, text):
        """
        Extract date from text.
        
        Args:
            text (str): Text to extract date from
            
        Returns:
            str: Extracted date in ISO format or None
        """
        # Common date patterns in Brazilian documents
        date_patterns = [
            r'\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b',  # DD/MM/YYYY
            r'\b(\d{1,2}) de (\w+) de (\d{2,4})\b',        # DD de Month de YYYY
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                # Process the first match
                match = matches[0]
                try:
                    if '/' in pattern or '.' in pattern or '-' in pattern:
                        day, month, year = map(int, match)
                        if year < 100:  # Convert 2-digit year
                            year += 2000 if year < 50 else 1900
                    else:  # Text month format
                        day = int(match[0])
                        month_text = match[1].lower()
                        month_dict = {
                            'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 
                            'abril': 4, 'maio': 5, 'junho': 6, 'julho': 7, 
                            'agosto': 8, 'setembro': 9, 'outubro': 10, 
                            'novembro': 11, 'dezembro': 12
                        }
                        month = month_dict.get(month_text, 1)
                        year = int(match[2])
                    
                    date_obj = datetime(year, month, day)
                    return date_obj.isoformat()[:10]  # YYYY-MM-DD
                except (ValueError, TypeError):
                    continue
        
        return None