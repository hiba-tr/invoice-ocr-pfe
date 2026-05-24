from typing import Dict, Any

def generate_resume_text(facture_data: Dict[str, Any]) -> str:
    """
    Génère un résumé en langage naturel à partir des données structurées.
    """
    numero = facture_data.get("id_facture")
    fournisseur = facture_data.get("fournisseur") or facture_data.get("concession")
    client = facture_data.get("client")
    date_emission = facture_data.get("date_facture")
    objet = facture_data.get("objet")
    items = facture_data.get("items", [])
    devise = facture_data.get("devise", "USD")
    
    # Calcul des montants (similaire à avant)
    total_ht = 0.0
    tva_montant = 0.0
    for item in items:
        for col, val in item.get("valeurs", {}).items():
            if not isinstance(val, (int, float)):
                continue
            col_lower = col.lower()
            if "ht" in col_lower or "h.t" in col_lower:
                total_ht += val
            elif "tva" in col_lower:
                tva_montant += val
            elif "ttc" in col_lower or "total" in col_lower:
                total_ht += val
            else:
                total_ht += val
    total_ttc = total_ht + tva_montant
    
    # Construction du texte
    lines = []
    
    # 1. Informations générales
    info_parts = []
    if numero:
        info_parts.append(f"Facture n°{numero}")
    if fournisseur:
        info_parts.append(f"émise par {fournisseur}")
    if client:
        info_parts.append(f"à destination de {client}")
    if date_emission:
        info_parts.append(f"en date du {date_emission}")
    if info_parts:
        lines.append(" ".join(info_parts) + ".")
    
    # 2. Objet
    if objet:
        lines.append(f"Objet : {objet}.")
    
    # 3. Détails des opérations
    if items:
        nb_articles = len(items)
        # Catégories = descriptions uniques
        categories = list({item.get("description", "") for item in items if item.get("description")})
        categories_str = ", ".join(categories[:5])  # max 5
        lines.append(f"Cette facture comporte {nb_articles} article(s) concernant : {categories_str}.")
    
    # 4. Montants
    montant_parts = []
    if total_ht > 0:
        montant_parts.append(f"montant total HT de {total_ht:,.2f} {devise}")
    if tva_montant > 0:
        tva_taux = (tva_montant / total_ht * 100) if total_ht > 0 else 0
        montant_parts.append(f"TVA de {tva_montant:,.2f} {devise} (taux {tva_taux:.1f}%)")
    if total_ttc > 0:
        montant_parts.append(f"soit un total TTC de {total_ttc:,.2f} {devise}")
    if montant_parts:
        lines.append("Montants : " + ", ".join(montant_parts) + ".")
    
    # 5. Conclusion synthétique
    if items:
        types_ops = list({item.get("description", "") for item in items if item.get("description")})
        if types_ops:
            first_type = types_ops[0]
            lines.append(f"Cette facture regroupe principalement des opérations de type « {first_type} ».")
    
    return "\n".join(lines)


# resume.py - Ajouter les détails des items
def generate_resume(facture_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retourne un dictionnaire compatible avec ResumeOut, incluant le texte formaté.
    """
    items = facture_data.get("items", [])
    devise = facture_data.get("devise", "USD")

    total_ht = 0.0
    tva_montant = 0.0

    # 🔥 CORRECTION : Stocker les détails des items
    details_items = []
    
    for item in items:
        description = item.get("description", "")
        valeurs = item.get("valeurs", {})
        
        # Ajouter aux détails
        details_items.append({
            "description": description,
            "valeurs": valeurs
        })
        
        for col, val in valeurs.items():
            if not isinstance(val, (int, float)):
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    continue
            col_lower = col.lower()
            if "ht" in col_lower or "h.t" in col_lower:
                total_ht += val
            elif "tva" in col_lower:
                tva_montant += val
            elif "ttc" in col_lower or "total" in col_lower:
                total_ht += val
            else:
                total_ht += val

    total_ttc = total_ht + tva_montant
    tva_taux = (tva_montant / total_ht * 100) if total_ht != 0 else 0.0

    categories = list({item.get("description", "") for item in items if item.get("description")})
    exemples = [item.get("description") for item in items[:3] if item.get("description")]

    resume_text = generate_resume_text(facture_data)

    return {
        "resume": {
            "numero": facture_data.get("id_facture"),
            "date_emission": facture_data.get("date_facture"),
            "fournisseur": facture_data.get("fournisseur") or facture_data.get("concession", "Non spécifié"),
            "client": facture_data.get("client", "Non spécifié"),
            "objet": facture_data.get("objet", "Facture de prestations"),
            "nb_articles": len(items),
            "categories_principales": categories[:5],
            "exemples_articles": exemples,
            "total_ht": round(total_ht, 2),
            "tva_taux": round(tva_taux, 2),
            "tva_montant": round(tva_montant, 2),
            "total_ttc": round(total_ttc, 2),
            "devise": devise,
            "date_insertion": facture_data.get("date_insertion"),
            "resume_texte": resume_text,
            "details_items": details_items  # 🔥 AJOUT : détails des items
        }
    }