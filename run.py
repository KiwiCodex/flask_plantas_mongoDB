import os
from dotenv import load_dotenv
from app import create_app, db

# Cargar variables de entorno desde .env
load_dotenv()

app = create_app()

with app.app_context():
    print(db.metadata.tables.keys())

if __name__ == '__main__':
    app.run(debug=True)
