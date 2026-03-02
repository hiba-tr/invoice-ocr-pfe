import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'une-cle-secrete-par-defaut'
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
    OUTPUT_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'output')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Oracle Database
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_DSN = os.environ.get('DB_DSN')  # ex: 'localhost:1521/ORCL'