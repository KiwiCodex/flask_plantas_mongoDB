from flask import current_app
from app import mongo
from bson import ObjectId
from datetime import datetime
from geoalchemy2 import Geometry


def get_collection(name):
    return current_app.extensions['pymongo']['MONGO_URI'][name]

def get_collection(name):
    return mongo.db[name]

#---------
#Escuela
#---------
def crear_escuela(nombre, comuna, director, profesor, curso, coordenadas=None):
    escuela = {
        "nombre": nombre,
        "comuna": comuna,
        "director": director,
        "profesor": profesor,
        "curso": curso,
        "coordenadas": {"type": "Point", "coordinates": coordenadas or [0, 0]}
    }
    coleccion = get_collection('escuelas')
    return coleccion.insert_one(escuela).inserted_id


def obtener_escuelas():
    return list(get_collection('escuelas').find())

def obtener_escuela_por_id(id_):
    return get_collection('escuelas').find_one({"_id": ObjectId(id_)})

def actualizar_escuela(id_, nuevos_datos):
    return get_collection('escuelas').update_one(
        {"_id": ObjectId(id_)}, {"$set": nuevos_datos}
    )

def eliminar_escuela(id_):
    return get_collection('escuelas').delete_one({"_id": ObjectId(id_)})

def escuela_duplicada(nombre, comuna, director, profesor, coordenadas, curso):
    escuelas = obtener_escuelas()
    for esc in escuelas:
        if (
            esc["nombre"] == nombre and
            esc["comuna"] == comuna and
            esc["director"] == director and
            esc["profesor"] == profesor and
            esc.get("coordenadas", {}).get("coordinates") == coordenadas and
            esc["curso"] == curso
        ):
            return True
    return False

#---------
#Dataloger
#---------
def crear_dataloger(nombre, ip, api_token, api_url):

    dataloger = {
        "nombre": nombre, #Device_SN
        "ip": ip,
        "api_token": api_token,
        "api_url": api_url
    }

    coleccion = get_collection('datalogers')
    return coleccion.insert_one(dataloger).inserted_id


def obtener_datalogers():
    return list(get_collection('datalogers').find())

#---------
#Planta
#---------
def crear_planta(nombre, fecha_plantado, fecha_cosecha, id_variables=None):
    planta = {
        "especie": nombre,
        "fecha_plantado": fecha_plantado,
        "fecha_cosecha": fecha_cosecha,
        "id_variables": [ObjectId(v) for v in id_variables] if id_variables else []
    }
    coleccion = get_collection('plantas')
    return coleccion.insert_one(planta).inserted_id

def obtener_plantas():
    return list(get_collection('plantas').find())


#---------
#Variables
#---------

def crear_variable(nombre, unidad_medida):
    variable = {
        "nombre": nombre,
        "unidad_medida": unidad_medida
    }
    mongo.db.variables.insert_one(variable)
    return variable

def obtener_variables():
    return list(mongo.db.variables.find())

def obtener_variable_por_id(variable_id):
    return mongo.db.variables.find_one({"_id": variable_id})

def actualizar_variable(variable_id, campos_actualizados):
    return mongo.db.variables.update_one({"_id": variable_id}, {"$set": campos_actualizados})

def eliminar_variable(variable_id):
    return mongo.db.variables.delete_one({"_id": variable_id})


#---------
#Rangos
#---------


def crear_rango(id_planta, temperatura_min=None, temperatura_max=None, ph_min=None, ph_max=None, humedad_min=None, humedad_max=None):
    rango = {
        "id_planta": id_planta,
        "temperatura_min": temperatura_min,
        "temperatura_max": temperatura_max,
        "ph_min": ph_min,
        "ph_max": ph_max,
        "humedad_min": humedad_min,
        "humedad_max": humedad_max
    }
    mongo.db.rangos.insert_one(rango)
    return rango

def obtener_rangos():
    return list(mongo.db.rangos.find())

def obtener_rango_por_id(rango_id):
    return mongo.db.rangos.find_one({"_id": rango_id})

def actualizar_rango(rango_id, campos_actualizados):
    return mongo.db.rangos.update_one({"_id": rango_id}, {"$set": campos_actualizados})

def eliminar_rango(rango_id):
    return mongo.db.rangos.delete_one({"_id": rango_id})

#---------
#Modulos
#---------

def crear_modulo_escolar(nombre, ubicacion=None, coordenadas=None, id_dataloger=None, id_planta=None, id_escuela=None):
    modulo = {
        "nombre": nombre,
        "ubicacion": ubicacion,
        "coordenadas": coordenadas,  # Ejemplo: {"type": "Point", "coordinates": [lon, lat]}
        "id_dataloger": id_dataloger,
        "id_planta": id_planta,
        "id_escuela": id_escuela
    }
    mongo.db.modulos_escolares.insert_one(modulo)
    return modulo

def obtener_modulos_escolares():
    return list(mongo.db.modulos_escolares.find())

def obtener_modulo_por_id(modulo_id):
    return mongo.db.modulos_escolares.find_one({"_id": modulo_id})

def actualizar_modulo(modulo_id, campos_actualizados):
    return mongo.db.modulos_escolares.update_one({"_id": modulo_id}, {"$set": campos_actualizados})

def eliminar_modulo(modulo_id):
    return mongo.db.modulos_escolares.delete_one({"_id": modulo_id})


#---------
#Mediciones
#---------
def crear_medicion(value, id_dataloger, id_planta, precision=None, sensor_type=None, mrid=None, error_flag=False, error_description=None):
    medicion = {
        "datetime": datetime.utcnow(),
        "value": value,
        "precision": precision,
        "sensor_type": sensor_type,
        "mrid": mrid,
        "error_flag": error_flag,
        "error_description": error_description,
        "id_dataloger": id_dataloger,
        "id_planta": id_planta
    }
    mongo.db.mediciones.insert_one(medicion)
    return medicion

def obtener_mediciones():
    return list(mongo.db.mediciones.find())

def obtener_medicion_por_id(medicion_id):
    return mongo.db.mediciones.find_one({"_id": medicion_id})

def obtener_mediciones_por_planta(id_planta):
    return list(mongo.db.mediciones.find({"id_planta": id_planta}))

def obtener_mediciones_por_dataloger(id_dataloger):
    return list(mongo.db.mediciones.find({"id_dataloger": id_dataloger}))

def eliminar_medicion(medicion_id):
    return mongo.db.mediciones.delete_one({"_id": medicion_id})
