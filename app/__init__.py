# app/__init__.py
from flask import Flask
from pymongo import MongoClient
from config import Config

mongo = None  # Variable global para compartir la conexión

def create_app():
    global mongo
    app = Flask(__name__)
    app.config.from_object(Config)

    # Conexión a MongoDB
    client = MongoClient(app.config["MONGO_URI"])
    mongo = client["huertosdb"]  # Acceso directo

    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app
