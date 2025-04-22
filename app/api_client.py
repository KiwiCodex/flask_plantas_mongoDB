import requests
import os

# Configuración de la API
API_URL = "https://zentracloud.com/api/v4/get_readings/"
API_TOKEN = os.getenv("API_TOKEN")  # Usa variables de entorno para seguridad
DEVICE_SN = "z6-28150"

def obtener_datos(start_date="2025-01-01 00:00:00", end_date="2025-02-02 00:00:00"):
    """Obtiene los datos del dispositivo desde ZentraCloud."""
    headers = {
        "Authorization": API_TOKEN,
        "Content-Type": "application/json"
    }
    params = {
        "device_sn": DEVICE_SN,
        "start_date": start_date,
        "end_date": end_date,
        "output_format": "json"
    }

    try:
        response = requests.get(API_URL, headers=headers, params=params)
        response.raise_for_status()  # Lanza un error si la respuesta no es 200
        return response.json()  # Retorna los datos JSON
    except requests.RequestException as e:
        print(f"Error al obtener datos: {e}")
        return None
