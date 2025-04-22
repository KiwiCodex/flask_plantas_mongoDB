# app/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from flask import current_app
from app.models import Dataloger, Mediciones  # Asegúrate de importar los modelos necesarios
from app.routes import descargar_y_guardar_mediciones  # Importa la función de descarga
from app import db  # Importa tu instancia de la base de datos

def scheduled_descarga_mediciones():
    with current_app.app_context():
        # Obtener todos los Datalogers
        datalogers = Dataloger.query.all()
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        START_DATE = one_minute_ago.strftime("%Y-%m-%d %H:%M:%S")
        END_DATE = now.strftime("%Y-%m-%d %H:%M:%S")
        for dataloger in datalogers:
            # Suponiendo que tienes una relación entre Dataloger y Planta llamada "plantas"
            for planta in dataloger.plantas:
                # Llamar a la función para descargar y guardar las mediciones
                descargar_y_guardar_mediciones(
                    dataloger.api_token,
                    dataloger.device_sn,   # Asegúrate de que el modelo Dataloger tenga este campo
                    START_DATE,
                    END_DATE,
                    dataloger.id,
                    planta.id
                )

# Inicializar el scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=scheduled_descarga_mediciones, trigger="interval", minutes=1)
scheduler.start()

# Opcional: Para detener el scheduler al finalizar la aplicación, puedes registrar una función de cierre.
def shutdown_scheduler():
    scheduler.shutdown()
