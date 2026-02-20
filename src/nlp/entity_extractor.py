import spacy
from typing import List, Dict

class EntityExtractor:
    def __init__(self, model="fr_core_news_sm"):
        try:
            self.nlp = spacy.load(model)
        except OSError:
            # Télécharger automatiquement si absent
            spacy.cli.download(model)
            self.nlp = spacy.load(model)

    def extract(self, text: str) -> List[Dict[str, str]]:
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            entities.append({
                'text': ent.text,
                'label': ent.label_,
                'start': ent.start_char,
                'end': ent.end_char
            })
        return entities