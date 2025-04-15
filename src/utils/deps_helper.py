import os
import subprocess

def configure_poppler():
    """Configura o Poppler no PATH do sistema para processar PDFs."""
    # Caminhos comuns onde o Poppler pode estar instalado no Windows
    common_paths = [
        r"C:\Program Files\poppler\bin",
        r"C:\Program Files (x86)\poppler\bin",
        r"C:\poppler\bin",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'poppler', 'bin')
    ]
    
    # Verifica se já está no PATH
    try:
        result = subprocess.run(['pdfinfo', '-v'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE,
                              text=True,
                              timeout=2)
        print("✅ Poppler já configurado!")
        return True
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        # Verifica os caminhos comuns
        for path in common_paths:
            if os.path.exists(path) and os.path.exists(os.path.join(path, 'pdfinfo.exe')):
                # Adiciona o caminho ao PATH
                print(f"✅ Poppler encontrado em: {path}")
                print("✅ Adicionando Poppler ao PATH...")
                os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                return True
        
        print("⚠️ Poppler não encontrado. OCR avançado não estará disponível.")
        print("Por favor, instale o Poppler de https://github.com/oschwartz10612/poppler-windows/releases/")
        return False