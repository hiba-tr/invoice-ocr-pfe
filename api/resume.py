from typing import Dict, Any, List


# Colonnes candidates pour le calcul du total (ordre de priorité)
_TOTAL_COLUMN_PATTERNS = [
    "current month expenditure 100%",
    "current month",
    "montant",
    "total",
    "amount",
    "expenditure",
]


def _find_total_column(col_name: str) -> bool:
    """Retourne True si ce nom de colonne ressemble à une colonne de montant total."""
    col_lower = col_name.lower().strip()
    return any(pattern in col_lower for pattern in _TOTAL_COLUMN_PATTERNS)


def generate_resume(facture_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    facture_data = {
        "id_facture": int,
        "nom_fichier": str,
        "date_facture": str | None,
        "concession": str | None,
        "devise": str | None,
        "items": [{"description": str, "valeurs": {col: float}}]
    }

    Retourne un dict compatible avec le schema ResumeOut.
    """
    items: List[Dict] = facture_data.get("items", [])
    total: float = 0.0
    items_with_total: int = 0

    for item in items:
        valeurs = item.get("valeurs", {})
        # Chercher la colonne de montant par ordre de priorité
        matched = False
        for col, val in valeurs.items():
            if val is not None and _find_total_column(col):
                total += float(val)
                matched = True
                break  # une seule colonne par item
        if not matched and valeurs:
            # Fallback : prendre la première valeur non-nulle disponible
            first_val = next((v for v in valeurs.values() if v is not None), None)
            if first_val is not None:
                # Ne pas l'ajouter au total sauf si c'est le seul champ
                pass
        if valeurs:
            items_with_total += 1

    return {
        "resume": {
            "nom_fichier": facture_data.get("nom_fichier"),
            "numero": facture_data.get("id_facture"),
            "date": facture_data.get("date_facture"),
            "fournisseur": facture_data.get("concession"),
            "devise": facture_data.get("devise", "USD"),
            "total": round(total, 2),
            "nb_items": len(items),
            "modifications": [],  # historique à remplir via audit_log si besoin
        }
    }