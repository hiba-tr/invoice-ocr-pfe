from flask import Flask
from config import Config

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(Config)

    from app import routes, models
    models.init_app(app)
    app.register_blueprint(routes.bp)

    return app