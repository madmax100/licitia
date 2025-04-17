import os
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import tempfile
import re
from functools import lru_cache
import subprocess
import sys
import json
import shutil
from typing import List, Dict, Tuple, Optional
from pdf2image import convert_from_path, pdfinfo_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError # Import specific exceptions
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_ollama import OllamaLLM
import logging # Added for better logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# filepath: c:\Users\Cirilo\Documents\licitia\pdf-document-analyzer\src\main.py
import os
import shutil
print("--- System PATH ---")
print(os.environ.get('PATH'))
print("--- Checking pdftoppm ---")
print(shutil.which("pdftoppm"))
print("--- Checking pdfinfo ---")
print(shutil.which("pdfinfo"))
print("---------------------")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

def check_poppler_installation():
    """Verifica se o Poppler está instalado e no PATH."""
    # 1. Try running pdfinfo directly using pdf2image's expected mechanism first
    try:
        # Create a dummy empty PDF in memory to test pdfinfo_from_path
        # This avoids the NoneType error and properly tests pdf2image's ability to call pdfinfo
        dummy_pdf_path = os.path.join(tempfile.gettempdir(), "dummy_test.pdf")
        with open(dummy_pdf_path, "w") as f:
             f.write("%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f\n0000000010 00000 n\n0000000058 00000 n\ntrailer<</Size 3/Root 1 0 R>>startxref\n108\n%%EOF")

        pdfinfo_from_path(dummy_pdf_path, timeout=5)
        os.remove(dummy_pdf_path) # Clean up dummy file
        logging.info("Poppler check successful using pdfinfo_from_path with dummy PDF.")
        return True
    except PDFInfoNotInstalledError:
         logging.warning("Poppler check using pdfinfo_from_path failed: PDFInfoNotInstalledError. Trying common paths...")
         if 'dummy_pdf_path' in locals() and os.path.exists(dummy_pdf_path):
             os.remove(dummy_pdf_path)
    except Exception as e_pdfinfo: # Catch other potential errors
        logging.warning(f"Poppler check using pdfinfo_from_path failed: {type(e_pdfinfo).__name__}: {e_pdfinfo}. Trying common paths...")
        if 'dummy_pdf_path' in locals() and os.path.exists(dummy_pdf_path):
             os.remove(dummy_pdf_path)

    # 2. If direct check fails, search common paths and test 'pdfinfo -v'
    common_paths = [
        r"C:\Poppler\poppler-24.08.0\Library\bin", # Custom path first
        r"C:\Program Files\poppler\bin",
        r"C:\Program Files (x86)\poppler\bin",
        r"C:\poppler\bin",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'poppler', 'bin')
    ]
    original_path = os.environ['PATH']

    for path in common_paths:
        pdfinfo_exe = os.path.join(path, 'pdfinfo.exe')
        if os.path.exists(path) and os.path.exists(pdfinfo_exe):
            logging.info(f"Found potential Poppler pdfinfo.exe in: {path}. Verifying execution...")
            try:
                # Temporarily add to PATH for subprocess check
                os.environ['PATH'] = path + os.pathsep + original_path
                # Use subprocess to run 'pdfinfo -v' which should succeed if poppler is working
                result = subprocess.run(['pdfinfo', '-v'], capture_output=True, text=True, check=True, timeout=5)
                logging.info(f"Poppler check successful after adding path {path}. Output: {result.stderr.strip()}")
                # Keep the modified PATH for the rest of the script execution
                return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e_verify:
                 logging.warning(f"Poppler check failed for path {path}: {e_verify}")
                 os.environ['PATH'] = original_path # Restore original PATH if this attempt failed
                 continue # Try next path
            except Exception as e_general: # Catch any other unexpected error
                 logging.error(f"Unexpected error during Poppler verification for path {path}: {e_general}")
                 os.environ['PATH'] = original_path # Restore original PATH
                 continue

    # Restore original PATH if no path worked
    os.environ['PATH'] = original_path
    logging.error("Poppler not found or pdfinfo command failed in common paths and PATH.")
    return False

class PDFReader:
    # Change the default model name here
    def __init__(self, pdf_path, tesseract_path=None, model_name="phi4", ollama_base_url="http://localhost:11434"):
        """
        Initialize the PDF reader.

        Args:
            pdf_path (str): Path to the PDF file.
            tesseract_path (str, optional): Path to Tesseract executable.
            model_name (str): Name of the Ollama model to use (default changed to phi4).
            ollama_base_url (str): Base URL for the Ollama server.
        """
        self.pdf_path = pdf_path
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        # Check Poppler installation (required for pdf2image)
        if not check_poppler_installation():
            logging.error("Poppler is not installed or not found/working in PATH. OCR functionality depends on Poppler.")
            print("\nCRITICAL ERROR: Poppler not found or not working. pdf2image cannot function.")
            print("Please install Poppler and ensure its 'bin' directory is in your system's PATH and the executables run correctly.")
            print("Download from: https://github.com/oschwartz10612/poppler-windows/releases/")
            # Consider raising an exception or exiting if Poppler is essential
            raise RuntimeError("Poppler installation not found or not functional. Cannot proceed with OCR.")
        else:
            logging.info("Poppler found and verified. OCR enabled.")

        # Updated prompt for page analysis and data extraction
        self.page_analysis_prompt = PromptTemplate(
            input_variables=["text"],
            template="""
            Analise o seguinte texto extraído de UMA PÁGINA de um documento PDF:

            Texto da Página:
            {text}

            Tarefas:
            1. Determine se esta página representa o INÍCIO de um NOVO documento lógico (ex: um novo ofício, um novo contrato, uma nova nota fiscal começando nesta página) ou se é uma CONTINUAÇÃO do documento da página anterior.
            2. Extraia as seguintes informações DESTA PÁGINA, se presentes:
                - Título conciso que descreva o conteúdo principal da página.
                - Descrição breve (1-2 frases) do assunto principal da página.
                - Data principal mencionada na página (formato DD/MM/AAAA, se possível).
                - Tipo de documento aparente nesta página (ex: Ofício, Contrato, Nota Fiscal, Relatório, Anexo, Despacho, Indefinido).
                - Número principal do documento/processo mencionado na página.
                - Valor monetário principal (R$) mencionado na página.
                - Objeto ou assunto principal do documento descrito na página.

            Responda OBRIGATORIAMENTE no seguinte formato JSON. Se uma informação não for encontrada, use "Não encontrado" ou null.

            {{
              "novo_documento": true ou false,
              "titulo": "...",
              "descricao": "...",
              "data": "DD/MM/AAAA ou Não encontrado",
              "tipo": "...",
              "numero": "...",
              "valor": "R$ X.XXX,XX ou Não encontrado",
              "objeto": "..."
            }}

            Resposta JSON:
            """
        )

        try:
            self.llm = OllamaLLM(model=model_name, base_url=ollama_base_url)
            # Test connection
            self.llm.invoke("Test prompt")
            logging.info(f"Successfully connected to Ollama model '{model_name}' at {ollama_base_url}")
        except Exception as e:
            logging.error(f"Failed to initialize or connect to Ollama model '{model_name}' at {ollama_base_url}: {e}")
            # Depending on requirements, you might want to raise an error or fallback
            raise RuntimeError(f"Could not connect to Ollama: {e}")

        self.page_analysis_chain = LLMChain(llm=self.llm, prompt=self.page_analysis_prompt)

    def _get_total_pages(self) -> int:
        """Retorna o número total de páginas do PDF usando pdfinfo."""
        try:
            pdf_info = pdfinfo_from_path(self.pdf_path, timeout=30) # Increased timeout
            pages = pdf_info.get('Pages')
            if pages is None:
                 raise ValueError("Could not extract 'Pages' from pdfinfo output.")
            return int(pages) # Ensure it's an integer
        except (PDFInfoNotInstalledError, PDFPageCountError, ValueError, Exception) as e: # Catch more specific errors
            logging.error(f"Could not get page count using pdfinfo: {type(e).__name__}: {e}. Trying pdfplumber.")
            if PDFPLUMBER_AVAILABLE:
                try:
                    with pdfplumber.open(self.pdf_path) as pdf:
                        return len(pdf.pages)
                except Exception as e_plumber:
                    logging.error(f"Could not get page count using pdfplumber: {e_plumber}")
                    raise RuntimeError(f"Failed to determine page count for {self.pdf_path}") from e
            else:
                 raise RuntimeError(f"pdfinfo failed and pdfplumber is not available. Cannot determine page count for {self.pdf_path}") from e

    def _extract_text_from_page_ocr(self, page_number: int, temp_dir: str) -> Optional[str]:
        """Extrai texto de uma única página do PDF usando OCR."""
        image_path = None # Initialize image_path
        try:
            # Convert only the specific page to an image
            images = convert_from_path(
                self.pdf_path,
                dpi=300, # Higher DPI can improve OCR accuracy
                first_page=page_number,
                last_page=page_number,
                fmt='png', # Specify format
                thread_count=1, # Process one page at a time
                output_folder=temp_dir,
                timeout=60 # Timeout for conversion
            )

            if images:
                # pdf2image >= 1.17.0 returns PIL Image objects directly
                # We need to save the image temporarily to pass its path to Tesseract
                # Use a more specific temporary filename
                temp_image_filename = os.path.join(temp_dir, f"page_{page_number}.png")
                images[0].save(temp_image_filename, "PNG")
                image_path = temp_image_filename # Store path for cleanup

                # Apply OCR
                texto = pytesseract.image_to_string(Image.open(image_path), lang='por', config='--psm 3') # PSM 3: Auto page segmentation
                return texto
            else:
                logging.warning(f"Could not convert page {page_number} to image.")
                return None
        except Exception as e:
            logging.error(f"Error during OCR for page {page_number}: {e}")
            return None # Return None on error
        finally:
             # Clean up the temporary image file if it was created
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError as oe:
                    logging.warning(f"Could not remove temporary image {image_path}: {oe}")


    def _parse_llm_response(self, response_text: str, page_number: int) -> Dict:
        """Tenta analisar a resposta JSON do LLM, com fallback."""
        fallback_data = {
            "novo_documento": False, # Default to continuation if unsure
            "titulo": "Erro na Análise",
            "descricao": "Não foi possível analisar a resposta da IA.",
            "data": "Não encontrado",
            "tipo": "Não identificado",
            "numero": "Não encontrado",
            "valor": "Não encontrado",
            "objeto": "Não encontrado"
        }
        try:
            # Clean potential markdown code fences
            if response_text.strip().startswith("```json"):
                response_text = response_text.strip()[7:]
                if response_text.strip().endswith("```"):
                    response_text = response_text.strip()[:-3]

            # Find the JSON part more robustly
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                json_str = match.group(0)
                data = json.loads(json_str)
                # Validate required keys (optional but good practice)
                if "novo_documento" not in data:
                    logging.warning(f"LLM response for page {page_number} missing 'novo_documento'. Assuming False.")
                    data["novo_documento"] = False # Assume continuation if missing
                    # return fallback_data # Or assume False and continue processing other fields
                # Ensure boolean conversion if necessary
                if isinstance(data.get("novo_documento"), str):
                    data["novo_documento"] = data["novo_documento"].strip().lower() == 'true'
                elif not isinstance(data.get("novo_documento"), bool):
                     logging.warning(f"LLM response for page {page_number} has non-boolean 'novo_documento': {data.get('novo_documento')}. Assuming False.")
                     data["novo_documento"] = False


                # Fill missing optional keys with default values
                for key, default_value in fallback_data.items():
                    # Don't overwrite novo_documento if it was successfully parsed/defaulted above
                    if key == "novo_documento":
                        continue
                    if key not in data or data[key] is None or data[key] == "":
                         data[key] = default_value

                return data
            else:
                logging.warning(f"Could not find valid JSON in LLM response for page {page_number}. Response: {response_text[:100]}...")
                return fallback_data
        except json.JSONDecodeError as e:
            logging.error(f"JSONDecodeError for page {page_number}: {e}. Response: {response_text[:100]}...")
            return fallback_data
        except Exception as e:
            logging.error(f"Unexpected error parsing LLM response for page {page_number}: {e}")
            return fallback_data

    def identify_documents_page_by_page(self) -> List[Dict]:
        """
        Identifica documentos processando cada página com OCR e LLM.

        Returns:
            List[Dict]: Uma lista de dicionários, onde cada dicionário representa
                       um documento identificado, contendo metadados consolidados
                       e as páginas inicial/final.
        """
        logging.info(f"Starting page-by-page document identification for: {self.pdf_path}")
        if not os.path.exists(self.pdf_path):
            logging.error(f"PDF file not found: {self.pdf_path}")
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        total_pages = self._get_total_pages()
        if total_pages == 0:
            logging.warning(f"PDF file seems empty or unreadable (0 pages): {self.pdf_path}")
            return []

        logging.info(f"Total pages detected: {total_pages}")

        identified_documents = []
        current_document_pages_data = []
        current_doc_start_page = 1

        # Use a temporary directory for images
        with tempfile.TemporaryDirectory() as temp_dir:
            for page_num in range(1, total_pages + 1):
                logging.info(f"Processing Page {page_num}/{total_pages}...")

                # 1. Extract text using OCR
                page_text = self._extract_text_from_page_ocr(page_num, temp_dir)

                page_analysis_result = None
                if page_text and page_text.strip():
                    logging.info(f"  Page {page_num}: OCR successful ({len(page_text)} chars). Analyzing with LLM...")
                    # 2. Analyze text with LLM
                    try:
                        llm_response = self.page_analysis_chain.invoke({"text": page_text})
                        # Handle potential variations in Langchain output structure
                        if isinstance(llm_response, dict) and "text" in llm_response:
                            response_text = llm_response.get("text", "")
                        elif isinstance(llm_response, str):
                             response_text = llm_response
                        else:
                             response_text = str(llm_response) # Fallback

                        logging.info(f"  Page {page_num}: LLM response received. Parsing...")
                        page_analysis_result = self._parse_llm_response(response_text, page_num)
                        logging.info(f"  Page {page_num}: Parsed analysis: novo_documento={page_analysis_result.get('novo_documento')}, tipo={page_analysis_result.get('tipo')}")
                    except Exception as e:
                        logging.error(f"  Page {page_num}: Error invoking LLM chain: {e}")
                        page_analysis_result = self._parse_llm_response("", page_num) # Use fallback on error
                else:
                    logging.warning(f"  Page {page_num}: No text extracted via OCR or text is empty. Skipping LLM analysis.")
                    # Create a minimal entry for empty/failed pages
                    page_analysis_result = {
                        "novo_documento": False, # Assume continuation for empty pages
                        "titulo": "Página Vazia/Falha OCR",
                        "descricao": "Não foi possível extrair texto.",
                        "data": "Não encontrado", "tipo": "Não identificado", "numero": "Não encontrado",
                        "valor": "Não encontrado", "objeto": "Não encontrado"
                    }

                # 3. Determine document boundaries
                is_new_doc = page_analysis_result.get("novo_documento", False)

                # Force first page to be a new document
                if page_num == 1:
                    is_new_doc = True
                    logging.info(f"  Page {page_num}: Marked as start of the first document.")

                if is_new_doc and current_document_pages_data:
                    # Finalize the previous document
                    end_page = page_num - 1
                    logging.info(f"  Page {page_num}: New document detected. Finalizing previous document (Pages {current_doc_start_page}-{end_page}).")

                    # Consolidate data (using first page's data for now)
                    # --- Consolidation Strategy ---
                    # Simple: Take data from the first page of the segment.
                    # More complex strategies could involve merging data, prioritizing certain pages, etc.
                    consolidated_data = current_document_pages_data[0].copy() # Take data from the first page
                    consolidated_data["pagina_inicio"] = current_doc_start_page
                    consolidated_data["pagina_fim"] = end_page
                    # Remove the per-page flag after consolidation
                    consolidated_data.pop("novo_documento", None)

                    identified_documents.append(consolidated_data)

                    # Start the new document
                    current_doc_start_page = page_num
                    current_document_pages_data = [page_analysis_result]
                else:
                    # Continue current document
                    if is_new_doc and not current_document_pages_data:
                         logging.info(f"  Page {page_num}: Starting the very first document.")
                    elif not is_new_doc:
                         logging.info(f"  Page {page_num}: Continuing current document.")
                    current_document_pages_data.append(page_analysis_result)

            # 4. Add the last document
            if current_document_pages_data:
                end_page = total_pages
                logging.info(f"Processing finished. Finalizing last document (Pages {current_doc_start_page}-{end_page}).")
                consolidated_data = current_document_pages_data[0].copy() # Take data from the first page
                consolidated_data["pagina_inicio"] = current_doc_start_page
                consolidated_data["pagina_fim"] = end_page
                consolidated_data.pop("novo_documento", None)
                identified_documents.append(consolidated_data)

        logging.info(f"Document identification complete. Found {len(identified_documents)} documents.")
        return identified_documents

    # --- Methods below might be deprecated or need refactoring based on the new approach ---

    # Consider removing or refactoring process_pdf, _is_document_break, _process_document,
    # _extract_text_with_ocr (replaced by _extract_text_from_page_ocr),
    # _split_pdf (not needed for page-by-page), extract_text, _show_cursor_variables, _save_cursor_variables
    # if identify_documents_page_by_page becomes the primary method.

    # Keep _process_document's fallback dictionary updated as a reference or for potential reuse.
    def _get_fallback_document_info(self, start_page, end_page):
         """Provides a default structure for error cases."""
         return {
                "titulo": "Documento não identificado",
                "descricao": "Não foi possível extrair informações",
                "data": "Não encontrada",
                "tipo": "Não identificado",
                "numero": "Não encontrado",
                "valor": "Não encontrado",
                "objeto": "Não encontrado",
                "pagina_inicio": start_page,
                "pagina_fim": end_page
            }

# Example Usage (optional, for testing)
if __name__ == '__main__':
    # Configure Tesseract path if needed
    # tesseract_cmd_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Example path
    tesseract_cmd_path = None # Set to None if Tesseract is in PATH

    # Configure Ollama details
    ollama_url = "http://localhost:11434" # Default Ollama URL
    # Change the default model name here too
    ollama_model = "phi4" # Or "llama3", "mistral", etc.

    # --- !!! IMPORTANT: SET YOUR PDF FILE PATH HERE !!! ---
    pdf_file_to_process = r"C:\Users\Cirilo\Documents\licitia\licitia\data\input\test.pdf" # <--- EXAMPLE PATH

    if not pdf_file_to_process or not os.path.exists(pdf_file_to_process):
        print(f"Error: PDF file not found at '{pdf_file_to_process}' or path is not set.")
        print("Please set the 'pdf_file_to_process' variable in the script.")
    else:
        try:
            print(f"Initializing PDFReader for: {pdf_file_to_process}")
            # The reader will now use 'phi4' by default if model_name isn't specified here
            reader = PDFReader(
                pdf_path=pdf_file_to_process,
                tesseract_path=tesseract_cmd_path,
                # model_name=ollama_model, # You can explicitly pass it too
                ollama_base_url=ollama_url
            )

            print("\nStarting document identification...")
            identified_docs = reader.identify_documents_page_by_page()
            print("\n--- Document Identification Results ---")

            if identified_docs:
                for i, doc in enumerate(identified_docs):
                    print(f"\nDocument {i+1}:")
                    print(f"  Páginas: {doc.get('pagina_inicio')} - {doc.get('pagina_fim')}")
                    print(f"  Título: {doc.get('titulo')}")
                    print(f"  Tipo: {doc.get('tipo')}")
                    print(f"  Data: {doc.get('data')}")
                    print(f"  Número: {doc.get('numero')}")
                    print(f"  Valor: {doc.get('valor')}")
                    print(f"  Objeto: {doc.get('objeto')}")
                    print(f"  Descrição: {doc.get('descricao')}")
            else:
                print("No documents were identified.")

        except FileNotFoundError as e:
            print(f"Error: {e}")
        except RuntimeError as e:
            # Catch the specific Poppler error from __init__
            print(f"Initialization Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            logging.exception("Unexpected error during main execution.") # Log traceback