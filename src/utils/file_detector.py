import magic
from pathlib import Path

def detect_file_type(file_path: Path):
    ext = file_path.suffix.lower()
    try:
        mime = magic.from_file(str(file_path), mime=True)
    except:
        mime = None
    return ext, mime