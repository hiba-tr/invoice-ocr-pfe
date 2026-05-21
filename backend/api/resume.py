"""
Génération de résumé intelligent pour les factures
"""
from typing import Dict, Any, List
import random


class IntelligentResumeGenerator:
    """
    Générateur de résumé intelligent.
    """
    
    def __init__(self):
        self.templates = {
            "intro": [
                "Voici le détail de la facture {numero}.",
                "La facture {numero} concerne les éléments suivants :",
                "Récapitulatif de la facture {numero} :",
                "Document facturier {numero} - Analyse des prestations :"
            ],
            "supplier": [
                "Émise par {fournisseur}",
                "Fournisseur : {fournisseur}",
                "Provenance : {fournisseur}",
                "Prestataire : {fournisseur}"
            ],
            "concession": [
                "Concession concernée : {concession}",
                "Pour la concession {concession}",
                "Afférente à la concession {concession}",
                "Concession : {concession}"
            ],
            "date": [
                "en date du {date}",
                "datée du {date}",
                "({date})",
                "pour la période du {date}"
            ],
            "items_summary": [
                "Cette facture détaille {count} article(s).",
                "{count} ligne(s) de prestation sont répertoriées.",
                "Soit un total de {count} élément(s) facturé(s).",
                "Le document comptabilise {count} poste(s) de dépense."
            ],
            "categories": [
                "Les principaux postes concernent : {categories}.",
                "On y retrouve notamment : {categories}.",
                "Les dépenses se répartissent sur : {categories}.",
                "Catégories principales : {categories}."
            ],
            "amount": [
                "Montant total : {total} {devise}.",
                "Soit un montant de {total} {devise}.",
                "Total facturé : {total} {devise}.",
                "Pour un montant global de {total} {devise}."
            ],
            "main_category": [
                "La prestation principale est {category}.",
                "Le poste majoritaire concerne {category}.",
                "L'activité dominante est {category}.",
                "La dépense la plus significative est {category}."
            ],
            "closing": [
                "À traiter en comptabilité.",
                "Document à archiver.",
                "Facture à valider.",
                "En attente de règlement."
            ]
        }
    
    def generate(self, facture_data: Dict[str, Any]) -> Dict[str, Any]:
        """Génère un résumé intelligent."""
        items = facture_data.get("items", [])
        devise = facture_data.get("devise", "EUR")
        
        # Récupération correcte des champs
        fournisseur = facture_data.get("fournisseur") or facture_data.get("company") or "Non spécifié"
        concession = facture_data.get("concession") or facture_data.get("concession_nom") or "Non spécifiée"
        
        date_facture = facture_data.get("date_facture", "")
        id_facture = facture_data.get("id_facture", "N/A")
        
        # Analyse des items
        descriptions = [item.get("description", "") for item in items if item.get("description")]
        categories = list(set(descriptions))
        main_category = categories[0] if categories else "Non spécifié"
        
        # Calcul des montants
        total_ht, tva_montant, total_ttc = self._calculate_amounts(items)
        
        # Génération du texte
        text_parts = []
        
        intro = random.choice(self.templates["intro"]).format(numero=str(id_facture))
        text_parts.append(intro)
        
        if fournisseur and fournisseur != "Non spécifié":
            supplier_text = random.choice(self.templates["supplier"]).format(fournisseur=fournisseur)
            text_parts.append(supplier_text)
        
        if concession and concession != "Non spécifiée":
            concession_text = random.choice(self.templates["concession"]).format(concession=concession)
            text_parts.append(concession_text)
        
        if date_facture:
            date_text = random.choice(self.templates["date"]).format(date=date_facture)
            text_parts.append(date_text + ".")
        
        item_summary = random.choice(self.templates["items_summary"]).format(count=len(items))
        text_parts.append(item_summary)
        
        if categories:
            cat_str = ", ".join(categories[:5])
            categories_text = random.choice(self.templates["categories"]).format(categories=cat_str)
            text_parts.append(categories_text)
        
        if total_ttc > 0:
            amount_text = random.choice(self.templates["amount"]).format(total=f"{total_ttc:,.2f}", devise=devise)
            text_parts.append(amount_text)
        elif total_ht > 0:
            amount_text = random.choice(self.templates["amount"]).format(total=f"{total_ht:,.2f}", devise=devise)
            text_parts.append(amount_text)
        
        if main_category and main_category != "Non spécifié":
            main_cat_text = random.choice(self.templates["main_category"]).format(category=main_category)
            text_parts.append(main_cat_text)
        
        closing = random.choice(self.templates["closing"])
        text_parts.append(closing)
        
        resume_text = " ".join(text_parts)
        
        # Retour structuré avec TOUTES les données
        return {
            "resume": {
                "numero": str(id_facture),
                "date_emission": date_facture,
                "fournisseur": fournisseur,
                "concession": concession,
                "nb_articles": len(items),
                "categories_principales": categories[:5],
                "total_ht": round(total_ht, 2),
                "total_ttc": round(total_ttc, 2) if total_ttc > 0 else round(total_ht, 2),
                "tva_montant": round(tva_montant, 2),
                "devise": devise,
                "resume_texte": resume_text,
                "details_items": self._get_items_details(items),
                "stats": self._get_stats(items, total_ttc)
            }
        }
    
    def _calculate_amounts(self, items: List[Dict]) -> tuple:
        """Calcule les montants totaux."""
        total_ht = 0.0
        tva_montant = 0.0
        
        for item in items:
            valeurs = item.get("valeurs", {})
            for col, val in valeurs.items():
                if not isinstance(val, (int, float)):
                    continue
                col_lower = col.lower()
                if "ht" in col_lower or "h.t" in col_lower:
                    total_ht += val
                elif "tva" in col_lower:
                    tva_montant += val
                else:
                    total_ht += val
        
        total_ttc = total_ht + tva_montant
        return total_ht, tva_montant, total_ttc
    
    def _get_items_details(self, items: List[Dict]) -> List[Dict]:
        """Retourne le détail des items."""
        details = []
        for item in items:
            details.append({
                "description": item.get("description", "Sans description"),
                "valeurs": item.get("valeurs", {})
            })
        return details
    
    def _get_stats(self, items: List[Dict], total_ttc: float) -> Dict:
        """Retourne des statistiques."""
        if not items:
            return {"average_per_item": 0, "max_item": 0, "min_item": 0}
        
        values = []
        for item in items:
            for val in item.get("valeurs", {}).values():
                if isinstance(val, (int, float)):
                    values.append(val)
        
        if not values:
            return {"average_per_item": 0, "max_item": 0, "min_item": 0}
        
        return {
            "average_per_item": round(sum(values) / len(values), 2),
            "max_item": max(values),
            "min_item": min(values)
        }


generator = IntelligentResumeGenerator()


def generate_resume(facture_data: Dict[str, Any]) -> Dict[str, Any]:
    return generator.generate(facture_data)


def generate_resume_text(facture_data: Dict[str, Any]) -> str:
    return generator.generate(facture_data)["resume"]["resume_texte"]