"""Dictionnaire de synonymes métier (domaine pétrolier/facturation)."""
from typing import Dict, List, Set

SYNONYM_GROUPS: List[Set[str]] = [
    # Facturation
    {"facture", "invoice", "bill", "fac", "fact"},
    {"devis", "quotation", "quote", "offre", "estimation", "proforma"},
    {"bon de commande", "purchase order", "po", "commande", "order"},
    {"avoir", "credit note", "note de credit", "remboursement"},
    {"acompte", "avance", "deposit", "advance"},
    {"remise", "discount", "reduction", "rabais"},

    # Montants
    {"prix unitaire", "unit price", "pu", "tarif", "rate", "cout unitaire"},
    {"montant", "amount", "valeur", "value", "somme"},
    {"total ht", "subtotal", "sous total", "montant ht", "ht"},
    {"total ttc", "grand total", "net a payer", "ttc"},
    {"tva", "vat", "taxe", "tax", "montant tva"},
    {"budget", "previsionnel", "dotation", "budget"},

    # Quantités
    {"quantite", "quantity", "qte", "qty", "nombre", "nb"},
    {"stock", "inventory", "inventaire", "balance"},
    {"stock debut", "stock initial", "opening stock", "beginning inventory", "debut de stock"},
    {"stock fin", "stock final", "closing stock", "ending inventory", "fin de stock"},
    {"barrel", "bbl", "barils"},
    {"litre", "liter", "l", "lt"},
    {"kilogramme", "kg", "kilo", "kilogram"},
    {"metre", "meter", "m"},

    # Pétrole - Puits
    {"puits", "well", "wells"},
    {"forage", "drilling", "drill", "sondage"},
    {"stimulation", "acidification", "acid job"},
    {"completion", "completion puits"},
    {"workover", "recompletion", "w/o"},
    {"production", "prod"},

    # Pétrole - Surface
    {"pipeline", "conduite", "tuyauterie", "pipe", "flowline"},
    {"valve", "vanne", "soupape", "esdv"},
    {"compresseur", "compressor"},
    {"separateur", "separator"},
    {"pompe", "pump"},
    {"reservoir", "tank", "cuve", "storage"},
    {"flare", "torche", "brulee"},
    {"cpf", "central processing facility", "usine centrale"},

    # Maintenance
    {"maintenance", "entretien", "revision", "maint"},
    {"reparation", "repair", "fix", "depannage"},
    {"installation", "install", "mise en place", "setup", "montage"},
    {"inspection", "controle", "control", "check", "verification"},
    {"overhaul", "revision generale", "grand entretien", "turnaround", "ta"},
    {"soudure", "welding", "soudage"},
    {"peinture", "painting", "paint", "coating"},
    {"nettoyage", "cleaning", "clean", "lavage"},

    # Construction
    {"construction", "building", "batiment"},
    {"renovation", "rehabilitation"},
    {"camp", "base vie", "accommodation", "logement"},
    {"upgrade", "amelioration", "mise a niveau", "modernisation"},

    # Sécurité
    {"securite", "safety", "hse", "health safety environment"},
    {"incendie", "fire", "fire fighting", "lutte incendie"},
    {"protection", "protection", "parafoudre", "lightning"},

    # IT
    {"logiciel", "software", "programme", "application"},
    {"telemetrie", "telemetry", "pi", "supervision"},
    {"dcs", "distributed control system", "systeme de controle"},
    {"reseau", "network", "net"},
]

_SYNONYM_INDEX: Dict[str, Set[str]] = {}
for _group in SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYM_INDEX[_word] = _group


def get_synonyms(word: str) -> Set[str]:
    return _SYNONYM_INDEX.get(word.lower(), set()) - {word.lower()}


def expand_synonyms(text: str, max_variants: int = 12) -> List[str]:
    tokens = text.split()
    variants: Set[str] = {text}
    for i, token in enumerate(tokens):
        if token in _SYNONYM_INDEX:
            for syn in _SYNONYM_INDEX[token]:
                if len(variants) >= max_variants:
                    break
                new_tokens = tokens[:i] + [syn] + tokens[i + 1:]
                variants.add(" ".join(new_tokens))
    for i in range(len(tokens) - 1):
        phrase = f"{tokens[i]} {tokens[i+1]}"
        if phrase in _SYNONYM_INDEX and len(variants) < max_variants:
            for syn in _SYNONYM_INDEX[phrase]:
                variants.add(" ".join(tokens[:i] + syn.split() + tokens[i + 2:]))
    return list(variants)