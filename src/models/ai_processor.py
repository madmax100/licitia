import requests
import re
import json
from functools import lru_cache

class AIProcessor:
    def __init__(self, model, server_url, proxy_url=None, proxy_user=None, proxy_password=None):
        """
        Inicializa o processador de AI.
        
        Args:
            model (str): Nome do modelo a ser usado (llava, mistral, etc.)
            server_url (str): URL do servidor Ollama
        """
        self.model = model
        self.server_url = server_url
        self.proxy_url = proxy_url
        self.proxy_user = proxy_user
        self.proxy_password = proxy_password
        self.offline_mode = False
        self.chunk_size = 1000  # Tamanho dos chunks para processamento

    def process_document(self, text):
        print(f"🤖 Tentando processar com o modelo {self.model} (todas as partes)...")
        
        if self.offline_mode:
            print("⚠️ Modo offline ativado. Usando processamento local.")
            return self._local_fallback_processing(text)
        
        # Dividir o texto em partes menores
        chunks = self._split_text_into_chunks(text)
        print(f"🔄 Documento dividido em {len(chunks)} partes para processamento completo")
        
        # Processar cada parte usando o modelo
        titles = []
        summary_parts = []
        dates = []
        valores = []
        
        for i, chunk in enumerate(chunks):
            print(f"  🔍 Processando parte {i+1}/{len(chunks)}...")
            # Processar cada parte com timeout estendido
            try:
                url = f"{self.server_url}/api/generate"
                
                prompt_text = f"""Extraia as seguintes informações desta parte do documento:

{chunk}

Retorne um JSON com os campos:
title (título do documento),
summary (resumo do conteúdo),
date (data do documento, se houver),
valor (valor monetário mencionado, se houver)"""
                
                payload = {
                    "model": self.model,
                    "prompt": prompt_text,
                    "stream": False
                }
                
                print(f"  ⏳ Enviando solicitação ao modelo {self.model} para parte {i+1} (timeout: 300s)...")
                response = requests.post(url, json=payload, timeout=300)
                response.raise_for_status()
                
                result = response.json()
                print(f"  ✅ Resposta recebida do modelo {self.model} para parte {i+1}!")
                
                try:
                    ai_response = result.get("response", "{}")
                    # Procura por um bloco JSON válido na resposta
                    json_match = re.search(r'({.*})', ai_response.replace('\n', ' '), re.DOTALL)
                    if json_match:
                        ai_response = json_match.group(1)
                    
                    metadata = json.loads(ai_response)
                    
                    if metadata.get("title"):
                        titles.append(metadata.get("title"))
                    if metadata.get("summary"):
                        summary_parts.append(metadata.get("summary"))
                    if metadata.get("date"):
                        dates.append(metadata.get("date"))
                    if metadata.get("valor"):
                        valores.append(metadata.get("valor"))
                        
                except json.JSONDecodeError:
                    print(f"  ⚠️ Não foi possível analisar a resposta da parte {i+1} como JSON. Usando processamento local.")
                    local_result = self._local_fallback_processing(chunk)
                    if local_result.get("title"):
                        titles.append(local_result.get("title"))
                    if local_result.get("summary"):
                        summary_parts.append(local_result.get("summary"))
                    if local_result.get("date"):
                        dates.append(local_result.get("date"))
                
            except requests.exceptions.Timeout:
                print(f"  ⚠️ Timeout ao processar parte {i+1} com {self.model}. Usando processamento local.")
                local_result = self._local_fallback_processing(chunk)
                if local_result.get("title"):
                    titles.append(local_result.get("title"))
                if local_result.get("summary"):
                    summary_parts.append(local_result.get("summary"))
                if local_result.get("date"):
                    dates.append(local_result.get("date"))
                    
            except requests.exceptions.RequestException as e:
                print(f"  ⚠️ Erro na API ao processar parte {i+1} com {self.model}: {e}. Usando processamento local.")
                local_result = self._local_fallback_processing(chunk)
                if local_result.get("title"):
                    titles.append(local_result.get("title"))
                if local_result.get("summary"):
                    summary_parts.append(local_result.get("summary"))
                if local_result.get("date"):
                    dates.append(local_result.get("date"))
        
        # Consolidar os resultados
        best_title = self._select_best_title(titles) if titles else "Documento sem título"
        combined_summary = " ".join(summary_parts) if summary_parts else "Resumo não disponível"
        best_date = self._select_best_date(dates) if dates else None
        
        print(f"  ✅ Processamento concluído de todas as {len(chunks)} partes do documento")
        
        return {
            "title": best_title,
            "summary": combined_summary,
            "date": best_date,
            "valores": valores if valores else None
        }
    
    def _split_text_into_chunks(self, text):
        """Divide o texto em chunks menores para processamento."""
        # Se o texto for pequeno o suficiente, retorne-o como está
        if len(text) <= self.chunk_size:
            return [text]
        
        # Dividir por parágrafos para manter a coerência
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # Se adicionar este parágrafo exceder o tamanho do chunk, inicie um novo
            if len(current_chunk) + len(paragraph) > self.chunk_size:
                if current_chunk:  # Não adicione chunks vazios
                    chunks.append(current_chunk)
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Adicione o último chunk se não estiver vazio
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    def _local_fallback_processing(self, text):
        """Processamento local simples baseado em regras quando a IA falha."""
        # Extrair título (primeiras linhas não vazias)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        title = lines[0] if lines else "Documento"
        
        # Resumo (primeiros 200 caracteres)
        summary = text[:200] + "..." if len(text) > 200 else text
        
        # Tentar extrair data com regex
        date_patterns = [
            r'\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b',  # DD/MM/YYYY
            r'\b(\d{2,4})[/.-](\d{1,2})[/.-](\d{1,2})\b',   # YYYY/MM/DD
            r'\b(\d{1,2})\s+de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b'  # DD de Mês de YYYY
        ]
        
        date = None
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if isinstance(matches[0], tuple):
                    date = "/".join(matches[0])
                else:
                    date = matches[0]
                break
                
        # Extrair valores monetários
        value_pattern = r'R\$\s*[\d\.,]+|\d+[\.,]\d+\s*reais|\d+[\.,]\d+\s*mil reais|\d+[\.,]\d+\s*milhões'
        values = re.findall(value_pattern, text, re.IGNORECASE)
        
        return {
            "title": title, 
            "summary": summary, 
            "date": date,
            "valores": values if values else None
        }
    
    def _select_best_title(self, titles):
        """Seleciona o melhor título das partes processadas."""
        if not titles:
            return "Documento sem título"
        
        # Estratégia: selecionar o título mais longo e informativo
        # Exclui títulos que são simplesmente comandos do prompt
        filtered_titles = [t for t in titles if not t.startswith("Extraia as seguintes")]
        if not filtered_titles:
            return titles[0]
            
        # Ordenar por comprimento, excluindo aqueles muito curtos
        substantial_titles = [t for t in filtered_titles if len(t) > 5]
        if substantial_titles:
            return sorted(substantial_titles, key=lambda x: len(x), reverse=True)[0]
        else:
            return filtered_titles[0]
    
    def _select_best_date(self, dates):
        """Seleciona a data mais provável das partes processadas."""
        if not dates:
            return None
        
        # Estratégia: retornar a data que aparece com mais frequência
        date_count = {}
        for date in dates:
            if date:  # Ignora None ou string vazia
                date_count[date] = date_count.get(date, 0) + 1
        
        if not date_count:
            return None
            
        # Ordenar por frequência e retornar a mais comum
        sorted_dates = sorted(date_count.items(), key=lambda x: x[1], reverse=True)
        return sorted_dates[0][0]