import oracledb
from flask import current_app, g

def get_db():
    if 'db' not in g:
        g.db = oracledb.connect(
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            dsn=current_app.config['DB_DSN']
        )
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)