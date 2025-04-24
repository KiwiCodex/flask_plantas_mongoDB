from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, abort
from app.models import ModuloEscolar, Planta, Rangos, Escuela, Variables, Dataloger, Mediciones
import app.models as models
from app.models import get_collection
from app import db
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from .api_client import obtener_datos
from sqlalchemy import func
from datetime import datetime
from dateutil import parser
from bson import ObjectId
from bson.errors import InvalidId
from random import uniform
from colegios import COLEGIOS
import random
import requests
import json

# Define el blueprint
main = Blueprint('main', __name__)
plantas_collection = models.get_collection('plantas')
datalogers_collection = get_collection('datalogers')
variables_collection = get_collection('variables')


# -- TABLA MODULOS Y ENTIDADES --

@main.route('/')
def index():
    modulos = list(models.get_collection('modulos_escolares').find())
    return render_template('index.html', modulos=modulos)

# Crear un nuevo módulo escolar
@main.route('/modulos/crear', methods=['GET', 'POST'])
def modulos_crear():
    escuelas = list(get_collection('escuelas').find())
    datalogers = list(datalogers_collection.find())
    plantas = list(plantas_collection.find())
    rangos = list(get_collection('rangos').find())

    if request.method == 'POST':
        nombre = request.form['nombre']
        ubicacion = request.form.get('ubicacion')
        coordenadas_raw = request.form.get('coordenadas', '')  # ejemplo: "-70.6 -33.4"
        coords_split = list(map(float, coordenadas_raw.split()))
        coordenadas = {
            "type": "Point",
            "coordinates": coords_split  # [longitud, latitud]
        }

        nuevo_modulo = {
            "nombre": nombre,
            "ubicacion": ubicacion,
            "coordenadas": coordenadas,
            "id_escuela": ObjectId(request.form['escuela']),
            "id_dataloger": ObjectId(request.form['dataloger']),
            "id_planta": ObjectId(request.form['planta'])
        }

        get_collection('modulos_escolares').insert_one(nuevo_modulo)
        flash(f"<b>{nombre}</b> agregado con éxito.", "success")
        return redirect(url_for('main.index'))

    return render_template(
        'modulos_crear.html',
        escuelas=escuelas,
        datalogers=datalogers,
        plantas=plantas,
        rangos=rangos
    )


# Editar un módulo escolar
@main.route('/modulos/<id>/editar', methods=['GET', 'POST'])
def modulos_editar(id):
    modulo = get_collection('modulos_escolares').find_one({'_id': ObjectId(id)})
    if not modulo:
        abort(404)

    escuelas = list(get_collection('escuelas').find())
    datalogers = list(get_collection('datalogers').find())
    plantas = list(get_collection('plantas').find())

    if request.method == 'POST':
        nombre = request.form['nombre']
        ubicacion = request.form.get('ubicacion')
        coordenadas_raw = request.form.get('coordenadas', '')
        coords_split = list(map(float, coordenadas_raw.split()))
        coordenadas = {
            "type": "Point",
            "coordinates": coords_split
        }

        cambios = {
            "nombre": nombre,
            "ubicacion": ubicacion,
            "coordenadas": coordenadas,
            "id_escuela": ObjectId(request.form['escuela']),
            "id_dataloger": ObjectId(request.form['dataloger']),
            "id_planta": ObjectId(request.form['planta'])
        }

        get_collection('modulos_escolares').update_one({'_id': ObjectId(id)}, {"$set": cambios})
        flash(f"Se actualizó <b>{nombre}</b> correctamente.", "success")
        return redirect(url_for('main.index'))

    return render_template(
        'modulos_editar.html',
        modulo=modulo,
        escuelas=escuelas,
        datalogers=datalogers,
        plantas=plantas
    )

@main.route('/modulos/eliminar/<id>', methods=['POST'])
def modulos_eliminar(id):
    modulo = get_collection('modulos_escolares').find_one({'_id': ObjectId(id)})
    if not modulo:
        flash("Módulo no encontrado.", 'danger')
        return redirect(url_for('main.index'))

    try:
        get_collection('modulos_escolares').delete_one({'_id': ObjectId(id)})
        flash(f'El módulo {modulo["nombre"]} ha sido eliminado correctamente.', 'success')
    except Exception as e:
        flash(f'Error al eliminar el módulo: {str(e)}', 'danger')

    return redirect(url_for('main.index'))


# Función para construir el diccionario de rangos
def build_rangos_dict(rangos, variables):
    # Creamos un diccionario para acceder a los rangos por nombre de variable
    rangos_dict_mongo = {rango['id_variable']: rango for rango in rangos}

    def get_rango(var_nombre, default_min, default_max, default_unidad):
        var_doc = variables.get(var_nombre)
        if not var_doc:
            return {
                "min": default_min,
                "max": default_max,
                "unidad": default_unidad
            }

        id_var = var_doc["_id"]
        rango = rangos_dict_mongo.get(id_var, {})

        if var_nombre == "pH":
            min_val = max(0, rango.get("ph_min", default_min))
            max_val = min(14, rango.get("ph_max", default_max))
        else:
            min_val = rango.get(f"{var_nombre.lower()}_min", default_min)
            max_val = rango.get(f"{var_nombre.lower()}_max", default_max)

        return {
            "min": min_val,
            "max": max_val,
            "unidad": var_doc.get("unidad", default_unidad)
        }

    return {
        "Temperatura": get_rango("Temperatura", 15.0, 30.0, "°C"),
        "pH": get_rango("pH", 6.0, 7.5, "pH"),
        "Humedad": get_rango("Humedad", 40.0, 80.0, "%")
    }


def simulate_values(rangos_dict):
    return {
        "Temperatura": round(random.uniform(rangos_dict["Temperatura"]["min"] - 5,
                                             rangos_dict["Temperatura"]["max"] + 5), 1),
        "pH": round(random.uniform(
            max(0, rangos_dict["pH"]["min"] - 2),  
            min(14, rangos_dict["pH"]["max"] + 2)
        ), 1),
        "Humedad": round(random.uniform(rangos_dict["Humedad"]["min"] - 10,
                                         rangos_dict["Humedad"]["max"] + 10), 1)
    }


def get_variables_por_nombre(ids):
    variables = variables_collection.find({"_id": {"$in": ids}})
    return {
        v["nombre"]: {"unidad": v["unidad_medida"]}
        for v in variables
    }

# Umbrales para la puntuación
THRESHOLD_PREC_LOW = 0.5   # Si la diferencia al límite es ≤ 0.5, se marca precaución
THRESHOLD_ALERT = 1.0      # Umbral para condiciones fuera del rango

def determine_conditions(valores_simulados, rangos_dict):
    """
    Para cada variable:
      - Si el valor está fuera del rango:
          * Si la diferencia con el límite es ≤ THRESHOLD_ALERT → score = 1 (Precaución)
          * Si la diferencia es > THRESHOLD_ALERT y ≤ 4 → score = 2
          * Si la diferencia es > 4 → score = 3
      - Si el valor está dentro del rango, se considera ideal (score = 0)
    Devuelve dos diccionarios: uno con el mensaje (condiciones) y otro con los scores.
    """
    condiciones = {}
    scores = {}
    for var, rango in rangos_dict.items():
        valor = valores_simulados[var]
        min_val = rango["min"]
        max_val = rango["max"]
        if valor < min_val:
            diff = round(min_val - valor, 1)
            if diff <= THRESHOLD_ALERT:
                condiciones[var] = f"🟡 Falta {diff} {rango['unidad']} (Precaución)"
                scores[var] = 1
            elif diff <= 4:
                condiciones[var] = f"🟠 Falta {diff} {rango['unidad']}"
                scores[var] = 2
            else:
                condiciones[var] = f"🔴 Falta {diff} {rango['unidad']}"
                scores[var] = 3
        elif valor > max_val:
            diff = round(valor - max_val, 1)
            if diff <= THRESHOLD_ALERT:
                condiciones[var] = f"🟡 Exceso {diff} {rango['unidad']} (Precaución)"
                scores[var] = 1
            elif diff <= 4:
                condiciones[var] = f"🟠 Exceso {diff} {rango['unidad']}"
                scores[var] = 2
            else:
                condiciones[var] = f"🔴 Exceso {diff} {rango['unidad']}"
                scores[var] = 3
        else:
            condiciones[var] = "🟢 Dentro del rango ideal"
            scores[var] = 0
    return condiciones, scores


def calculate_final_state(scores):
    """
    Suma los scores de cada variable y asigna el estado global según la siguiente escala:
      - Total score 0   → green (😊, ¡Todo bien!)
      - Total score 1-2 → yellow (😐, En cuidado)
      - Total score 3-5 → orange (😟, Preocupado)
      - Total score mayor a 5 → red (😭, Necesito ayuda)
    """
    total_score = sum(scores.values())
    if total_score == 0:
        return "green"
    elif total_score <= 2:
        return "yellow"
    elif total_score <= 5:
        return "orange"
    else:
        return "red"

def globo_text(estado_color):
    mapping = {
        "green": ("😊", "¡Todo bien!"),
        "yellow": ("😐", "En cuidado"),
        "orange": ("😟", "Preocupado"),
        "red": ("😭", "Necesito ayuda")
    }
    return mapping.get(estado_color, ("", ""))

# --- Rutas de simulación ---
@main.route('/modulos/<id>/simulacion', methods=['GET', 'POST'])
def modulos_simulacion(id):
    modulo = get_collection('modulos_escolares').find_one({'_id': ObjectId(id)})
    if not modulo:
        abort(404)

    planta = get_collection('plantas').find_one({'_id': modulo['id_planta']})
    if not planta:
        abort(404)

    rangos = list(get_collection('rangos').find({'id_planta': planta['_id']}))
    simulacion = []

    if request.method == 'POST':
        for rango in rangos:
            valor_simulado = round(uniform(rango['valor_min'], rango['valor_max']) + uniform(-5, 5), 2)
            estado = 'Normal'
            if valor_simulado < rango['valor_min']:
                estado = 'Bajo'
            elif valor_simulado > rango['valor_max']:
                estado = 'Alto'

            variable = get_collection('variables').find_one({'_id': rango['id_variable']})
            simulacion.append({
                'variable': variable['nombre'],
                'unidad': variable['unidad'],
                'valor': valor_simulado,
                'estado': estado
            })

    return render_template(
        'modulos_simulacion.html',
        modulo=modulo,
        planta=planta,
        simulacion=simulacion
    )


@main.route('/modulos/simulacion_ajax/<id>', methods=['GET'])
def modulos_simulacion_ajax(id):
    modulo = get_collection('modulos_escolares').find_one({'_id': ObjectId(id)})
    if not modulo:
        return jsonify({"error": "Módulo no encontrado"}), 404

    planta = get_collection('plantas').find_one({'_id': modulo['id_planta']})
    if not planta:
        return jsonify({"error": "Planta no encontrada"}), 404

    rangos = list(get_collection('rangos').find({'id_planta': planta['_id']}))
    if not rangos:
        return jsonify({"error": "No hay rangos definidos para esta planta"}), 400

    # Suponiendo que las variables importantes son "Temperatura", "pH" y "Humedad"
    variables = {}
    for nombre in ["Temperatura", "pH", "Humedad"]:
        var = get_collection('variables').find_one({'nombre': nombre})
        if var:
            variables[nombre] = var

    rangos_dict = build_rangos_dict(rangos, variables)  # Asegúrate que esta función acepte documentos
    valores_simulados = simulate_values(rangos_dict)
    condiciones, scores = determine_conditions(valores_simulados, rangos_dict)
    estado_color = calculate_final_state(scores)

    return jsonify({
        "valores_simulados": valores_simulados,
        "estado_color": estado_color,
        "condiciones": condiciones,
        "scores": scores
    })


# ------------- ESCUELA -------------

@main.route('/escuela')
def escuela_lista():
    escuelas = models.obtener_escuelas()
    return render_template('escuela_lista.html', escuelas=escuelas)


@main.route('/escuela/crear', methods=['GET', 'POST'])
def escuela_crear():
    if request.method == 'POST':
        try:
            data = request.form
            nombre = data.get("nombre", "").strip()
            comuna = data.get("comuna", "").strip()
            director = data.get("director", "").strip()
            profesor = data.get("profesor", "").strip()
            curso = data.get("curso", "").strip()

            info_escuela = COLEGIOS.get(nombre)
            if not info_escuela:
                flash("Colegio no válido", "danger")
                return redirect(url_for('main.escuela_crear'))

            coordenadas_wkt = info_escuela["coordenadas"]
            lon, lat = map(float, coordenadas_wkt.replace("POINT (", "").replace(")", "").strip().split())
            coordenadas = [lon, lat]

            if models.escuela_duplicada(nombre, comuna, director, profesor, coordenadas, curso):
                flash("Ya existe una escuela con los mismos datos y curso", "danger")
                return redirect(url_for('main.escuela_crear'))

            models.crear_escuela(nombre, comuna, director, profesor, curso, coordenadas)
            flash(f"Escuela <b>{nombre}</b> creada correctamente", "success")
            return redirect(url_for('main.escuela_lista'))

        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('main.escuela_crear'))

    return render_template('escuela_crear.html', COLEGIOS=COLEGIOS)


@main.route('/escuela/editar/<id>', methods=['GET', 'POST'])
def escuela_editar(id):
    escuela = models.obtener_escuela_por_id(id)
    if not escuela:
        flash("Escuela no encontrada", "danger")
        return redirect(url_for('main.escuela_lista'))

    if request.method == 'POST':
        nuevos_datos = {
            "nombre": request.form['nombre'].strip(),
            "comuna": request.form['comuna'].strip(),
            "director": request.form['director'].strip(),
            "profesor": request.form['profesor'].strip(),
            "curso": request.form['curso'].strip()
        }
        models.actualizar_escuela(id, nuevos_datos)
        flash(f"Escuela <b>{nuevos_datos['nombre']}</b> actualizada correctamente", "success")
        return redirect(url_for('main.escuela_lista'))

    return render_template('escuela_editar.html', escuela=escuela)


@main.route('/escuela/eliminar/<id>', methods=['POST'])
def escuela_eliminar(id):
    models.eliminar_escuela(id)
    flash("Escuela eliminada correctamente", "success")
    return redirect(url_for('main.escuela_lista'))


# --- Plantas ---

@main.route('/plantas')
def plantas_lista():
    plantas = list(plantas_collection.find())
    return render_template('plantas_lista.html', plantas=plantas)

@main.route('/plantas/crear', methods=['GET', 'POST'])
def plantas_crear():
    if request.method == 'POST':
        especie = request.form['especie'].strip()
        fecha_plantado = request.form.get('fecha_plantado') or None
        fecha_cosecha = request.form.get('fecha_cosecha') or None

        # Rangos
        rangos = {
            "temperatura_min": float(request.form.get("temperatura_min", 0)),
            "temperatura_max": float(request.form.get("temperatura_max", 0)),
            "ph_min": float(request.form.get("ph_min", 0)),
            "ph_max": float(request.form.get("ph_max", 0)),
            "humedad_min": float(request.form.get("humedad_min", 0)),
            "humedad_max": float(request.form.get("humedad_max", 0))
        }

        # Variables asociadas
        id_variable_temp = request.form.get("variable_temp")
        id_variable_ph = request.form.get("variable_ph")
        id_variable_humedad = request.form.get("variable_humedad")

        variables_ids = []
        for var_id in [id_variable_temp, id_variable_ph, id_variable_humedad]:
            if var_id:
                variables_ids.append(ObjectId(var_id))

        nueva_planta = {
            "especie": especie,
            "fecha_plantado": fecha_plantado,
            "fecha_cosecha": fecha_cosecha,
            "rangos": rangos,
            "id_variables": variables_ids
        }

        plantas_collection.insert_one(nueva_planta)

        flash(f"Planta <b>{especie}</b> y sus rangos creados con éxito.", "success")
        return redirect(url_for('main.plantas_lista'))

    variables = list(variables_collection.find())
    return render_template('plantas_crear.html', variables=variables)

@main.route('/plantas/editar/<id>', methods=['GET', 'POST'])
def plantas_editar(id):
    try:
        planta = plantas_collection.find_one({'_id': ObjectId(id)})
    except InvalidId:
        flash("ID de planta inválido", "danger")
        return redirect(url_for('main.plantas_lista'))

    if not planta:
        flash("Planta no encontrada", "warning")
        return redirect(url_for('main.plantas_lista'))

    if request.method == 'POST':
        especie = request.form['especie'].strip()
        fecha_plantado = request.form.get('fecha_plantado') or None
        fecha_cosecha = request.form.get('fecha_cosecha') or None

        # Rangos
        rangos = {
            "temperatura_min": float(request.form.get("temperatura_min", 0)),
            "temperatura_max": float(request.form.get("temperatura_max", 0)),
            "ph_min": float(request.form.get("ph_min", 0)),
            "ph_max": float(request.form.get("ph_max", 0)),
            "humedad_min": float(request.form.get("humedad_min", 0)),
            "humedad_max": float(request.form.get("humedad_max", 0))
        }

        # Variables asociadas
        variables_ids = [
            ObjectId(var_id)
            for var_id in request.form.getlist('id_variables')
            if var_id
        ]

        actualizada = {
            "especie": especie,
            "fecha_plantado": fecha_plantado,
            "fecha_cosecha": fecha_cosecha,
            "rangos": rangos,
            "id_variables": variables_ids
        }

        plantas_collection.update_one({'_id': ObjectId(id)}, {"$set": actualizada})

        flash(f"Planta <b>{especie}</b> actualizada correctamente", "success")
        return redirect(url_for('main.plantas_lista'))

    variables = list(variables_collection.find())
    variables_seleccionadas = [str(vid) for vid in planta.get("id_variables", [])]

    return render_template(
        'plantas_editar.html',
        planta=planta,
        variables=variables,
        variables_seleccionadas=variables_seleccionadas
    )

@main.route('/plantas/eliminar/<id>', methods=['POST'])
def plantas_eliminar(id):
    try:
        planta = plantas_collection.find_one({'_id': ObjectId(id)})
        if not planta:
            flash("Planta no encontrada", "warning")
            return '', 404

        plantas_collection.delete_one({'_id': ObjectId(id)})
        flash("Planta y rangos eliminados correctamente", "success")
        return '', 204
    except Exception as e:
        flash(f"Error al eliminar planta: {str(e)}", "danger")
        return '', 400

# -- TABLA VARIABLES --
# ----------- LISTAR VARIABLES -----------

@main.route('/variables', methods=['GET'])
def variables_lista():
    variables = list(variables_collection.find())
    return render_template('variables_lista.html', unidades=variables)


# ----------- CREAR VARIABLE -----------

@main.route('/variables/crear', methods=['GET', 'POST'])
def variables_crear():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        unidad_medida = request.form['abreviatura'].strip()

        nueva_variable = {
            'nombre': nombre,
            'unidad_medida': unidad_medida
        }

        variables_collection.insert_one(nueva_variable)
        flash(f"Variable <b>{nombre}</b> creada correctamente", "success")
        return redirect(url_for('main.variables_lista'))

    return render_template('variables_crear.html')


# ----------- EDITAR VARIABLE -----------

@main.route('/variables/editar/<id>', methods=['GET', 'POST'])
def variables_editar(id):
    try:
        variable = variables_collection.find_one({'_id': ObjectId(id)})
    except InvalidId:
        flash("ID inválido", "danger")
        return redirect(url_for('main.variables_lista'))

    if not variable:
        flash("Variable no encontrada", "warning")
        return redirect(url_for('main.variables_lista'))

    if request.method == 'POST':
        nuevos_datos = {
            'nombre': request.form['nombre'].strip(),
            'unidad_medida': request.form['abreviatura'].strip()
        }

        variables_collection.update_one({'_id': ObjectId(id)}, {'$set': nuevos_datos})
        flash(f"Variable <b>{nuevos_datos['nombre']}</b> actualizada correctamente", "success")
        return redirect(url_for('main.variables_lista'))

    return render_template('variables_editar.html', variable=variable)


# ----------- ELIMINAR VARIABLE -----------

@main.route('/variables/eliminar/<id>', methods=['POST'])
def variables_eliminar(id):
    try:
        variable = variables_collection.find_one({'_id': ObjectId(id)})

        if not variable:
            flash("Variable no encontrada", "warning")
            return '', 404

        variables_collection.delete_one({'_id': ObjectId(id)})
        flash("Variable eliminada correctamente", "success")
        return '', 204

    except Exception:
        flash("Error al eliminar la variable. Puede estar en uso.", "danger")
        return '', 400
    

# -- TABLA DATALOGER --

# ----------- LISTA DATALOGERS -----------

@main.route('/datalogers', methods=['GET'])
def datalogers_lista():
    datalogers = list(datalogers_collection.find())
    return render_template('datalogers_lista.html', datalogers=datalogers)


# ----------- CREAR DATALOGER -----------

@main.route('/datalogers/crear', methods=['GET', 'POST'])
def datalogers_crear():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        ip = request.form['ip'].strip()
        api_token = request.form['api_token'].strip()
        api_url = request.form['api_url'].strip()

        nuevo_dataloger = {
            'nombre': nombre,
            'ip': ip,
            'api_token': api_token,
            'api_url': api_url
        }

        datalogers_collection.insert_one(nuevo_dataloger)
        flash(f"Dataloger <b>{nombre}</b> creado correctamente", "success")
        return redirect(url_for('main.datalogers_lista'))

    return render_template('datalogers_crear.html')


# ----------- EDITAR DATALOGER -----------

@main.route('/datalogers/editar/<id>', methods=['GET', 'POST'])
def datalogers_editar(id):
    try:
        datalogger = datalogers_collection.find_one({'_id': ObjectId(id)})
    except InvalidId:
        flash("ID inválido", "danger")
        return redirect(url_for('main.datalogers_lista'))

    if not datalogger:
        flash("Dataloger no encontrado", "warning")
        return redirect(url_for('main.datalogers_lista'))

    if request.method == 'POST':
        nuevos_datos = {
            'nombre': request.form['nombre'].strip(),
            'ip': request.form['ip'].strip(),
            'api_token': request.form['api_token'].strip(),
            'api_url': request.form['api_url'].strip()
        }

        datalogers_collection.update_one({'_id': ObjectId(id)}, {'$set': nuevos_datos})
        flash(f"Dataloger <b>{nuevos_datos['nombre']}</b> actualizado correctamente", "success")
        return redirect(url_for('main.datalogers_lista'))

    return render_template('datalogers_editar.html', dataloger=datalogger)


# ----------- ELIMINAR DATALOGER -----------

@main.route('/datalogers/eliminar/<id>', methods=['POST'])
def datalogers_eliminar(id):
    try:
        datalogger = datalogers_collection.find_one({'_id': ObjectId(id)})

        if not datalogger:
            flash("Dataloger no encontrado", "warning")
            return '', 404

        datalogers_collection.delete_one({'_id': ObjectId(id)})
        flash("Dataloger eliminado correctamente", "success")
        return '', 204

    except Exception as e:
        flash("Error al eliminar el Dataloger. Puede estar en uso.", "danger")
        return '', 400



# -- LIMPIAR MENSAJES SWEETALERT2 -- 
@main.route('/limpiar-mensajes', methods=['POST'])
def limpiar_mensajes():
    session.pop('mensaje', None)
    session.pop('categoria', None)
    return '', 204  # Respuesta vacía con código 204 (No Content)


# -- API -- 
@main.route('/api/datos')
def api_datos():
    """Devuelve datos desde la API de ZentraCloud."""
    start_date = request.args.get("start_date", "2025-01-01 00:00:00")
    end_date = request.args.get("end_date", "2025-02-02 00:00:00")

    datos_nube = obtener_datos(start_date, end_date)  # Suponiendo que esa función está definida en api_client.py
    if datos_nube is None:
        return jsonify({"error": "No se pudieron obtener los datos"}), 500

    return jsonify(datos_nube)

# -------------------------------
# Ruta para descargar y guardar mediciones
# -------------------------------
@main.route('/mediciones/descargar', methods=['GET', 'POST'])
def mediciones_descargar():
    datalogers_col = get_collection("datalogers")
    plantas_col = get_collection("plantas")
    mediciones_col = get_collection("mediciones")

    if request.method == 'POST':
        dataloger_id = request.form['dataloger']
        planta_id = request.form['planta']
        start_date_input = request.form.get("start_date")
        end_date_input = request.form.get("end_date")
        start_date = start_date_input.replace("T", " ") + ":00" if start_date_input else "2025-02-11 00:00:00"
        end_date = end_date_input.replace("T", " ") + ":00" if end_date_input else "2025-03-20 01:00:00"

        dataloger = datalogers_col.find_one({"_id": ObjectId(dataloger_id)})
        if not dataloger:
            flash("No se encontró el Dataloger seleccionado.", "danger")
            return redirect(url_for("main.mediciones_descargar"))

        api_token = dataloger.get("api_token")
        device_sn = dataloger.get("nombre")

        # Llamada a la API
        API_URL = "https://zentracloud.com/api/v4/get_readings/"
        params = {
            "device_sn": device_sn,
            "start_date": start_date,
            "end_date": end_date,
            "output_format": "json"
        }
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }

        response = requests.get(API_URL, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            sensor_data = data.get("data", {}).get("Atmospheric Pressure", [])
            count = 0
            for entry in sensor_data:
                for reading in entry.get("readings", []):
                    try:
                        dt_obj = parser.parse(reading.get("datetime", ""))
                    except:
                        continue
                    medicion = {
                        "datetime": dt_obj,
                        "value": reading.get("value"),
                        "precision": reading.get("precision"),
                        "sensor_type": "Atmospheric Pressure",
                        "id_dataloger": ObjectId(dataloger_id),
                        "id_planta": ObjectId(planta_id)
                    }
                    mediciones_col.insert_one(medicion)
                    count += 1
            flash(f"{count} mediciones descargadas y guardadas correctamente.", "success")
        else:
            flash(f"Error al obtener datos de la API: {response.status_code}", "danger")

        return redirect(url_for("main.mediciones_lista"))

    else:
        datalogers = list(datalogers_col.find())
        plantas = list(plantas_col.find())
        return render_template("mediciones_descargar.html", datalogers=datalogers, plantas=plantas)

# -------------------------------
# Ruta para listar todas las mediciones
# -------------------------------
@main.route('/mediciones/lista')
def mediciones_lista():
    mediciones_col = get_collection("mediciones")
    mediciones = list(mediciones_col.find().sort("datetime", -1))
    return render_template("mediciones_lista.html", readings=mediciones)

# Ruta para ver directamente los datos devueltos por la API (para depuración)
# -------------------------------
@main.route('/mediciones/ver')
def mediciones_ver():
    API_TOKEN = current_app.config.get("API_TOKEN")
    DEVICE_SN = current_app.config.get("DEVICE_SN")
    START_DATE = "2025-02-11 00:00:00"
    END_DATE = "2025-03-20 01:00:00"

    API_URL = "https://zentracloud.com/api/v4/get_readings/"
    params = {
        "device_sn": DEVICE_SN,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "output_format": "json"
    }
    headers = {
        "Authorization": API_TOKEN,
        "Content-Type": "application/json"
    }

    response = requests.get(API_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        return render_template("mediciones_ver.html", data=data)
    else:
        flash(f"Error en la solicitud: {response.status_code}", "danger")
        return redirect(url_for("main.mediciones_lista"))
    
