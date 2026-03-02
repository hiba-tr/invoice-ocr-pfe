import sys
import subprocess
import os
from flask import current_app
from app.filter_invoice import filter_invoice

def process_invoice(file_path):
    input_file = file_path
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_dir = current_app.config['OUTPUT_FOLDER']
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "docling",
        input_file,
        "--to", "json",
        "--output", output_dir
    ]
    print(f"DEBUG: Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Docling error: {result.stderr}\nCommande: {' '.join(cmd)}")

    raw_json = os.path.join(output_dir, base_name + ".json")
    if not os.path.exists(raw_json):
        json_files = [f for f in os.listdir(output_dir) if f.endswith('.json')]
        if not json_files:
            raise FileNotFoundError("Aucun JSON généré par Docling.")
        raw_json = os.path.join(output_dir, max(json_files, key=lambda f: os.path.getctime(os.path.join(output_dir, f))))

    structured_json_path = os.path.join(output_dir, f"{base_name}_structured.json")
    structured = filter_invoice(raw_json, structured_json_path) 
    return structured