from flask import Blueprint, request, jsonify, render_template, current_app
from werkzeug.utils import secure_filename
import os
from app.processing import process_invoice
from app.models import get_db
from datetime import datetime

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    try:
        # Traitement
        structured = process_invoice(filepath)

        # Insertion en base
        db = get_db()
        cursor = db.cursor()

        # --- Gestion de la date (optionnelle) ---
        date_str = structured['invoice']['header']['invoice_date']
        date_obj = None
        if date_str is not None:
            # Mapping des mois français vers anglais (si nécessaire)
            mois_fr_en = {
                'janvier': 'January', 'février': 'February', 'mars': 'March', 'avril': 'April',
                'mai': 'May', 'juin': 'June', 'juillet': 'July', 'août': 'August',
                'septembre': 'September', 'octobre': 'October', 'novembre': 'November', 'décembre': 'December'
            }
            # Remplacer les mois français par anglais
            for fr, en in mois_fr_en.items():
                date_str = date_str.replace(fr, en)
            # Parser la date (format attendu : "DD Month YYYY")
            try:
                date_obj = datetime.strptime(date_str, "%d %B %Y")
            except ValueError as e:
                raise ValueError(f"Format de date invalide : '{date_str}'. Attendu : 'DD Month YYYY'") from e

        # 1. Insertion dans INVOICES
        inv_id = cursor.var(int)
        cursor.execute(
            """INSERT INTO INVOICES (SUPPLIER, DOCUMENT_TITLE, INVOICE_DATE, CURRENCY)
               VALUES (:1, :2, :3, :4)
               RETURNING INVOICE_ID INTO :5""",
            (structured['invoice']['header']['supplier'],
             structured['invoice']['header']['document_title'],
             date_obj,  # ← peut être None
             structured['invoice']['header']['currency'],
             inv_id)
        )
        invoice_id = inv_id.getvalue()[0]

        # 2. Insertion des colonnes
        columns = structured['invoice']['columns']
        for idx, col_name in enumerate(columns, start=1):
            cursor.execute(
                "INSERT INTO INVOICE_COLUMNS (INVOICE_ID, COLUMN_NAME, COLUMN_ORDER) VALUES (:1, :2, :3)",
                (invoice_id, col_name, idx)
            )

        # Récupérer les COLUMN_ID pour les utiliser ensuite
        cursor.execute("SELECT COLUMN_ID, COLUMN_NAME FROM INVOICE_COLUMNS WHERE INVOICE_ID = :1 ORDER BY COLUMN_ORDER", (invoice_id,))
        col_map = {row[1]: row[0] for row in cursor}

        # 3. Insertion des lignes et valeurs
        items = structured['invoice']['line_items']
        for row_order, item in enumerate(items, start=1):
            # Insérer la ligne
            li_id = cursor.var(int)
            cursor.execute(
                "INSERT INTO INVOICE_LINE_ITEMS (INVOICE_ID, DESCRIPTION, ROW_ORDER) VALUES (:1, :2, :3) RETURNING LINE_ITEM_ID INTO :4",
                (invoice_id, item['description'], row_order, li_id)
            )
            line_item_id = li_id.getvalue()[0]

            # Insérer les valeurs pour chaque colonne
            for col_name, col_id in col_map.items():
                val_str = item['values'].get(col_name, '')
                # Tentative de conversion en nombre
                num_val = None
                if val_str and val_str != '-':
                    # Nettoyage
                    clean = val_str.replace(',', '').replace(' ', '')
                    if clean.startswith('(') and clean.endswith(')'):
                        clean = '-' + clean[1:-1]
                    try:
                        num_val = float(clean)
                    except ValueError:
                        pass
                cursor.execute(
                    "INSERT INTO INVOICE_LINE_ITEM_VALUES (LINE_ITEM_ID, COLUMN_ID, VALUE_STRING, VALUE_NUMBER) VALUES (:1, :2, :3, :4)",
                    (line_item_id, col_id, val_str, num_val)
                )

        db.commit()
        return jsonify({'success': True, 'invoice_id': invoice_id})

    except Exception as e:
        # Afficher l'erreur dans la console pour déboguer
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@bp.route('/invoices', methods=['GET'])
def get_invoices():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT i.INVOICE_ID, i.SUPPLIER, i.DOCUMENT_TITLE, i.INVOICE_DATE, i.CURRENCY,
                   c.COLUMN_ID, c.COLUMN_NAME, c.COLUMN_ORDER,
                   l.LINE_ITEM_ID, l.DESCRIPTION, l.ROW_ORDER,
                   v.VALUE_ID, v.VALUE_STRING, v.VALUE_NUMBER, v.VALUE_DATE
            FROM INVOICES i
            LEFT JOIN INVOICE_COLUMNS c ON i.INVOICE_ID = c.INVOICE_ID
            LEFT JOIN INVOICE_LINE_ITEMS l ON i.INVOICE_ID = l.INVOICE_ID
            LEFT JOIN INVOICE_LINE_ITEM_VALUES v ON l.LINE_ITEM_ID = v.LINE_ITEM_ID AND c.COLUMN_ID = v.COLUMN_ID
            ORDER BY i.INVOICE_ID, c.COLUMN_ORDER, l.ROW_ORDER
        """)
        rows = cursor.fetchall()

        # Réorganisation en JSON
        invoices_dict = {}
        for row in rows:
            inv_id = row[0]
            if inv_id not in invoices_dict:
                invoices_dict[inv_id] = {
                    'invoice_id': inv_id,
                    'supplier': row[1],
                    'document_title': row[2],
                    'invoice_date': row[3].strftime('%d %B %Y') if row[3] else None,
                    'currency': row[4],
                    'columns': {},
                    'line_items': []
                }
            # Ajout colonne
            col_id = row[5]
            if col_id and col_id not in invoices_dict[inv_id]['columns']:
                invoices_dict[inv_id]['columns'][col_id] = {
                    'name': row[6],
                    'order': row[7]
                }
            # Ajout ligne et valeur
            li_id = row[8]
            if li_id:
                # Chercher la ligne
                line = next((li for li in invoices_dict[inv_id]['line_items'] if li['id'] == li_id), None)
                if not line:
                    line = {
                        'id': li_id,
                        'description': row[9],
                        'row_order': row[10],
                        'values': {}
                    }
                    invoices_dict[inv_id]['line_items'].append(line)
                # Ajouter valeur
                if row[11]:
                    # Gérer VALUE_DATE si présente
                    if row[14] is not None:
                        val = row[14].strftime('%Y-%m-%d %H:%M:%S') if isinstance(row[14], datetime) else str(row[14])
                    elif row[13] is not None:
                        val = row[13]
                    else:
                        val = row[12]
                    line['values'][row[6]] = val  # row[6] = nom colonne

        # Convertir en liste
        result = list(invoices_dict.values())
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500