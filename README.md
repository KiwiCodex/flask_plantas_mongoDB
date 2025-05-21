Requisitos:
- Python 3.9+
- MongoDB (instalado localmente o en la nube)
- MongoDB Compass (opcional, para visualizar datos)
- Pipenv o venv
- Navegador web (Chrome, Firefox, etc.)

Clona el repositorio
```
git clone https://github.com/usuario/mi_proyecto_flask_mongo.git
cd mi_proyecto_flask_mongo
```
Crea entorno virtual
```
python -m venv venv
# En Windows
venv\Scripts\activate
# En Linux/Mac
source venv/bin/activate
```
Instala dependencias
```
pip install -r requirements.txt
```
Configura la conexión MongoDB
Edita el archivo config.py o app.py para poner tu URI de MongoDB:
```
MONGO_URI = "mongodb://localhost:27017/nombre_de_tu_base"
```
Ejecuta la aplicación
```
python run.py
```
Luego entra en http://127.0.0.1:5000



Estructura del proyecto:
```
/mi_proyecto_flask_mongo
│
├── run.py                   # Punto de entrada
├── app.py                   # Configuración Flask + MongoDB
├── models.py                # Funciones CRUD con PyMongo
├── rutas/                   # Rutas para cada entidad
│   ├── escuela_routes.py
│   ├── planta_routes.py
│   ├── dataloger_routes.py
│   └── variables_routes.py
│
├── templates/               # HTML con Jinja2
│   ├── index.html
│   ├── escuela/
│   └── planta/
│
├── static/                  # JS, CSS, etc.
└── requirements.txt         # Paquetes necesarios
```



