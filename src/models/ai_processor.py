import requests
import json
import re
import base64
from datetime import datetime
from PIL import Image
import io
import os

class AIProcessor:
    def __init__(self, model="llava", server_url="http://localhost:11434", 
                 proxy_url=None, proxy_user=None, proxy_password=None):
        """
        Initialize the AI processor with offline mode by default.
        
        Args:
            model (str): The name of the Ollama model to use
            server_url (str): URL of the Ollama server
            proxy_url (str, optional): Proxy URL (e.g., http://proxy.example.com:8080)
            proxy_user (str, optional): Username for proxy authentication
            proxy_password (str, optional): Password for proxy authentication
        """
        self.model = model
        self.server_url = server_url
        self.offline_mode = True  # Set to True by default
        
        # Configure proxy settings
        self.proxies = {}
        if proxy_url:
            proxy_auth = ""
            if proxy_user and proxy_password:
                proxy_auth = f"{proxy_user}:{proxy_password}@"
                
            proxy_with_auth = proxy_url.replace("://", f"://{proxy_auth}")
            self.proxies = {
                "http": proxy_with_auth,
                "https": proxy_with_auth
            }
        
        # Detect if we should try to use Ollama or stay offline
        try:
            # Test if server is reachable - simple GET request
            response = requests.get(
                f"{self.server_url}", 
                proxies=self.proxies,
                timeout=2
            )
            
            if response.status_code == 200:
                self.offline_mode = False
                print("Ollama server detectado, tentando usar modelos de IA.")
        except Exception as e:
            print(f"Ollama server não está acessível: {e}. Usando processamento offline.")
    
    def _call_ollama(self, prompt, system_prompt=None, image_path=None):
        """
        Call the Ollama API or use offline processing.
        """
        # If offline mode is enabled, skip API call and use fallback
        if self.offline_mode:
            return ""
            
        # Otherwise try to call the API
        url = f"{self.server_url}/api/generate"
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        
        if system_prompt:
            data["system"] = system_prompt
            
        # Add image if provided
        if image_path:
            try:
                with open(image_path, "rb") as image_file:
                    image_data = image_file.read()
                    base64_image = base64.b64encode(image_data).decode("utf-8")
                    data["images"] = [base64_image]
            except Exception as e:
                print(f"Error processing image: {e}")
        
        try:
            # Also use proxy settings from environment variables if available
            proxies = self.proxies.copy()
            if "HTTP_PROXY" in os.environ and not proxies.get("http"):
                proxies["http"] = os.environ["HTTP_PROXY"]
            if "HTTPS_PROXY" in os.environ and not proxies.get("https"):
                proxies["https"] = os.environ["HTTPS_PROXY"]
            
            response = requests.post(
                url, 
                json=data, 
                proxies=proxies,
                timeout=5
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            print(f"Error calling Ollama API: {e}")
            return ""
    
    def process_document(self, extracted_text):
        """
        Process document text to extract metadata.
        
        Args:
            extracted_text (str): The extracted text from the document
            
        Returns:
            dict: Dictionary containing title, summary, date
        """
        title = self.extract_title(extracted_text)
        summary = self.summarize_text(extracted_text)
        date = self.extract_date(extracted_text)
        
        return {
            "title": title,
            "summary": summary,
            "date": date
        }
    
    def is_new_document_page(self, page_image_path, page_text):
        """
        Determine if a page likely starts a new document using the Llava model.
        
        Args:
            page_image_path (str): Path to the page image
            page_text (str): Text extracted from the page
            
        Returns:
            bool: True if the page likely starts a new document
        """
        prompt = """
        Analyze this page and determine if it appears to be the start of a new document.
        Look for title pages, cover pages, new headers, or other indicators that this is 
        the first page of a document rather than a continuation page.
        Answer with only "YES" if this is likely the start of a new document, or "NO" if it's a continuation page.
        """
        
        response = self._call_ollama(prompt, image_path=page_image_path)
        
        # If Ollama response fails, fallback to simple heuristics
        if not response or "Error" in response:
            # Check if page contains elements that suggest it's a first page
            first_lines = page_text.strip().split('\n')[:5]
            first_text = ' '.join(first_lines).lower()
            
            # Check for common first page indicators
            indicators = ['termo', 'relatório', 'laudo', 'auto', 'ofício', 'memorando', 
                         'processo', 'parecer', 'despacho', 'decisão']
            
            for indicator in indicators:
                if indicator.lower() in first_text:
                    return True
                    
            # First page often has less text
            if len(page_text.strip()) < 300:
                return True
                
            return False
        
        return "YES" in response.upper()
    
    def extract_title(self, text):
        """
        Extract the title from the document text.
        """
        prompt = f"""
        Extract the main title or document type from the following text. 
        Give only the title, without any additional text:
        
        {text[:1000]}
        """
        
        response = self._call_ollama(prompt)
        
        if not response:
            # Fallback to simple heuristics
            lines = text.split('\n')
            candidate_lines = [line.strip() for line in lines[:10] if line.strip()]
            
            if candidate_lines:
                # Select the line most likely to be a title (short but not too short)
                for line in candidate_lines:
                    if 5 < len(line) < 100:
                        return line
                        
            return "Documento sem título identificado"
            
        return response.strip()
    
    def summarize_text(self, text):
        """
        Summarize the document text.
        """
        prompt = f"""
        Create a concise summary (maximum 3 paragraphs) of the following document:
        
        {text[:3000]}
        """
        
        response = self._call_ollama(prompt)
        
        if not response:
            # Fallback to simple extraction
            paragraphs = text.split('\n\n')
            relevant_paragraphs = [p for p in paragraphs[:5] if len(p.strip()) > 50]
            
            if relevant_paragraphs:
                summary = "\n".join(relevant_paragraphs[:3])
                if len(summary) > 500:
                    summary = summary[:500] + "..."
                return summary
                    
            return "Extrato do documento: " + text[:500] + "..."
            
        return response.strip()
    
    def extract_date(self, text):
        """
        Extract the date from the document text.
        """
        prompt = f"""
        Extract the date of creation or issue date from the following document text.
        Return just the date in DD/MM/YYYY format. If no date is found, return "Date not found".
        
        {text[:2000]}
        """
        
        response = self._call_ollama(prompt)
        
        if not response or "not found" in response.lower():
            # Fallback to regex extraction
            date_patterns = [
                r'\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b',  # DD/MM/YYYY
                r'\b(\d{1,2}) de (\w+) de (\d{2,4})\b',        # DD de Mês de YYYY
            ]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, text[:1000])
                if matches:
                    # Process the first match
                    match = matches[0]
                    return f"{match[0]}/{match[1]}/{match[2]}"
                    
            return "Data não identificada"
            
        return response.strip()