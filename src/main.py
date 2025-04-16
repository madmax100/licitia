import sys
import os
import argparse
import json
import subprocess
from datetime import datetime
import logging # Import logging

# Adiciona o diretório principal ao path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Import the refactored PDFReader
from utils.pdf_reader import PDFReader
# Remove unused imports:
# from utils.ocr_helper import OCRHelper
# from models.ai_processor import AIProcessor
# from src.utils.deps_helper import configure_poppler # Poppler check is now inside PDFReader

# Setup basic logging (optional but good practice)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Analyze PDF documents using AI')
    parser.add_argument('--pdf', '-p', required=True, help='Path to the PDF file')
    parser.add_argument('--output', '-o', default='output', help='Output directory')
    # Default model changed to phi4 to match PDFReader default
    parser.add_argument('--model', '-m', default='phi4', help='Ollama model to use')
    parser.add_argument('--tesseract', '-t', default=None, help='Path to Tesseract executable')
    parser.add_argument('--server', '-s', default='http://localhost:11434', help='Ollama server URL')
    # Removed proxy arguments as they are not currently used by PDFReader's Langchain implementation
    # parser.add_argument('--proxy', default=None, help='Proxy URL (e.g., http://proxy.example.com:8080)')
    # parser.add_argument('--proxy-user', default=None, help='Username for proxy authentication')
    # parser.add_argument('--proxy-pass', default=None, help='Password for proxy authentication')

    return parser.parse_args()

def check_and_pull_ollama_model(model_name):
    """Checks if an Ollama model exists locally and pulls it if not."""
    try:
        # Check if model exists
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=True, encoding='utf-8')
        if model_name in result.stdout:
            logging.info(f"Model '{model_name}' found locally.")
            return True

        logging.warning(f"Model '{model_name}' not found locally. Attempting to pull...")

        # Attempt to pull the model
        pull_command = ['ollama', 'pull', model_name]
        logging.info(f"Running command: {' '.join(pull_command)}")

        # Use shell=True on Windows if needed, but try without first for security
        # Stream the output
        process = subprocess.Popen(pull_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        # Print output line by line
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip(), flush=True) # Ensure output is flushed

        rc = process.poll()
        if rc == 0:
            logging.info(f"Successfully pulled model '{model_name}'.")
            return True
        else:
            logging.error(f"Failed to pull model '{model_name}'. Error code: {rc}. Check Ollama installation and network connection.")
            return False

    except FileNotFoundError:
        logging.error("Error: 'ollama' command not found. Make sure Ollama is installed and in your PATH.")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Error checking/pulling Ollama model: {e}")
        logging.error(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during model check/pull: {e}")
        return False


def analyze_pdf(pdf_path, output_dir, model_name, tesseract_path, server_url):
    """Analyzes the PDF using the refactored PDFReader."""

    # Ensure the specified model is available
    model_available = check_and_pull_ollama_model(model_name)
    if not model_available:
        logging.error(f"Required Ollama model '{model_name}' is not available. Aborting.")
        print(f"❌ Error: Could not find or pull the Ollama model '{model_name}'. Please ensure Ollama is running and the model name is correct.")
        return # Stop execution if model is unavailable

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Initialize PDFReader (it handles Poppler check, Ollama connection, etc.)
        logging.info(f"Initializing PDFReader for: {pdf_path}")
        pdf_reader = PDFReader(
            pdf_path=pdf_path,
            tesseract_path=tesseract_path,
            model_name=model_name,
            ollama_base_url=server_url
        )

        # Call the main processing method
        logging.info("Starting document identification...")
        identified_docs = pdf_reader.identify_documents_page_by_page()
        logging.info(f"Document identification complete. Found {len(identified_docs)} documents.")

        # --- Process and Save Results ---
        if not identified_docs:
            print("⚠️ No documents were identified in the PDF.")
            return

        # Prepare results in the desired final format (using the keys from identified_docs)
        results_to_save = []
        for i, doc_data in enumerate(identified_docs):
            result = {
                "documento_id": i + 1,
                "pagina_inicio": doc_data.get("pagina_inicio", "N/A"),
                "pagina_fim": doc_data.get("pagina_fim", "N/A"),
                "titulo": doc_data.get("titulo", "Não encontrado"),
                "descricao": doc_data.get("descricao", "Não encontrado"),
                "data": doc_data.get("data", "Não encontrado"),
                "tipo": doc_data.get("tipo", "Não identificado"),
                "numero": doc_data.get("numero", "Não encontrado"),
                "valor": doc_data.get("valor", "Não encontrado"),
                "objeto": doc_data.get("objeto", "Não encontrado"),
                # Add page count for convenience
                "contagem_paginas": doc_data.get("pagina_fim", 0) - doc_data.get("pagina_inicio", 1) + 1
            }
            results_to_save.append(result)
            print(f"✅ Processed Document {result['documento_id']}: {result['titulo']} (Pages {result['pagina_inicio']}-{result['pagina_fim']})")


        # Save results to JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename_base = os.path.splitext(os.path.basename(pdf_path))[0]
        output_filename = f"{pdf_filename_base}_analysis_{timestamp}.json"
        output_filepath = os.path.join(output_dir, output_filename)

        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(results_to_save, f, ensure_ascii=False, indent=2)
            logging.info(f"Results successfully saved to: {output_filepath}")
            print(f"\n💾 Results saved to: {output_filepath}")
        except IOError as e:
            logging.error(f"Failed to save results to {output_filepath}: {e}")
            print(f"❌ Error saving results file: {e}")

    except FileNotFoundError as e:
        logging.error(f"Error: {e}")
        print(f"❌ File Error: {e}")
    except RuntimeError as e:
        # Catch errors from PDFReader initialization (like Poppler or Ollama connection issues)
        logging.error(f"Initialization Error: {e}")
        print(f"❌ Runtime Error during initialization: {e}")
    except Exception as e:
        logging.exception("An unexpected error occurred during PDF analysis.") # Log full traceback
        print(f"❌ An unexpected error occurred: {e}")


def main():
    # Poppler configuration is now handled inside PDFReader's __init__ via check_poppler_installation()
    # No need to configure it explicitly here unless check_poppler_installation fails and you need manual intervention.

    args = parse_arguments()

    analyze_pdf(
        pdf_path=args.pdf,
        output_dir=args.output,
        model_name=args.model,
        tesseract_path=args.tesseract,
        server_url=args.server
        # Removed proxy args as they are not used in the current PDFReader
    )

if __name__ == "__main__":
    main()