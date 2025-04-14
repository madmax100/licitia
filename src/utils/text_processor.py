def summarize_text(text):
    # This function generates a brief summary of the provided text.
    # For simplicity, we will return the first few sentences as a summary.
    sentences = text.split('. ')
    summary = '. '.join(sentences[:2]) + '.' if len(sentences) > 1 else text
    return summary.strip()

def clean_text(text):
    # This function cleans the extracted text by removing unnecessary whitespace and formatting.
    return ' '.join(text.split()).strip()