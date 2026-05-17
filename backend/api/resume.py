from typing import Dict, Any


def generate_resume_text(facture_data: Dict[str, Any]) -> str:
    numero = facture_data.get("id_facture")
    fournisseur = facture_data.get("fournisseur") or facture_data.get("concession")
    client = facture_data.get("client")
    date_emission = facture_data.get("date_facture")
    objet = facture_data.get("objet")
    items = facture_data.get("items", [])
    devise = facture_data.get("devise", "USD")

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

    lines = []
    info_parts = []
    if numero:
        info_parts.append(f"Facture n{numero}")
    if fournisseur:
        info_parts.append(f"emise par {fournisseur}")
    if client:
        info_parts.append(f"a destination de {client}")
    if date_emission:
        info_parts.append(f"en date du {date_emission}")
    if info_parts:
        lines.append(" ".join(info_parts) + ".")

    if objet:
        lines.append(f"Objet : {objet}.")

    if items:
        nb_articles = len(items)
        categories = list({item.get("description", "") for item in items if item.get("description")})
        categories_str = ", ".join(categories[:5])
        lines.append(f"Cette facture comporte {nb_articles} article(s) concernant : {categories_str}.")

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

    if items:
        types_ops = list({item.get("description", "") for item in items if item.get("description")})
        if types_ops:
            lines.append(f"Cette facture regroupe principalement des operations de type {types_ops[0]}.")

    return "\n".join(lines)


def generate_resume(facture_data: Dict[str, Any]) -> Dict[str, Any]:
    items = facture_data.get("items", [])
    devise = facture_data.get("devise", "USD")
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
            "fournisseur": facture_data.get("fournisseur") or facture_data.get("concession", "Non specifie"),
            "client": facture_data.get("client", "Non specifie"),
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
        }
    }