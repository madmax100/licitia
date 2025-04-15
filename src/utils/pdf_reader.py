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
from typing import List, Dict, Tuple
from pdf2image import convert_from_path
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_ollama import OllamaLLM

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

def check_poppler_installation():
    """Verifica se o Poppler está instalado e no PATH."""
    try:
        # Tenta executar o comando pdfinfo
        result = subprocess.run(['pdfinfo'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE,
                              text=True,
                              timeout=2)
        
        # Se o comando retornar algo (mesmo que seja erro), significa que o pdfinfo existe
        return True
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        # Verifica se o Poppler está em locais comuns no Windows
        common_paths = [
            # Adicione o caminho personalizado como primeira opção
            r"C:\Users\Cirilo\Downloads\Release-24.08.0-0\poppler-24.08.0\Library\bin",
            r"C:\Program Files\poppler\bin",
            r"C:\Program Files (x86)\poppler\bin",
            r"C:\poppler\bin",
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'poppler', 'bin')
        ]
        
        for path in common_paths:
            if os.path.exists(path) and os.path.exists(os.path.join(path, 'pdfinfo.exe')):
                # Adiciona o caminho ao PATH do processo atual
                print(f"🔍 Poppler encontrado em: {path}")
                os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                return True
        
        return False

class PDFReader:
    def __init__(self, pdf_path, tesseract_path=None, use_ocr=True, max_pages_per_doc=20, model_name="phi4"):
        """
        Initialize the PDF reader.
        
        Args:
            pdf_path (str): Path to the PDF file
            tesseract_path (str, optional): Path to Tesseract executable
        """
        self.pdf_path = pdf_path
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # Verifica se o Poppler está instalado
        if use_ocr:
            if not check_poppler_installation():
                print("\nAVISO: Poppler não encontrado. O OCR será desativado.")
                print("Para instalar o Poppler no Windows:")
                print("1. Baixe o Poppler do site: https://github.com/oschwartz10612/poppler-windows/releases/")
                print("2. Extraia o arquivo ZIP")
                print("3. Copie a pasta 'bin' para C:\\Program Files\\poppler\\bin")
                print("4. Adicione C:\\Program Files\\poppler\\bin ao PATH do sistema")
                print("5. Reinicie o computador")
                self.use_ocr = False
            else:
                print("Poppler encontrado com sucesso! OCR ativado.")
        
        # Template para extrair informações do documento
        self.prompt_template = PromptTemplate(
            input_variables=["text"],
            template="""
            Analise o seguinte texto e extraia as seguintes informações:
            1. Título do documento
            2. Data de assinatura (se houver)
            
            Texto: {text}
            
            Responda no formato JSON:
            {{
                "titulo": "título do documento",
                "data_assinatura": "data de assinatura (se encontrada)"
            }}
            """
        )
        
        self.llm = OllamaLLM(model=model_name)
        self.use_ocr = use_ocr
        self.max_pages_per_doc = max_pages_per_doc

    def _get_total_pages(self, pdf_path: str) -> int:
        """Retorna o número total de páginas do PDF."""
        with pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)

    def _split_pdf(self, pdf_path: str) -> List[str]:
        """Divide o PDF em arquivos menores se necessário."""
        total_pages = self._get_total_pages(pdf_path)
        if total_pages <= self.max_pages_per_doc:
            return [pdf_path]
        
        # Cria diretório temporário para os PDFs divididos
        temp_dir = tempfile.mkdtemp()
        pdf_files = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for i in range(0, total_pages, self.max_pages_per_doc):
                end_page = min(i + self.max_pages_per_doc, total_pages)
                output_path = os.path.join(temp_dir, f'parte_{i//self.max_pages_per_doc + 1}.pdf')
                
                # Cria um novo PDF com as páginas do intervalo
                with pdfplumber.open(pdf_path) as source:
                    pages = source.pages[i:end_page]
                    with pdfplumber.open(output_path, 'wb') as dest:
                        for page in pages:
                            dest.add_page(page)
                
                pdf_files.append(output_path)
        
        return pdf_files

    def _extract_text_with_ocr(self, pdf_path: str) -> List[str]:
        """Extrai texto de cada página do PDF usando OCR."""
        if not check_poppler_installation():
            raise RuntimeError("Poppler não está instalado. Por favor, instale o Poppler para usar OCR.")
            
        textos = []
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Converte PDF para imagens
                images = convert_from_path(pdf_path)
                
                for i, image in enumerate(images):
                    # Salva a imagem temporariamente
                    temp_image_path = os.path.join(temp_dir, f'page_{i}.png')
                    image.save(temp_image_path, 'PNG')
                    
                    # Aplica OCR na imagem
                    texto = pytesseract.image_to_string(Image.open(temp_image_path), lang='por')
                    textos.append(texto)
            except Exception as e:
                print(f"Erro durante a conversão do PDF: {e}")
                raise RuntimeError("Erro ao converter PDF para imagens. Verifique se o Poppler está instalado corretamente.")
        
        return textos

    def _show_cursor_variables(self, current_doc: Dict, i: int, total_pages: int):
        """Mostra as variáveis armazenadas no cursor."""
        print("\nVariáveis do cursor:")
        print(f"Página atual: {i}/{total_pages}")
        print(f"Página de início do documento atual: {current_doc.get('pagina_inicio', 'N/A')}")
        print(f"Página de fim do documento atual: {current_doc.get('pagina_fim', 'N/A')}")
        print(f"Tamanho do texto atual: {len(current_doc.get('texto', ''))} caracteres")
        print(f"Primeiros 100 caracteres do texto: {current_doc.get('texto', '')[:100]}...")
        print("-" * 50)

   
        """Salva as variáveis do cursor em um arquivo JSON."""
        log_file = "cursor_variables.json"
        
        # Cria o dicionário com as variáveis
        cursor_data = {
            "pagina_atual": i,
            "total_paginas": total_pages,
            "documento_atual": {
                "pagina_inicio": current_doc.get('pagina_inicio', 'N/A'),
                "pagina_fim": current_doc.get('pagina_fim', 'N/A'),
                "tamanho_texto": len(current_doc.get('texto', '')),
                "primeiros_100_caracteres": current_doc.get('texto', '')[:100]
            }
        }
        
        # Se o arquivo já existe, carrega os dados existentes
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = {"registros": []}
        else:
            existing_data = {"registros": []}
        
        # Adiciona o novo registro
        existing_data["registros"].append(cursor_data)
        
        # Salva os dados atualizados
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

    def process_pdf(self, pdf_path: str) -> Tuple[List[Dict], int]:
        """Processa o PDF e retorna informações sobre cada documento e o total de páginas."""
        total_pages = self._get_total_pages(pdf_path)
        pdf_files = self._split_pdf(pdf_path)
        all_documentos = []
        
        # Limpa o arquivo de log se ele existir
        if os.path.exists("cursor_variables.json"):
            os.remove("cursor_variables.json")
        
        for pdf_file in pdf_files:
            documentos = []
            
            if self.use_ocr:
                try:
                    # Extrai texto usando OCR
                    textos = self._extract_text_with_ocr(pdf_file)
                except RuntimeError as e:
                    print(f"Erro ao usar OCR: {e}")
                    print("Continuando com extração de texto normal...")
                    self.use_ocr = False
                    textos = []
                    with pdfplumber.open(pdf_file) as pdf:
                        for page in pdf.pages:
                            texto = page.extract_text()
                            textos.append(texto if texto else "")
            else:
                # Extrai texto diretamente do PDF
                textos = []
                with pdfplumber.open(pdf_file) as pdf:
                    for page in pdf.pages:
                        texto = page.extract_text()
                        textos.append(texto if texto else "")
            
            current_doc = {
                "pagina_inicio": 1,
                "texto": ""
            }
            
            for i, texto in enumerate(textos, 1):
                print(f"\rAnalisando página {i} de {total_pages}...", end="")
                if not texto.strip():
                    continue
                
                # Salva as variáveis do cursor a cada 10 páginas
                if i % 10 == 0:
                    self._save_cursor_variables(current_doc, i, total_pages)
                
                # Verifica se há uma quebra clara de documento
                if self._is_document_break(texto):
                    if current_doc["texto"]:
                        # Processa o documento atual
                        print(f"\nIdentificado novo documento na página {i}")
                        info = self._process_document(current_doc)
                        documentos.append(info)
                    
                    # Inicia novo documento
                    current_doc = {
                        "pagina_inicio": i,
                        "texto": texto
                    }
                else:
                    current_doc["texto"] += "\n" + texto
                    current_doc["pagina_fim"] = i
            
            # Processa o último documento
            if current_doc["texto"]:
                info = self._process_document(current_doc)
                documentos.append(info)
            
            all_documentos.extend(documentos)
        
        print("\nAnálise concluída!")
        print(f"Variáveis do cursor salvas em cursor_variables.json")
        return all_documentos, total_pages

    def _is_document_break(self, texto: str) -> bool:
        """Verifica se há uma quebra clara de documento."""
        # Texto muito curto geralmente indica uma quebra (página de separação ou início de documento)
        if len(texto.strip()) < 150 and len(texto.strip()) > 10:
            # Pequenos textos isolados frequentemente são separadores ou páginas de título
            return True
            
        # Verifica se o texto começa com numeração (comum em novos documentos)
        if re.match(r'^\s*\d+[\.-]\s+', texto[:50]):
            return True
            
        # Verifica se há cabeçalhos comuns que indicam novos documentos
        cabecalhos = ['ofício', 'memorando', 'relatório', 'carta', 'despacho', 'certidão', 
                      'parecer', 'anexo', 'termo', 'formulário', 'requerimento', 'documento',
                      'comprovante', 'declaração', 'notificação', 'intimação', 'informação',
                      'pedido', 'solicitação', 'prestação', 'aviso', 'comunicado']
                      
        for cabecalho in cabecalhos:
            if re.search(fr'^\s*{cabecalho}\b', texto[:100], re.IGNORECASE):
                return True
        
        # Verifica se começa com data (comum em novos documentos)
        if re.search(r'^\s*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}', texto[:50]):
            return True
            
        # Verifica por números de processo, protocolos, etc.
        if re.search(r'\b(processo|sei|protocolo|registro)[\s\.:].*?\d+', texto[:200], re.IGNORECASE):
            return True
            
        # Verifica números de documentos
        if re.search(r'\b(n[º°\.]*|número)[\s:]*\d+[/.-]?\d*', texto[:200], re.IGNORECASE):
            return True
            
        # Verifica por assinaturas no final da página anterior
        if re.search(r'(atenciosamente|respeitosamente|cordialmente)\s*[,\.]\s*$', texto, re.IGNORECASE):
            return True
            
        # Padrões que podem indicar início de novo documento
        padroes = [
            r"^\s*DOCUMENTO\s*",
            r"^\s*CONTRATO\s*",
            r"^\s*TERMO\s*DE\s*",
            r"^\s*ATA\s*DE\s*",
            r"^\s*PROCESSO\s*",
            r"^\s*PETIÇÃO\s*",
            r"^\s*SENTENÇA",
            r"^\s*DECISÃO",
            r"^\s*DESPACHO",
            r"^\s*CERTIDÃO",
            r"^\s*REQUERIMENTO",
            r"^\s*OFÍCIO",
            r"^\s*NOTIFICAÇÃO",
            r"^\s*INTIMAÇÃO",
            r"^\s*CITAÇÃO",
            r"^\s*MANDADO",
            r"^\s*EDITAL",
            r"^\s*LAUDO",
            r"^\s*PERÍCIA",
            r"^\s*INQUÉRITO",
            r"^\s*MINISTÉRIO\s*",
            r"^\s*DEPARTAMENTO\s*",
            r"^\s*SECRETARIA\s*",
            r"^\s*DELEGACIA\s*",
            r"^\s*PLANILHA\s*"
        ]
        
        # Verifica se o texto começa com algum dos padrões
        for padrao in padroes:
            if re.search(padrao, texto[:200], re.IGNORECASE):
                return True
                
        # Verifica por cabeçalhos/logos no topo da página
        if re.search(r'^[\s\*=-]{0,10}[A-ZÇÁÉÍÓÚÂÊÎÔÛÃÕ\s]{10,}[\s\*=-]{0,10}$', texto[:200], re.MULTILINE):
            return True
        
        # Verifica por uma mudança significativa no conteúdo
        palavras_chave = ["processo", "petição", "sentença", "decisão", "despacho",
                          "certidão", "requerimento", "ofício", "notificação", "intimação",
                          "citação", "mandado", "edital", "laudo", "perícia", "inquérito",
                          "planilha", "orçamentária", "projeto", "básico", "licitação",
                          "proposta", "contrato", "parecer", "ata", "memorial", "cronograma",
                          "termo", "relatório", "requisição", "empenho", "comprovante"]
        
        # Conta a ocorrência de palavras-chave no texto - precisa de pelo menos 2
        contagem = sum(1 for palavra in palavras_chave if palavra.lower() in texto.lower())
        return contagem >= 2

    def _process_document(self, doc: Dict) -> Dict:
        """Processa um documento individual usando o modelo de IA."""
        try:
            # Template mais detalhado para extrair informações
            prompt_template = PromptTemplate(
                input_variables=["text"],
                template="""
                Analise o seguinte texto e extraia as seguintes informações:
                1. Título do documento (se houver)
                2. Descrição do documento (resumo do conteúdo)
                3. Data do documento (se houver)
                4. Tipo de documento (contrato, edital, parecer, etc)
                5. Número do documento (se houver)
                6. Valor (se mencionado)
                7. Objeto (se mencionado)
                
                Texto: {text}
                
                Responda no formato JSON:
                {{
                    "titulo": "título do documento",
                    "descricao": "descrição do documento",
                    "data": "data do documento",
                    "tipo": "tipo do documento",
                    "numero": "número do documento",
                    "valor": "valor mencionado",
                    "objeto": "objeto do documento"
                }}
                """
            )
            
            chain = LLMChain(llm=self.llm, prompt=prompt_template)
            resultado = chain.invoke({"text": doc["texto"]})
            info = json.loads(resultado["text"])
            
            # Adiciona informações de paginação
            info.update({
                "pagina_inicio": doc["pagina_inicio"],
                "pagina_fim": doc.get("pagina_fim", doc["pagina_inicio"])
            })
            
            return info
        except Exception as e:
            print(f"Erro ao processar documento: {e}")
            return {
                "titulo": "Documento não identificado",
                "descricao": "Não foi possível extrair informações",
                "data": "Não encontrada",
                "tipo": "Não identificado",
                "numero": "Não encontrado",
                "valor": "Não encontrado",
                "objeto": "Não encontrado",
                "pagina_inicio": doc["pagina_inicio"],
                "pagina_fim": doc.get("pagina_fim", doc["pagina_inicio"])
            }
    
    def extract_text(self, use_ocr=False):
        """
        Extract text from a PDF file using PyMuPDF with fallback to pdfplumber.
        
        Args:
            use_ocr (bool): Whether to use OCR for text extraction
            
        Returns:
            list: List of strings containing text for each page
        """
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")
        
        # Tenta primeiro com pdfplumber (que sabemos que está sendo importado)
        try:
            pages_content = []
            with pdfplumber.open(self.pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=3, y_tolerance=3)
                    pages_content.append(text if text else "")
                    
            print(f"✅ Texto extraído com pdfplumber: {len(pages_content)} páginas")
            return pages_content
                    
        except Exception as e:
            print(f"⚠️ Error with pdfplumber: {e}. Tentando com OCR...")
            
            # Fallback para OCR se pdfplumber falhar
            if use_ocr:
                try:
                    print("🔍 Iniciando extração com OCR...")
                    images = convert_from_path(self.pdf_path)
                    
                    pages_content = []
                    for i, image in enumerate(images):
                        # Aplica OCR na imagem
                        text = pytesseract.image_to_string(image, lang='por')
                        pages_content.append(text)
                        
                    print(f"✅ Texto extraído com OCR: {len(pages_content)} páginas")
                    return pages_content
                    
                except Exception as e2:
                    raise Exception(f"Failed to extract text with both pdfplumber and OCR: {e}, {e2}")
                
            else:
                raise Exception(f"pdfplumber failed and no valid text was extracted: {e}")

    def identify_document_boundaries(self, pages_content, ai_processor=None):
        """
        Identifica os limites de cada documento no PDF usando o modelo de IA,
        já extraindo resumo, data e valores de cada página.
        """
        print("🔍 Identificando limites de documentos no PDF (usando IA página por página)...")

        documents = []
        current_doc_pages = []
        current_doc_start = 0
        current_doc_resumos = []
        current_doc_datas = []
        current_doc_valores = []

        # Prompt para o modelo decidir se é início de novo documento e extrair informações
        boundary_prompt = PromptTemplate(
            input_variables=["text"],
            template=(
                "O texto a seguir foi extraído de uma página de um PDF.\n"
                "1. Responda apenas com 'SIM' se esta página é o INÍCIO de um novo documento, ou 'NÃO' caso contrário.\n"
                "2. Extraia um resumo curto do conteúdo da página.\n"
                "3. Se houver, extraia a data principal e valores monetários.\n"
                "Responda no formato JSON:\n"
                "{\n"
                "  \"novo_documento\": \"SIM\" ou \"NÃO\",\n"
                "  \"resumo\": \"...\",\n"
                "  \"data\": \"...\",\n"
                "  \"valores\": [ ... ]\n"
                "}\n"
                "Texto:\n{text}\n"
                "Resposta:"
            )
        )
        chain = boundary_prompt | self.llm

        for i, page_content in enumerate(pages_content):
            is_new_doc = False
            page_number = i + 1
            resumo = ""
            data = ""
            valores = []

            # Sempre novo documento na primeira página
            if i == 0:
                is_new_doc = True
                print(f"  📄 Página {page_number}: Início do primeiro documento")
            else:
                # Usa o modelo para decidir e extrair informações
                try:
                    resposta = chain.invoke({"text": page_content})
                    info = json.loads(resposta)
                    is_new_doc = info.get("novo_documento", "").strip().upper().startswith("SIM")
                    resumo = info.get("resumo", "")
                    data = info.get("data")
                    valores = info.get("valores", [])
                except Exception as e:
                    print(f"⚠️ Erro ao consultar IA ou interpretar resposta na página {page_number}: {e}")
                    # fallback simples
                    is_new_doc = self._is_document_break(page_content)
                    resumo = ""
                    data = ""
                    valores = []

            # Se for novo documento e já temos páginas acumuladas, finalize o anterior
            if is_new_doc and current_doc_pages:
                doc_end = i
                documents.append({
                    "start_page": current_doc_start + 1,
                    "end_page": doc_end,
                    "pages_content": current_doc_pages,
                    "resumos": current_doc_resumos,
                    "datas": current_doc_datas,
                    "valores": current_doc_valores
                })
                print(f"  ✅ Documento finalizado: páginas {current_doc_start+1}-{doc_end}")
                # Inicia novo documento
                current_doc_pages = [page_content]
                current_doc_start = i
                current_doc_resumos = [resumo]
                current_doc_datas = [data]
                current_doc_valores = [valores]
            else:
                current_doc_pages.append(page_content)
                current_doc_resumos.append(resumo)
                current_doc_datas.append(data)
                current_doc_valores.append(valores)

        # Adiciona o último documento
        if current_doc_pages:
            documents.append({
                "start_page": current_doc_start + 1,
                "end_page": len(pages_content),
                "pages_content": current_doc_pages,
                "resumos": current_doc_resumos,
                "datas": current_doc_datas,
                "valores": current_doc_valores
            })
            print(f"  ✅ Documento final: páginas {current_doc_start+1}-{len(pages_content)}")

        print(f"📑 Identificados {len(documents)} documentos no PDF")
        return documents

    # Adicione esta função auxiliar para calcular similaridade de texto
    def _text_similarity(self, text1, text2):
        """Calcula a similaridade entre dois textos (medida simples)"""
        if not text1 or not text2:
            return 0
            
        # Remove espaços e pontuação para comparação
        t1 = re.sub(r'[^\w\s]', '', text1.lower())
        t2 = re.sub(r'[^\w\s]', '', text2.lower())
        
        # Divide em palavras
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        # Calcula interseção
        common = words1.intersection(words2)
        
        # Calcula coeficiente de Jaccard
        if len(words1) == 0 and len(words2) == 0:
            return 1.0
        elif len(words1) == 0 or len(words2) == 0:
            return 0.0
        else:
            return len(common) / (len(words1) + len(words2) - len(common))