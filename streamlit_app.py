import streamlit as st
import requests
import pandas as pd
import math
import json
from datetime import datetime

API_URL = "http://localhost:8000"

# --- Fonctions utilitaires ---
def safe_float(val):
    if val is None:
        return None
    try:
        if isinstance(val, str):
            s = val.strip().replace(' ', '').replace(',', '')
            if s.startswith('(') and s.endswith(')'):
                s = '-' + s[1:-1]
            f = float(s)
        else:
            f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None

def clean_payload(obj):
    """Nettoie récursivement les NaN et inf d'un objet JSON."""
    if isinstance(obj, dict):
        return {k: clean_payload(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_payload(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    else:
        return obj

# --- Configuration de la page ---
st.set_page_config(page_title="DocCore", layout="wide", initial_sidebar_state="expanded")

if "menu_index" not in st.session_state:
    st.session_state.menu_index = 0

# --- CSS MODERNE ---
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
    * { font-family: 'Inter', system-ui, sans-serif; }
    section[data-testid="stSidebar"] { background: var(--card); border-right: 1px solid var(--border); }
    .stButton > button { border-radius: 50px !important; font-weight: 600 !important; padding: 12px 28px !important; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important; box-shadow: 0 2px 6px rgba(79, 70, 229, 0.2) !important; }
    .stButton > button[kind="primary"] { background: linear-gradient(135deg, var(--primary), #6366f1) !important; color: white !important; border: none !important; }
    .stButton > button[kind="primary"]:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(79, 70, 229, 0.35) !important; }
    .stButton > button[kind="secondary"] { background: white !important; border: 1.5px solid var(--border) !important; color: var(--text) !important; }
    .upload-zone { border: 2.5px dashed #cbd5e1; border-radius: 24px; padding: 52px 32px; text-align: center; background: var(--card); transition: all 0.3s; margin-bottom: 24px; cursor: pointer; }
    .upload-zone:hover { border-color: var(--primary); background: #f8faff; transform: translateY(-4px); }
    .upload-icon { font-size: 56px; color: var(--primary); margin-bottom: 16px; }
    .stDataEditor, .stDataFrame { border-radius: 20px !important; border: 1px solid var(--border) !important; }
    .stApp { background: var(--bg); }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; padding: 8px 0 24px 0; border-bottom: 1px solid #e2e8f0;">
        <div style="width: 42px; height: 42px; background: linear-gradient(135deg, #4f46e5, #6366f1); 
                    border-radius: 12px; display: flex; align-items: center; justify-content: center; 
                    color: white; font-weight: 700; font-size: 22px; box-shadow: 0 4px 10px rgba(79,70,229,0.3);">D</div>
        <div>
            <h2 style="margin:0; font-size: 23px; font-weight: 700; color: #1e293b;">DocCore</h2>
            <p style="margin:0; color:#64748b; font-size:13.5px;">Invoice Intelligence</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("")
    nav_options = [("Déposer une facture", "fas fa-file-upload", 0), ("Historique", "fas fa-history", 1), ("Base de données", "fas fa-database", 2)]
    for label, icon, index in nav_options:
        is_selected = st.session_state.menu_index == index
        if st.button(f"   {label}", key=f"nav_{index}", use_container_width=True, type="primary" if is_selected else "secondary"):
            st.session_state.menu_index = index
            st.rerun()

current_menu = st.session_state.menu_index
menu_titles = {0: "Déposer une facture", 1: "Historique des factures", 2: "Base de données"}
st.title(menu_titles[current_menu])
st.markdown("---")

# =============================================================================
# 1. DÉPOSER UNE FACTURE
# =============================================================================
if current_menu == 0:
    st.markdown("""
    <div class="upload-zone" id="customUploadZone">
        <div class="upload-icon"><i class="fas fa-file-invoice"></i></div>
        <div class="upload-title">Glissez votre facture ici ou cliquez</div>
        <div class="upload-badge"><span>pdf </span><span>png </span><span>jpg</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(" ", type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed")
    
    if uploaded_file:
        if st.button("Lancer l'extraction", use_container_width=True, type="primary"):
            with st.spinner("Extraction en cours..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    response = requests.post(f"{API_URL}/upload", files=files)
                    if response.status_code == 200:
                        # FIX 1: Réinitialiser edited_df à chaque nouvelle extraction
                        for k in ["extraction", "suggestions", "edited_df"]:
                            st.session_state.pop(k, None)
                        st.session_state["extraction"] = response.json()
                        st.session_state["uploaded_file_name"] = uploaded_file.name
                        st.success("Extraction réussie")
                    else:
                        st.error(f"Erreur API : {response.status_code} — {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Impossible de contacter l'API. Vérifiez que le serveur est lancé sur localhost:8000")

    if "extraction" in st.session_state:
        data = st.session_state["extraction"]
        metadata = data.get("metadata", {})
        items = data.get("items", [])

        st.subheader("Métadonnées")
        col1, col2 = st.columns(2)
        with col1:
            concession = st.text_input("Concession", metadata.get("concession") or "")
            try:
                date_init = pd.to_datetime(metadata.get("date")).date()
            except:
                date_init = datetime.today().date()
            date_facture = st.date_input("Date de la facture", value=date_init)
            client = st.text_input("Client", metadata.get("client") or "")
        with col2:
            devise = st.text_input("Devise", metadata.get("currency") or "TND")
            fournisseur = st.text_input("Fournisseur", metadata.get("company") or "")
            objet = st.text_input("Objet", "")

        if items:
            # FIX 2: Utiliser first_column_name depuis les métadonnées (pas hardcodé)
            first_col_name = metadata.get("first_column_name") or "Description"

            # FIX 3: Conserver l'ordre des colonnes (pas de sorted())
            seen_cols = []
            for it in items:
                for col in it["valeurs"].keys():
                    if col not in seen_cols:
                        seen_cols.append(col)
            all_cols = seen_cols

            df_data = [
                [it["description"]] + [it["valeurs"].get(col) for col in all_cols]
                for it in items
            ]
            df = pd.DataFrame(df_data, columns=[first_col_name] + all_cols)

            # FIX 4: Initialiser edited_df seulement si pas encore fait pour cette extraction
            if "edited_df" not in st.session_state:
                st.session_state["edited_df"] = df

            st.subheader("Items extraits")

            # ── Initialiser l'état de gestion des colonnes ───────────────────
            for k, v in [("col_action", None), ("col_target", None), ("new_col_name", ""), ("rename_col_val", "")]:
                if k not in st.session_state:
                    st.session_state[k] = v

            # ── Sélecteur colonne + actions dans une seule ligne compacte ─────
            value_cols_list = [c for c in st.session_state["edited_df"].columns if c != first_col_name]
            if value_cols_list:
                sel_col, btn_ren, btn_del, btn_add = st.columns([3, 0.6, 0.6, 0.6])
                with sel_col:
                    selected_col = st.selectbox("Colonne à modifier", value_cols_list,
                                                label_visibility="collapsed", key="sel_col")
                with btn_ren:
                    if st.button("✏️", key="btn_ren_col", help="Renommer"):
                        st.session_state["col_action"] = "rename"
                        st.session_state["col_target"] = selected_col
                        st.session_state["rename_col_val"] = selected_col
                with btn_del:
                    if st.button("🗑️", key="btn_del_col", help="Supprimer"):
                        st.session_state["col_action"] = "delete"
                        st.session_state["col_target"] = selected_col
                with btn_add:
                    if st.button("＋", key="btn_add_col", help="Ajouter une colonne"):
                        st.session_state["col_action"] = "add"
            else:
                if st.button("＋", key="btn_add_col_empty", help="Ajouter une colonne"):
                    st.session_state["col_action"] = "add"

            # ── Formulaire inline selon l'action ─────────────────────────────
            action = st.session_state.get("col_action")
            target = st.session_state.get("col_target")

            if action == "rename" and target:
                f1, f2, f3 = st.columns([3, 0.6, 0.6])
                with f1:
                    new_name = st.text_input("Nouveau nom", value=target, key="rename_col_input")
                with f2:
                    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                    if st.button("✓ OK", type="primary", key="confirm_ren"):
                        n = new_name.strip()
                        if n and n not in st.session_state["edited_df"].columns:
                            st.session_state["edited_df"].rename(columns={target: n}, inplace=True)
                        st.session_state["col_action"] = None
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                with f3:
                    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                    if st.button("✕ Annuler", key="cancel_ren"):
                        st.session_state["col_action"] = None
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            elif action == "delete" and target:
                st.warning(f"Supprimer la colonne **{target}** ?")
                f1, f2 = st.columns([0.6, 0.6])
                with f1:
                    if st.button("✓ Confirmer", type="primary", key="confirm_del"):
                        st.session_state["edited_df"].drop(columns=[target], inplace=True)
                        st.session_state["col_action"] = None
                        st.rerun()
                with f2:
                    if st.button("✕ Annuler", key="cancel_del"):
                        st.session_state["col_action"] = None
                        st.rerun()

            elif action == "add":
                f1, f2, f3 = st.columns([3, 0.6, 0.6])
                with f1:
                    new_col_name = st.text_input("Nom de la nouvelle colonne",
                                                  placeholder="ex: Qté, TVA, Référence…", key="new_col_input")
                with f2:
                    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                    if st.button("✓ OK", type="primary", key="confirm_add"):
                        n = new_col_name.strip()
                        if n and n not in st.session_state["edited_df"].columns:
                            st.session_state["edited_df"].insert(len(st.session_state["edited_df"].columns), n, None)
                        st.session_state["col_action"] = None
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                with f3:
                    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                    if st.button("✕ Annuler", key="cancel_add"):
                        st.session_state["col_action"] = None
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            # ── Tableau ───────────────────────────────────────────────────────
            edited_df = st.data_editor(st.session_state["edited_df"], num_rows="dynamic", use_container_width=True)
            st.session_state["edited_df"] = edited_df

            if st.button("Vérifier correspondances", use_container_width=True):
                try:
                    items_resp = requests.get(f"{API_URL}/items")
                    if items_resp.status_code == 200:
                        suggestions = []
                        for idx, row in edited_df.iterrows():
                            desc = str(row.get(first_col_name, "")).strip()
                            if desc:
                                resp = requests.get(f"{API_URL}/suggest", params={"description": desc})
                                if resp.status_code == 200 and resp.json().get("item_id"):
                                    suggestions.append({
                                        "index": idx,
                                        "description": desc,
                                        "suggestion": resp.json()["nom_item"],
                                        "item_id": resp.json()["item_id"],
                                        "confiance": resp.json().get("confiance")
                                    })
                        st.session_state["suggestions"] = suggestions
                        if not suggestions:
                            st.info("🔍 Aucune correspondance trouvée pour les items de cette facture.")
                    else:
                        st.error("Impossible de récupérer les items existants.")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Impossible de contacter l'API.")
                    st.session_state["suggestions"] = []

            # Affichage des suggestions
            if st.session_state.get("suggestions"):
                st.subheader("Correspondances trouvées")
                for i, s in enumerate(st.session_state["suggestions"]):
                    pct = f"{s['confiance']*100:.1f}%" if s.get("confiance") else "?"
                    col_a, col_b = st.columns([5, 1])
                    with col_a:
                        st.info(f"**{s['description']}** → **{s['suggestion']}** (confiance {pct})")
                    with col_b:
                        if st.button("Utiliser", key=f"use_{i}_{s['item_id']}"):
                            df_mod = st.session_state["edited_df"]
                            df_mod.at[s['index'], first_col_name] = s['suggestion']
                            st.session_state["edited_df"] = df_mod
                            st.session_state["suggestions"].pop(i)
                            st.success(f"Description mise à jour : '{s['suggestion']}'")
                            st.rerun()

            force_overwrite = st.checkbox("Écraser si la facture existe déjà")

            if st.button("Enregistrer en base", use_container_width=True, type="primary"):
                items_to_save = []
                value_cols = [c for c in edited_df.columns if c != first_col_name]
                for _, row in edited_df.iterrows():
                    desc = str(row.get(first_col_name, "")).strip()
                    if desc:
                        valeurs = {col: (safe_float(row.get(col)) or 0.0) for col in value_cols}
                        items_to_save.append({"description": desc, "valeurs": valeurs})
                
                payload = clean_payload({
                    "facture": {
                        "nom_fichier": st.session_state.get("uploaded_file_name", ""),
                        "date_facture": date_facture.strftime("%Y-%m-%d"),
                        "concession": fournisseur if fournisseur else concession,
                        "devise": devise,
                        "client": client,
                        "objet": objet
                    },
                    "items_data": items_to_save,
                })
                
                try:
                    resp = requests.post(f"{API_URL}/facture", json=payload, params={"force": force_overwrite})
                    if resp.status_code == 200:
                        st.success("✅ Facture enregistrée !")
                        for k in ["extraction", "suggestions", "uploaded_file_name", "edited_df"]:
                            st.session_state.pop(k, None)
                        st.rerun()
                    else:
                        st.error(f"Erreur lors de l'enregistrement : {resp.status_code} — {resp.text}")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Impossible de contacter l'API.")

# =============================================================================
# 2. HISTORIQUE
# =============================================================================
elif current_menu == 1:
    st.subheader("Historique des factures")
    try:
        resp = requests.get(f"{API_URL}/factures")
        if resp.status_code == 200:
            factures = resp.json()
            if not factures:
                st.info("Aucune facture enregistrée.")
            for f in factures:
                with st.expander(f"Facture #{f['id_facture']} - {f.get('concession', '—')} ({f.get('date_facture', '—')})"):
                    res_det = requests.get(f"{API_URL}/facture/{f['id_facture']}/details")
                    if res_det.status_code == 200:
                        data_json = res_det.json().get("details", [])
                        if data_json:
                            df_hist = pd.DataFrame(data_json)
                            pivot_df = df_hist.pivot(index='item', columns='colonne', values='valeur')
                            df_display = pivot_df.fillna("∅").astype(str)
                            st.write("**Récapitulatif des lignes :**")
                            st.dataframe(df_display, use_container_width=True)
                    
                    btn1, btn2 = st.columns(2)
                    with btn1:
                        if st.button("Résumé AI", key=f"res_{f['id_facture']}"):
                            res_resp = requests.post(f"{API_URL}/facture/{f['id_facture']}/resume")
                            if res_resp.status_code == 200:
                                st.info(res_resp.json().get("resume", {}).get("resume_texte", "Aucun résumé"))
                    with btn2:
                        if st.button("Supprimer", key=f"del_{f['id_facture']}"):
                            requests.delete(f"{API_URL}/facture/{f['id_facture']}")
                            st.rerun()
        else:
            st.error("Impossible de récupérer l'historique.")
    except requests.exceptions.ConnectionError:
        st.error("❌ Impossible de contacter l'API.")

# =============================================================================
# 3. BASE DE DONNÉES
# =============================================================================
elif current_menu == 2:
    st.subheader("Contenu des tables")
    tab_labels = ["Items", "Colonnes", "Factures", "Valeurs"]
    tabs = st.tabs(tab_labels)
    
    with tabs[0]:
        try:
            r = requests.get(f"{API_URL}/items")
            if r.status_code == 200:
                items = r.json()
                if items:
                    st.write("Sélectionnez les items à supprimer :")
                    selected_items = {}
                    for item in items:
                        selected_items[item['id_item']] = st.checkbox(f"{item['nom_item']}", key=f"chk_{item['id_item']}")
                    if st.button("🗑️ Supprimer les items sélectionnés", type="secondary"):
                        to_delete = [item_id for item_id, checked in selected_items.items() if checked]
                        if not to_delete:
                            st.warning("Aucun item sélectionné.")
                        else:
                            success_count = 0
                            for item_id in to_delete:
                                del_resp = requests.delete(f"{API_URL}/item/{item_id}")
                                if del_resp.status_code == 200:
                                    success_count += 1
                                else:
                                    st.error(f"Erreur suppression item {item_id}")
                            if success_count > 0:
                                st.success(f"{success_count} item(s) supprimé(s).")
                                st.rerun()
                else:
                    st.info("Aucun item en base.")
            else:
                st.error("Erreur de chargement des items")
        except requests.exceptions.ConnectionError:
            st.error("❌ Impossible de contacter l'API.")
    
    with tabs[1]:
        try:
            r = requests.get(f"{API_URL}/colonnes")
            if r.status_code == 200:
                cols = r.json()
                st.dataframe(pd.DataFrame(cols).fillna("∅"), use_container_width=True) if cols else st.info("Aucune colonne en base.")
            else:
                st.error("Erreur de chargement des colonnes")
        except requests.exceptions.ConnectionError:
            st.error("❌ Impossible de contacter l'API.")
    
    with tabs[2]:
        try:
            r = requests.get(f"{API_URL}/factures")
            if r.status_code == 200:
                facts = r.json()
                st.dataframe(pd.DataFrame(facts).fillna("∅"), use_container_width=True) if facts else st.info("Aucune facture en base.")
            else:
                st.error("Erreur de chargement des factures")
        except requests.exceptions.ConnectionError:
            st.error("❌ Impossible de contacter l'API.")
    
    with tabs[3]:
        try:
            r = requests.get(f"{API_URL}/fact_data")
            if r.status_code == 200:
                data = r.json()
                st.dataframe(pd.DataFrame(data).fillna("∅"), use_container_width=True) if data else st.info("Aucune donnée dans fact_data.")
            else:
                st.error("Erreur de chargement des valeurs")
        except requests.exceptions.ConnectionError:
            st.error("❌ Impossible de contacter l'API.")