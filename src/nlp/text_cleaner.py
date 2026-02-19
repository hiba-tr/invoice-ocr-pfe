import re

def clean_text(text: str) -> str:
    # Supprimer les caractères non désirés, normaliser les espaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()