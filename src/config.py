# Configuration settings for the PDF Document Analyzer application

import os

class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INPUT_DIR = os.path.join(BASE_DIR, '../data/input')
    OUTPUT_DIR = os.path.join(BASE_DIR, '../data/output')
    
    # AI model settings
    AI_MODEL_PATH = 'path/to/ollama/model'  # Update with the actual model path
    AI_MODEL_PARAMS = {
        'param1': 'value1',  # Example parameter
        'param2': 'value2'   # Example parameter
    }
    
    # Tesseract settings
    TESSERACT_CMD = 'tesseract'  # Command to run Tesseract
    TESSERACT_CONFIG = '--psm 6'  # Example configuration for Tesseract

    @staticmethod
    def get_input_path(filename):
        return os.path.join(Config.INPUT_DIR, filename)

    @staticmethod
    def get_output_path(filename):
        return os.path.join(Config.OUTPUT_DIR, filename)