import sys
import os
import argparse  # Adicionar esta linha
import json  # Também precisamos disso para o JSON dump
import subprocess
from datetime import datetime  # Para o timestamp

# Adiciona o diretório principal ao path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Import modules
from utils.pdf_reader import PDFReader
from utils.ocr_helper import OCRHelper
from models.ai_processor import AIProcessor
from src.utils.deps_helper import configure_poppler

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Analyze PDF documents using AI')
    parser.add_argument('--pdf', '-p', required=True, help='Path to the PDF file')
    parser.add_argument('--output', '-o', default='output', help='Output directory')
    parser.add_argument('--model', '-m', default='llava', help='Ollama model to use')
    parser.add_argument('--tesseract', '-t', default=None, help='Path to Tesseract executable')
    parser.add_argument('--server', '-s', default='http://localhost:11434', help='Ollama server URL')
    parser.add_argument('--proxy', default=None, help='Proxy URL (e.g., http://proxy.example.com:8080)')
    parser.add_argument('--proxy-user', default=None, help='Username for proxy authentication')
    parser.add_argument('--proxy-pass', default=None, help='Password for proxy authentication')

    return parser.parse_args()

def check_and_pull_ollama_model(model_name, proxy_url=None, proxy_user=None, proxy_password=None):
    """Checks if an Ollama model exists locally and pulls it if not, using proxy if configured."""
    try:
        # Check if model exists
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=True, encoding='utf-8')
        if model_name in result.stdout:
            print(f"✅ Model '{model_name}' found locally.")
            return True

        print(f"⚠️ Model '{model_name}' not found locally. Attempting to pull...")

        # Prepare environment variables for proxy
        pull_env = os.environ.copy()
        proxy_set_in_script = False
        if proxy_url:
            proxy_auth = ""
            if proxy_user and proxy_password:
                proxy_auth = f"{proxy_user}:{proxy_password}@"
            proxy_with_auth = proxy_url.replace("://", f"://{proxy_auth}")

            # Only set if not already defined in environment
            if "HTTP_PROXY" not in pull_env:
                 pull_env["HTTP_PROXY"] = proxy_with_auth
                 proxy_set_in_script = True
            if "HTTPS_PROXY" not in pull_env:
                 pull_env["HTTPS_PROXY"] = proxy_with_auth # Ollama CLI uses HTTPS_PROXY for registry
                 proxy_set_in_script = True

        if proxy_set_in_script:
             print(f"🔧 Using proxy {proxy_url} for ollama pull.")
        elif "HTTPS_PROXY" in pull_env or "HTTP_PROXY" in pull_env:
             print("🔧 Using system proxy settings for ollama pull.")
        else:
             print("ℹ️ No proxy configured for ollama pull.")


        # Attempt to pull the model
        pull_command = ['ollama', 'pull', model_name]
        print(f"🚀 Running command: {' '.join(pull_command)}")

        # Use shell=True on Windows if needed, but try without first for security
        process = subprocess.Popen(pull_command, env=pull_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        # Print output line by line
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())

        rc = process.poll()
        if rc == 0:
            print(f"✅ Successfully pulled model '{model_name}'.")
            return True
        else:
            print(f"❌ Failed to pull model '{model_name}'. Error code: {rc}. Check proxy settings and network connection.")
            return False

    except FileNotFoundError:
        print("❌ Error: 'ollama' command not found. Make sure Ollama is installed and in your PATH.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking/pulling Ollama model: {e}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during model check/pull: {e}")
        return False


def analyze_pdf(pdf_path, output_dir, model_name, tesseract_path, server_url,
               proxy_url=None, proxy_user=None, proxy_password=None):
    # Substitua esta linha:
    model_available = check_and_pull_ollama_model(model_name, proxy_url, proxy_user, proxy_password)
    
    # Resto do código permanece igual
    force_offline = not model_available
    if force_offline:
        print("⚠️ Proceeding in offline mode as the required model could not be pulled.")
    
    # Inicializa os componentes
    pdf_reader = PDFReader(pdf_path, tesseract_path=tesseract_path)
    ocr_helper = OCRHelper(tesseract_path=tesseract_path)
    ai_processor = AIProcessor(
        model=model_name,
        server_url=server_url,
        proxy_url=proxy_url,
        proxy_user=proxy_user,
        proxy_password=proxy_password
    )

    # Force offline mode in AI processor if model pull failed
    if force_offline:
        ai_processor.offline_mode = True


    print(f"🔍 Analyzing PDF: {pdf_path}")

    # Extract text from PDF
    try:
        pages_content = pdf_reader.extract_text()
        print(f"📄 Extracted text from {len(pages_content)} pages")
    except Exception as e:
        print(f"❌ Error extracting text from PDF: {e}")
        return

    # Identify document boundaries inteligentemente
    documents = pdf_reader.identify_document_boundaries(pages_content, ai_processor)
    print(f"📑 Identified {len(documents)} documents in the PDF")

    # Process each document
    results = []

    for i, doc in enumerate(documents):
        print(f"\n📝 Processing document {i+1} of {len(documents)}...")
        start_page = doc["start_page"]
        end_page = doc["end_page"]
        
        # Combine all pages of this document
        doc_text = "\n\n".join(doc["pages_content"])
        
        # Get metadata using AI or fallback
        try:
            metadata = ai_processor.process_document(doc_text)
        except Exception as e:
            print(f"❌ Error processing document with AI: {e}")
            metadata = {"title": f"Document {i+1}", "summary": "Error processing", "date": None}
        
        # Create result
        result = {
            "document_id": i + 1,
            "start_page": start_page,
            "end_page": end_page,
            "title": metadata["title"],
            "summary": metadata["summary"],
            "date": metadata["date"],
            "page_count": end_page - start_page + 1
        }
        
        # Add values if they exist
        if doc.get("values") or metadata.get("valores"):
            result["values"] = doc.get("values") or metadata.get("valores")
        
        results.append(result)
        print(f"✅ Processed document: {result['title']}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = os.path.basename(pdf_path)
    output_file = os.path.join(output_dir, f"{pdf_filename}_{timestamp}.json")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Results saved to: {output_file}")

def main():
    # Configura o Poppler explicitamente com o caminho fornecido
    poppler_path = r"C:\Users\Cirilo\Downloads\Release-24.08.0-0\poppler-24.08.0\Library\bin"
    
    if os.path.exists(poppler_path):
        print(f"✅ Adicionando Poppler ao PATH: {poppler_path}")
        os.environ['PATH'] = poppler_path + os.pathsep + os.environ['PATH']
    
    # Continua com o código existente
    args = parse_arguments()
    analyze_pdf(
        args.pdf,
        args.output,
        args.model,
        args.tesseract,
        args.server,
        args.proxy,
        args.proxy_user,
        args.proxy_pass
    )

if __name__ == "__main__":
    main()