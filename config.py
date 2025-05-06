# config.py
from dotenv import load_dotenv
import os

load_dotenv()  # Carga las variables del .env

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    MONGO_URI = os.environ.get("MONGO_URI")
