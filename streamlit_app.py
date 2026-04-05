import streamlit as st
import requests
import pandas as pd
import math

API_URL = "http://localhost:8000"

def clean_amount(val):
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().replace(' ', '').replace(',', '')
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        try:
            f = float(s)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except ValueError:
            return None
    if isinstance(val, (int, float)):
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    return None

st.set_page_config(page_title="DocCore", layout="wide", initial_sidebar_state="expanded")
# Initialisation de la session pour le menu
if "menu_index" not in st.session_state:
    st.session_state.menu_index = 0

# CSS moderne et épuré
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    :root {
        --primary: #4f46e5;
        --primary-hover: #4338ca;
        --bg: #f8fafc;
        --card: #ffffff;
        --border: #e2e8f0;
        --text: #1e293b;
        --text-light: #64748b;
    }

    * {
        font-family: 'Inter', system-ui, sans-serif;
    }

    section[data-testid="stSidebar"] {
        background: var(--card);
        border-right: 1px solid var(--border);
    }

    .stButton > button {
        border-radius: 50px !important;
        font-weight: 600 !important;
        padding: 12px 28px !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 2px 6px rgba(79, 70, 229, 0.2) !important;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--primary), #6366f1) !important;
        color: white !important;
        border: none !important;
    }

    .stButton > button[kind="primary"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.35) !important;
    }

    .stButton > button[kind="secondary"] {
        background: white !important;
        border: 1.5px solid var(--border) !important;
        color: var(--text) !important;
    }

    .stButton > button[kind="secondary"]:hover {
        border-color: var(--primary);
        color: var(--primary);
        background: #f8faff !important;
    }

    .upload-zone {
        border: 2.5px dashed #cbd5e1;
        border-radius: 24px;
        padding: 52px 32px;
        text-align: center;
        background: var(--card);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        margin-bottom: 24px;
    }

    .upload-zone:hover {
        border-color: var(--primary);
        background: #f8faff;
        transform: translateY(-4px);
    }

    .upload-icon {
        font-size: 56px;
        color: var(--primary);
        margin-bottom: 16px;
        transition: transform 0.3s ease;
    }

    .upload-zone:hover .upload-icon {
        transform: scale(1.1);
    }

    .upload-title {
        font-size: 18px;
        font-weight: 600;
        color: var(--text);
        margin-bottom: 6px;
    }

    .upload-sub {
        font-size: 14px;
        color: var(--text-light);
    }

    .upload-badge span {
        background: #f1f5f9;
        padding: 5px 12px;
        border-radius: 30px;
        font-size: 12px;
        font-weight: 600;
        color: #475569;
    }

    .stDataEditor, .stDataFrame {
        border-radius: 20px !important;
        border: 1px solid var(--border) !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04) !important;
    }

    div[data-testid="metric-container"] {
        background: var(--card);
        border-radius: 20px;
        border: 1px solid var(--border);
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03);
    }

    details {
        border-radius: 20px !important;
        border: 1px solid var(--border) !important;
        background: var(--card) !important;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
    }

    .stApp {
        background: var(--bg);
    }

    h1, h2, h3 {
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .stTextInput > div > div > input,
    .stSelectbox > div > div > div {
        border-radius: 12px !important;
        border: 1.5px solid var(--border) !important;
    }

    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > div:focus-within {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1) !important;
    }
</style>
""", unsafe_allow_html=True)

# ====================== SIDEBAR MODERNE ======================
with st.sidebar:
    st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px; padding: 8px 0 24px 0; border-bottom: 1px solid #e2e8f0;">
            <div style="width: 42px; height: 42px; background: linear-gradient(135deg, #4f46e5, #6366f1); 
                        border-radius: 12px; display: flex; align-items: center; justify-content: center; 
                        color: white; font-weight: 700; font-size: 22px; box-shadow: 0 4px 10px rgba(79,70,229,0.3);">
                D
            </div>
            <div>
                <h2 style="margin:0; font-size: 23px; font-weight: 700; color: #1e293b;">DocCore</h2>
                <p style="margin:0; color:#64748b; font-size:13.5px;">Invoice Intelligence</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("")

    nav_options = [
        ("Déposer une facture", "fas fa-file-upload", 0),
        ("Historique", "fas fa-history", 1),
        ("Base de données", "fas fa-database", 2),
    ]

    for label, icon, index in nav_options:
        is_selected = st.session_state.menu_index == index
        if st.button(
            f"   {label}",
            key=f"nav_{index}",
            use_container_width=True,
            type="primary" if is_selected else "secondary"
        ):
            st.session_state.menu_index = index
            st.rerun()

    st.markdown("---")

# ====================== TITRE PRINCIPAL ======================
current_menu = st.session_state.menu_index
menu_titles = {
    0: "Déposer une facture",
    1: "Historique des factures",
    2: "Base de données"
}
st.title(menu_titles[current_menu])
st.caption("Extraction, correspondance sémantique et gestion centralisée")
st.markdown("---")

# =============================================================================
# 1. DÉPOSER UNE FACTURE
# =============================================================================
if current_menu == 0:
    # Zone de dépôt stylisée
    st.markdown("""
    <div class="upload-zone">
        <div class="upload-icon"><i class="fas fa-file-invoice"></i></div>
        <div class="upload-title">Glissez votre facture ici</div>
        <div class="upload-sub">ou cliquez pour parcourir</div>
        <div class="upload-badge">
            <span>PDF</span>
            <span>PNG</span>
            <span>JPG</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        " ",
        type=["pdf", "png", "jpg", "jpeg"],
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        st.markdown(f"""
        <div style="background:#eef2ff; border-radius:12px; padding:12px 16px; margin-bottom:16px;">
            <i class="fas fa-check-circle" style="color:#4f46e5;"></i> <strong>{uploaded_file.name}</strong> ({round(len(uploaded_file.getvalue())/1024, 1)} KB)
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("Lancer l'extraction", use_container_width=True, type="primary"):
            with st.spinner("Extraction en cours..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                response = requests.post(f"{API_URL}/upload", files=files)
                if response.status_code == 200:
                    st.session_state["extraction"] = response.json()
                    st.session_state["uploaded_file_name"] = uploaded_file.name
                    st.session_state.pop("suggestions", None)
                    st.session_state.pop("edited_df", None)
                    st.success("Extraction réussie")
                else:
                    st.error(f"Erreur {response.status_code}: {response.text}")

    if "extraction" in st.session_state:
        data = st.session_state["extraction"]
        metadata = data.get("metadata", {})
        items = data.get("items", [])

        st.subheader("Métadonnées")
        col1, col2, col3 = st.columns(3)
        with col1:
            concession = st.text_input("Concession", metadata.get("concession") or "")
            date_facture = st.text_input("Date (YYYY-MM-DD)", metadata.get("date") or "")
        with col2:
            devise = st.text_input("Devise", metadata.get("currency") or "TND")
        with col3:
            st.metric("Société", metadata.get("company") or "—")

        if items:
            all_cols = sorted({col for it in items for col in it["valeurs"].keys()})
            df_data = [[it["description"]] + [it["valeurs"].get(col) for col in all_cols] for it in items]
            df = pd.DataFrame(df_data, columns=["description"] + all_cols)

            if "edited_df" not in st.session_state:
                st.session_state["edited_df"] = df

            st.subheader("Items extraits (modifiables)")
            edited_df = st.data_editor(
                st.session_state["edited_df"],
                num_rows="dynamic",
                use_container_width=True,
                key="data_editor"
            )
            st.session_state["edited_df"] = edited_df

            if st.button("Vérifier correspondances", use_container_width=True):
                suggestions = []
                for idx, row in edited_df.iterrows():
                    desc = str(row.get("description", "")).strip()
                    if not desc:
                        continue
                    try:
                        resp = requests.get(f"{API_URL}/suggest", params={"description": desc}, timeout=10)
                        if resp.status_code == 200:
                            sugg = resp.json()
                            if sugg.get("item_id"):
                                suggestions.append({
                                    "index": idx,
                                    "description": desc,
                                    "suggestion": sugg["nom_item"],
                                    "item_id": sugg["item_id"],
                                    "confiance": sugg.get("confiance")
                                })
                    except Exception as e:
                        st.warning(f"Erreur pour '{desc}': {e}")
                st.session_state["suggestions"] = suggestions
                if not suggestions:
                    st.info("Aucune correspondance trouvée.")

            if st.session_state.get("suggestions"):
                st.subheader("Correspondances trouvées")
                for i, s in enumerate(st.session_state["suggestions"].copy()):
                    pct = f"{s['confiance']*100:.1f}%" if s["confiance"] else "?"
                    col_a, col_b = st.columns([5, 1])
                    with col_a:
                        st.info(f"**{s['description']}** → **{s['suggestion']}** (confiance {pct})")
                    with col_b:
                        if st.button("Utiliser", key=f"use_{i}_{s['item_id']}"):
                            df_mod = st.session_state["edited_df"]
                            df_mod.at[s['index'], "description"] = s['suggestion']
                            st.session_state["edited_df"] = df_mod
                            st.session_state["suggestions"].pop(i)
                            st.success(f"Description mise à jour : '{s['suggestion']}'")
                            st.rerun()

            st.markdown("---")
            force_overwrite = st.checkbox("Écraser si la facture existe déjà")

            if st.button("Enregistrer en base", use_container_width=True, type="primary"):
                items_to_save = []
                for _, row in st.session_state["edited_df"].iterrows():
                    desc = str(row.get("description", "")).strip()
                    if not desc:
                        continue
                    valeurs = {}
                    for col in all_cols:
                        val = clean_amount(row.get(col))
                        if val is not None:
                            valeurs[col] = val
                    if valeurs:
                        items_to_save.append({"description": desc, "valeurs": valeurs})
                payload = {
                    "facture": {
                        "nom_fichier": st.session_state["uploaded_file_name"],
                        "date_facture": date_facture if date_facture else None,
                        "concession": concession,
                        "devise": devise,
                    },
                    "items_data": items_to_save,
                }
                try:
                    resp = requests.post(f"{API_URL}/facture", json=payload, params={"force": force_overwrite})
                    if resp.status_code == 200:
                        fid = resp.json()["id_facture"]
                        st.success(f"✅ Facture enregistrée avec succès (ID {fid})")
                        for k in ["extraction", "suggestions", "uploaded_file_name", "edited_df"]:
                            st.session_state.pop(k, None)
                        st.rerun()
                    elif resp.status_code == 409:
                        st.warning("⚠️ Cette facture existe déjà. Cochez 'Écraser' pour la remplacer.")
                    else:
                        st.error(f"Erreur {resp.status_code}: {resp.text}")
                except Exception as e:
                    st.error(f"Erreur d'envoi : {e}")
        else:
            st.warning("Aucun item détecté dans cette facture.")

# =============================================================================
# 2. HISTORIQUE
# =============================================================================
elif current_menu == 1:
    st.subheader("Factures enregistrées")
    resp = requests.get(f"{API_URL}/factures")
    if resp.status_code != 200:
        st.error("Erreur de chargement des factures")
    else:
        factures = resp.json()
        if not factures:
            st.info("Aucune facture en base.")
        else:
            for f in factures:
                label = f"Facture #{f['id_facture']} — {f.get('date_facture', '—')} — {f.get('concession', '—')}"
                with st.expander(label):
                    col1, col2 = st.columns(2)
                    col1.write(f"**Fichier :** {f.get('nom_fichier', '—')}")
                    col2.write(f"**Devise :** {f.get('devise', '—')}")
                    details = requests.get(f"{API_URL}/facture/{f['id_facture']}")
                    if details.status_code == 200:
                        fact_data = details.json().get("data", [])
                        if fact_data:
                            st.dataframe(pd.DataFrame(fact_data), use_container_width=True)
                        else:
                            st.caption("Aucune donnée associée.")
                    btn1, btn2 = st.columns(2)
                    with btn1:
                        if st.button("Résumé", key=f"resume_{f['id_facture']}"):
                            resume_resp = requests.post(f"{API_URL}/facture/{f['id_facture']}/resume")
                            if resume_resp.status_code == 200:
                                r = resume_resp.json().get("resume", {})
                                st.metric("Total", f"{r.get('total', 0):.2f} {r.get('devise', '')}")
                                st.metric("Items", r.get("nb_items", 0))
                                st.metric("Fournisseur", r.get("fournisseur") or "—")
                            else:
                                st.error("Erreur lors du résumé.")
                    with btn2:
                        if st.button("Supprimer", key=f"del_{f['id_facture']}"):
                            del_resp = requests.delete(f"{API_URL}/facture/{f['id_facture']}")
                            if del_resp.status_code == 200:
                                st.success(f"Facture {f['id_facture']} supprimée")
                                st.rerun()
                            else:
                                st.error("Erreur lors de la suppression")

# =============================================================================
# 3. BASE DE DONNÉES
# =============================================================================
elif current_menu == 2:
    st.subheader("Contenu des tables")
    tabs = st.tabs(["Items", "Colonnes", "Factures", "Valeurs (fact_data)"])
    with tabs[0]:
        r = requests.get(f"{API_URL}/items")
        if r.status_code == 200:
            st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
        else:
            st.error("Erreur de chargement")
    with tabs[1]:
        r = requests.get(f"{API_URL}/colonnes")
        if r.status_code == 200:
            st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
    with tabs[2]:
        r = requests.get(f"{API_URL}/factures")
        if r.status_code == 200:
            st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
    with tabs[3]:
        r = requests.get(f"{API_URL}/fact_data")
        if r.status_code == 200:
            st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
        else:
            st.info("Endpoint /fact_data non disponible")