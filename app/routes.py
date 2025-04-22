from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from app.models import ModuloEscolar, Planta, Rangos, Escuela, Variables, Dataloger, Mediciones
from app import db
from colegios import COLEGIOS
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from .api_client import obtener_datos
from sqlalchemy import func
from datetime import datetime
import random
import requests
import json
from dateutil import parser


# Define el blueprint
main = Blueprint('main', __name__)

# -- TABLA MODULOS Y ENTIDADES --

@main.route('/')
def index():
    modulos = ModuloEscolar.query.all()  # Obtener todos los módulos
    return render_template('index.html', modulos=modulos)

# Crear un nuevo módulo escolar
@main.route('/modulos/crear', methods=['GET', 'POST'])
def modulos_crear():
    # Obtener escuelas con sus coordenadas y otros datos necesarios
    escuelas = Escuela.query.with_entities(
        Escuela.id, 
        Escuela.nombre, 
        Escuela.profesor,
        Escuela.curso,
        db.func.ST_AsText(Escuela.coordenadas).label("coordenadas")
    ).all()
    datalogers = Dataloger.query.all()
    plantas = Planta.query.all()
    rangos = Rangos.query.all()

    if request.method == 'POST':
        nombre = request.form['nombre']
        ubicacion = request.form.get('ubicacion', None)
        coordenadas = f"POINT({request.form.get('coordenadas', '')})"
        id_escuela = request.form['escuela']
        id_dataloger = request.form['dataloger']
        id_planta = request.form['planta']

        nuevo_modulo = ModuloEscolar(
            nombre=nombre,
            ubicacion=ubicacion,
            coordenadas=coordenadas,
            id_escuela=id_escuela,
            id_dataloger=id_dataloger,
            id_planta=id_planta
        )

        db.session.add(nuevo_modulo)
        db.session.commit()

        flash(f"<b>{nuevo_modulo.nombre}</b> agregado con éxito.", "success")
        return redirect(url_for('main.index'))

    return render_template(
        'modulos_crear.html',
        escuelas=escuelas,
        datalogers=datalogers,
        plantas=plantas,
        rangos=rangos
    )


# Editar un módulo escolar
@main.route('/modulos/editar/<int:id>', methods=['GET', 'POST'])
def modulos_editar(id):
    modulo = ModuloEscolar.query.get_or_404(id)  # Obtenemos el objeto modificable

    # Convertir coordenadas a formato WKT
    coordenadas_wkt = db.session.query(
        db.func.ST_AsText(ModuloEscolar.coordenadas)
    ).filter(ModuloEscolar.id == id).scalar()

    if request.method == 'POST':
        modulo.nombre = request.form['nombre']
        modulo.ubicacion = request.form.get('ubicacion', None)
        coordenadas = request.form.get('coordenadas', None)
        if coordenadas:
            modulo.coordenadas = func.ST_GeomFromText(f"POINT({coordenadas})")
        modulo.id_escuela = request.form['escuela']
        modulo.id_dataloger = request.form['dataloger']
        modulo.id_planta = request.form['planta']

        db.session.commit()
        flash(f"<b>{modulo.nombre}</b> ctualizado correctamente.", "success")  # 🟢 Aquí agregamos el nombre en negritas

        return redirect(url_for('main.index'))

    escuelas = Escuela.query.all()
    datalogers = Dataloger.query.all()
    plantas = Planta.query.all()
    rangos = Rangos.query.all()

    return render_template(
        'modulos_editar.html',
        modulo=modulo,
        escuelas=escuelas,
        datalogers=datalogers,
        plantas=plantas,
        rangos=rangos,
        coordenadas_wkt=coordenadas_wkt  # <-- Asegúrate de pasarlo a la plantilla
    )

@main.route('/modulos/eliminar/<int:id>', methods=['POST'])
def modulos_eliminar(id):
    modulo = ModuloEscolar.query.get_or_404(id)

    try:
        db.session.delete(modulo)
        db.session.commit()
        flash(f'El módulo {modulo.nombre} ha sido eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el módulo: {str(e)}', 'danger')

    return redirect(url_for('main.index'))


# Función para construir el diccionario de rangos
def build_rangos_dict(rangos, variables):
    return {
        "Temperatura": {
            "min": rangos.temperatura_min or 15.0,
            "max": rangos.temperatura_max or 30.0,
            "unidad": variables["Temperatura"].unidad if variables["Temperatura"] else "°C"
        },
        "pH": {
            "min": max(0, rangos.ph_min) if rangos.ph_min is not None else 6.0,
            "max": min(14, rangos.ph_max) if rangos.ph_max is not None else 7.5,
            "unidad": variables["pH"].unidad if variables["pH"] else "pH"
        },
        "Humedad": {
            "min": rangos.humedad_min or 40.0,
            "max": rangos.humedad_max or 80.0,
            "unidad": variables["Humedad"].unidad if variables["Humedad"] else "%"
        }
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

@main.route('/modulos/simulacion/<int:id>', methods=['GET'])
def modulos_simulacion(id):
    modulo = ModuloEscolar.query.get_or_404(id)
    planta = Planta.query.get_or_404(modulo.id_planta)
    rangos = Rangos.query.filter_by(id_planta=planta.id).first()
    if not rangos:
        flash("No hay rangos definidos para esta planta.", "warning")
        return redirect(url_for("main.index"))
    
    variables = {
        "Temperatura": Variables.query.filter_by(nombre="Temperatura").first(),
        "pH": Variables.query.filter_by(nombre="pH").first(),
        "Humedad": Variables.query.filter_by(nombre="Humedad").first()
    }
    
    rangos_dict = build_rangos_dict(rangos, variables)
    valores_simulados = simulate_values(rangos_dict)
    condiciones, scores = determine_conditions(valores_simulados, rangos_dict)
    estado_color = calculate_final_state(scores)
    globo = globo_text(estado_color)
    
    return render_template(
        "modulos_simulacion.html",
        modulo=modulo,
        planta=planta,
        valores_simulados=valores_simulados,
        estado_color=estado_color,
        rangos_dict=rangos_dict,
        condiciones=condiciones,
        scores=scores,  # ¡Importante pasar scores al template!
        globo=globo,
        abs=abs
    )

@main.route('/modulos/simulacion_ajax/<int:id>', methods=['GET'])
def modulos_simulacion_ajax(id):
    modulo = ModuloEscolar.query.get_or_404(id)
    planta = Planta.query.get_or_404(modulo.id_planta)
    rangos = Rangos.query.filter_by(id_planta=planta.id).first()
    if not rangos:
        return jsonify({"error": "No hay rangos definidos para esta planta"}), 400
    
    variables = {
        "Temperatura": Variables.query.filter_by(nombre="Temperatura").first(),
        "pH": Variables.query.filter_by(nombre="pH").first(),
        "Humedad": Variables.query.filter_by(nombre="Humedad").first()
    }
    
    rangos_dict = build_rangos_dict(rangos, variables)
    valores_simulados = simulate_values(rangos_dict)
    condiciones, scores = determine_conditions(valores_simulados, rangos_dict)
    estado_color = calculate_final_state(scores)
    
    return jsonify({
        "valores_simulados": valores_simulados,
        "estado_color": estado_color,
        "condiciones": condiciones,
        "scores": scores  # También pasamos los scores en el JSON
    })


# -- TABLA ESCUELA --
@main.route('/escuelas')
def escuela_lista():
    escuelas = Escuela.query.all()  # Obtener todas las escuelas de la BD
    return render_template('escuela_lista.html', escuelas=escuelas)

@main.route('/escuela/crear', methods=['GET', 'POST'])
def escuela_crear():
    if request.method == 'POST':
        try:
            data = request.form  

            nombre = data.get("nombre")
            comuna = data.get("comuna")
            director = data.get("director")
            profesor = data.get("profesor")
            curso = data.get("curso")

            # Obtener información de la escuela desde COLEGIOS
            info_escuela = COLEGIOS.get(nombre)
            if not info_escuela:
                flash("Colegio no válido", "danger")
                return redirect(url_for('main.escuela_crear'))

            coordenadas_wkt = info_escuela["coordenadas"]

            # Convertir WKT a objeto POINT
            lon, lat = map(float, coordenadas_wkt.replace("POINT (", "").replace(")", "").strip().split())
            point_geom = from_shape(Point(lon, lat))

            # Verificar si ya existe una escuela con los mismos datos excepto el curso
            escuela_existente = Escuela.query.filter_by(
                nombre=nombre,
                coordenadas=point_geom,
                comuna=comuna,
                director=director,
                profesor=profesor
            ).first()

            if escuela_existente and escuela_existente.curso == curso:
                flash("Ya existe una escuela con los mismos datos y curso. Cambie al menos un campo.", "danger")
                return redirect(url_for('main.escuela_crear'))

            # Crear la nueva escuela
            nueva_escuela = Escuela(
                nombre=nombre,
                coordenadas=point_geom,
                comuna=comuna,
                director=director,
                profesor=profesor,
                curso=curso
            )

            db.session.add(nueva_escuela)
            db.session.commit()

            flash(f"Escuela <b>{nombre}</b> creada correctamente", "success")  # 🔥 Mensaje en negritas
            return redirect(url_for('main.escuela_lista'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('main.escuela_crear'))

    return render_template('escuela_crear.html', COLEGIOS=COLEGIOS)


@main.route('/escuela/editar/<int:id>', methods=['GET', 'POST'])
def escuela_editar(id):
    escuela = Escuela.query.get_or_404(id)

    if request.method == 'POST':
        escuela.nombre = request.form['nombre']
        escuela.comuna = request.form['comuna']
        escuela.director = request.form['director']
        escuela.profesor = request.form['profesor']
        escuela.curso = request.form['curso']

        db.session.commit()
        flash(f"Escuela <b>{escuela.nombre}</b> actualizada correctamente", "success")  # 🔥 Mensaje en negritas
        return redirect(url_for('main.escuela_lista'))

    return render_template('escuela_editar.html', escuela=escuela)


@main.route('/escuela/eliminar/<int:id>', methods=['POST'])
def escuela_eliminar(id):
    escuela = Escuela.query.get_or_404(id)
    db.session.delete(escuela)
    db.session.commit()
    flash("Escuela eliminada correctamente", "success")
    return redirect(url_for('main.escuela_lista'))


# -- TABLA PLANTAS --
@main.route('/plantas')
def plantas_lista():
    plantas = Planta.query.all()
    return render_template('plantas_lista.html', plantas=plantas)

@main.route('/plantas/crear', methods=['GET', 'POST'])
def plantas_crear():
    if request.method == 'POST':
        especie = request.form['especie']
        fecha_plantado = request.form.get('fecha_plantado') or None
        fecha_cosecha = request.form.get('fecha_cosecha') or None

        # Crear la planta primero
        nueva_planta = Planta(
            especie=especie, 
            fecha_plantado=fecha_plantado, 
            fecha_cosecha=fecha_cosecha
        )
        db.session.add(nueva_planta)
        db.session.commit()  # Guardamos para obtener el ID de la planta

        # Obtener los valores de las variables
        id_variable_temp = request.form.get("variable_temp")
        id_variable_ph = request.form.get("variable_ph")
        id_variable_humedad = request.form.get("variable_humedad")

        # Crear un solo registro en Rangos con todos los valores
        nuevo_rango = Rangos(
            id_planta=nueva_planta.id,
            temperatura_min=float(request.form.get("temperatura_min")) if request.form.get("temperatura_min") else None,
            temperatura_max=float(request.form.get("temperatura_max")) if request.form.get("temperatura_max") else None,
            ph_min=float(request.form.get("ph_min")) if request.form.get("ph_min") else None,
            ph_max=float(request.form.get("ph_max")) if request.form.get("ph_max") else None,
            humedad_min=float(request.form.get("humedad_min")) if request.form.get("humedad_min") else None,
            humedad_max=float(request.form.get("humedad_max")) if request.form.get("humedad_max") else None
        )
        db.session.add(nuevo_rango)

        # Asignar variables a la planta en la tabla intermedia
        if id_variable_temp:
            nueva_planta.variables.append(Variables.query.get(int(id_variable_temp)))
        if id_variable_ph:
            nueva_planta.variables.append(Variables.query.get(int(id_variable_ph)))
        if id_variable_humedad:
            nueva_planta.variables.append(Variables.query.get(int(id_variable_humedad)))

        db.session.commit()  # Guardar todos los cambios en la base de datos

        flash(f"Planta <b>{especie}</b> y rangos agregados con éxito.", "success")  # 🟢 Aquí agregamos el nombre en negritas

        return redirect(url_for('main.plantas_lista'))

    variables = Variables.query.all()
    return render_template('plantas_crear.html', variables=variables)

@main.route('/plantas/editar/<int:id>', methods=['GET', 'POST'])
def plantas_editar(id):
    planta = Planta.query.get_or_404(id)
    variables = Variables.query.all()

    # Obtener rangos existentes o definir valores por defecto
    rango = Rangos.query.filter_by(id_planta=planta.id).first()
    if not rango:
        rango = Rangos(temperatura_min=0, temperatura_max=0, ph_min=0, ph_max=0, humedad_min=0, humedad_max=0)

    if request.method == 'POST':
        planta.especie = request.form['especie']
        planta.fecha_plantado = request.form.get('fecha_plantado') or None
        planta.fecha_cosecha = request.form.get('fecha_cosecha') or None

        id_variables = set(map(int, request.form.getlist('id_variables')))
        planta.variables = Variables.query.filter(Variables.id.in_(id_variables)).all()

        # Actualizar o crear el registro de Rangos
        rango = Rangos.query.filter_by(id_planta=planta.id).first()
        if not rango:
            rango = Rangos(id_planta=planta.id)  # Crear nuevo si no existe
            db.session.add(rango)

        rango.temperatura_min = request.form['temperatura_min']
        rango.temperatura_max = request.form['temperatura_max']
        rango.ph_min = request.form['ph_min']
        rango.ph_max = request.form['ph_max']
        rango.humedad_min = request.form['humedad_min']
        rango.humedad_max = request.form['humedad_max']

        # Guardar cambios
        db.session.commit()

        flash(f"Planta <b>{planta.especie}</b> actualizada con éxito.", "success")  # 🟢 Aquí agregamos el nombre en negritas
        return redirect(url_for('main.plantas_lista'))


    variables_seleccionadas = [v.id for v in planta.variables]
    
    return render_template('plantas_editar.html', planta=planta, variables=variables, variables_seleccionadas=variables_seleccionadas, rango=rango)

# Eliminar Planta
@main.route('/plantas/eliminar/<int:id>', methods=['POST'])
def plantas_eliminar(id):
    planta = Planta.query.get_or_404(id)

    try:
        # Eliminar los rangos asociados a la planta
        Rangos.query.filter_by(id_planta=planta.id).delete()

        # Desvincular variables de la planta antes de eliminar
        planta.variables.clear()
        db.session.commit()

        # Ahora eliminar la planta
        db.session.delete(planta)
        db.session.commit()

        flash('Planta y sus rangos eliminados con éxito.', 'success')
        return '', 204  # Respuesta exitosa sin contenido

    except Exception as e:
        db.session.rollback()
        flash('Error al eliminar la planta. Verifique dependencias.', 'danger')
        return '', 400  # Código de error

# -- TABLA VARIABLES --
@main.route('/variables', methods=['GET'])
def variables_lista():
    variables = Variables.query.all()
    return render_template('variables_lista.html', unidades=variables)  

@main.route('/variables/crear', methods=['GET', 'POST'])
def variables_crear():
    if request.method == 'POST':
        nombre = request.form['nombre']
        unidad_medida = request.form['abreviatura']  

        nueva_variable = Variables(nombre=nombre, unidad_medida=unidad_medida)
        db.session.add(nueva_variable)
        db.session.commit()

        flash(f"Variable <b>{nombre}</b> creada correctamente", "success")  # 🟢 Aquí agregamos el nombre en negritas
        return redirect(url_for('main.variables_lista'))

    return render_template('variables_crear.html')

@main.route('/variables/editar/<int:id>', methods=['GET', 'POST'])
def variables_editar(id):
    variable = Variables.query.get_or_404(id)

    if request.method == 'POST':
        variable.nombre = request.form['nombre']
        variable.unidad_medida = request.form['abreviatura']  

        db.session.commit()
        flash(f"Variable <b>{variable.nombre}</b> actualizada correctamente", "success")  # 🟢 Aquí también
        return redirect(url_for('main.variables_lista'))

    return render_template('variables_editar.html', variable=variable)

@main.route('/variables/eliminar/<int:id>', methods=['POST'])
def variables_eliminar(id):
    variable = Variables.query.get_or_404(id)
    
    try:
        db.session.delete(variable)
        db.session.commit()
        flash("Variable eliminada correctamente", "success")
        return '', 204  # Respuesta vacía con código 204 (No Content)
    
    except Exception as e:
        db.session.rollback()
        flash("Error al eliminar la variable. Puede estar en uso.", "danger")
        return '', 400  # Código de error HTTP 400 (Bad Request)


# -- TABLA DATALOGER --

@main.route('/datalogers', methods=['GET'])
def datalogers_lista():
    datalogers = Dataloger.query.all()
    return render_template('datalogers_lista.html', datalogers=datalogers)


@main.route('/datalogers/crear', methods=['GET', 'POST'])
def datalogers_crear():
    if request.method == 'POST':
        nombre = request.form['nombre']
        ip = request.form['ip']
        api_token = request.form['api_token']
        api_url = request.form['api_url']

        nuevo_dataloger = Dataloger(nombre=nombre, ip=ip, api_token=api_token, api_url=api_url)
        db.session.add(nuevo_dataloger)
        db.session.commit()

        flash(f"Dataloger <b>{nombre}</b> creado correctamente", "success")  # 🔥 Usamos flash() aquí
        return redirect(url_for('main.datalogers_lista'))

    return render_template('datalogers_crear.html')

@main.route('/datalogers/editar/<int:id>', methods=['GET', 'POST'])
def datalogers_editar(id):
    dataloger = Dataloger.query.get_or_404(id)

    if request.method == 'POST':
        dataloger.nombre = request.form['nombre']
        dataloger.ip = request.form['ip']
        dataloger.api_token = request.form['api_token']
        dataloger.api_url = request.form['api_url']

        db.session.commit()
        flash(f"Dataloger <b>{dataloger.nombre}</b> actualizado correctamente", "success")  # 🔥 También aquí
        return redirect(url_for('main.datalogers_lista'))

    return render_template('datalogers_editar.html', dataloger=dataloger)

@main.route('/datalogers/eliminar/<int:id>', methods=['POST'])
def datalogers_eliminar(id):
    datalogger = Dataloger.query.get_or_404(id)
    
    try:
        db.session.delete(datalogger)
        db.session.commit()
        flash("Dataloger eliminado correctamente", "success")
        return '', 204  # Éxito sin contenido
    
    except Exception as e:
        db.session.rollback()
        flash("Error al eliminar el Dataloger. Puede estar en uso.", "danger")
        return '', 400  # Error en la solicitud



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

def descargar_y_guardar_mediciones(api_token, device_sn, start_date, end_date, dataloger_id, planta_id):
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
    
    print("Enviando solicitud a:", API_URL)
    print("Parámetros:", params)
    print("Headers:", headers)
    
    response = requests.get(API_URL, headers=headers, params=params)
    print("Status code:", response.status_code)  # Para depuración
    if response.status_code == 200:
        data = response.json()
        # Imprime el JSON recibido (para depuración)
        print("Datos recibidos:", json.dumps(data, indent=2))
        
        # Extraer datos del sensor "Atmospheric Pressure"
        sensor_data = data.get("data", {}).get("Atmospheric Pressure", [])
        if not sensor_data:
            print("No se encontraron datos para 'Atmospheric Pressure'.")
            return
        
        count = 0  # Contador de mediciones insertadas
        for entry in sensor_data:
            readings = entry.get("readings", [])
            for reading in readings:
                dt_str = reading.get("datetime", "")
                try:
                    # Usamos dateutil.parser para interpretar la cadena de fecha
                    dt_obj = parser.parse(dt_str)
                except Exception as e:
                    print(f"Error al parsear fecha: {dt_str} - {e}")
                    continue

                value = reading.get("value")
                precision = reading.get("precision")
                sensor_type = "Atmospheric Pressure"
                
                # Crear la instancia del modelo Mediciones
                medicion = Mediciones(
                    datetime=dt_obj,
                    value=value,
                    precision=precision,
                    sensor_type=sensor_type,
                    id_dataloger=dataloger_id,
                    id_planta=planta_id
                )
                db.session.add(medicion)
                print(f"Agregando medición: {medicion}")
                count += 1
        db.session.commit()
        print(f"¡Mediciones guardadas correctamente! Total insertadas: {count}")
    else:
        print(f"Error en la solicitud: {response.status_code}")

# -------------------------------
# Ruta para desplegar el formulario de descarga de mediciones
# -------------------------------
@main.route('/mediciones/descargar', methods=['GET', 'POST'])
def mediciones_descargar():
    if request.method == 'POST':
        # Recoger los datos del formulario
        dataloger_id = request.form['dataloger']
        planta_id = request.form['planta']
        start_date_input = request.form.get("start_date")
        end_date_input = request.form.get("end_date")
        # Convertir el formato de "datetime-local" a "YYYY-MM-DD HH:MM:SS"
        START_DATE = start_date_input.replace("T", " ") + ":00" if start_date_input else "2025-02-11 00:00:00"
        END_DATE = end_date_input.replace("T", " ") + ":00" if end_date_input else "2025-03-20 01:00:00"
        
        # Obtener el Dataloger desde la BD y usar sus datos
        dataloger = Dataloger.query.get(dataloger_id)
        if not dataloger:
            flash("No se encontró el Dataloger seleccionado.", "danger")
            return redirect(url_for("main.mediciones_descargar"))
        
        # Se asume que el campo 'nombre' del Dataloger funciona como device_sn; ajusta si tienes otro campo.
        DEVICE_SN = dataloger.nombre
        API_TOKEN = dataloger.api_token
        
        descargar_y_guardar_mediciones(API_TOKEN, DEVICE_SN, START_DATE, END_DATE, dataloger_id, planta_id)
    
        flash("Mediciones descargadas y almacenadas correctamente.", "success")
        return redirect(url_for("main.mediciones_lista"))
    else:
        # En GET: mostrar el formulario para que el usuario seleccione Dataloger, Planta y las fechas deseadas
        datalogers = Dataloger.query.all()
        plantas = Planta.query.all()
        return render_template("mediciones_descargar.html", datalogers=datalogers, plantas=plantas)

# -------------------------------
# Ruta para listar todas las mediciones almacenadas en la BD
# -------------------------------
@main.route('/mediciones/lista')
def mediciones_lista():
    readings = Mediciones.query.order_by(Mediciones.datetime.desc()).all()
    return render_template("mediciones_lista.html", readings=readings)

# -------------------------------
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
        print("Datos recibidos:", json.dumps(data, indent=2))
        return render_template("mediciones_ver.html", data=data)
    else:
        flash(f"Error en la solicitud: {response.status_code}", "danger")
        return redirect(url_for("main.mediciones_lista"))

'''
@main.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        # Obtener datos del formulario
        numero = request.form['numero']
        especie = request.form['especie']
        temperatura_min = request.form['temperatura_min']
        temperatura_max = request.form['temperatura_max']
        ph_min = request.form['ph_min']
        ph_max = request.form['ph_max']
        humedad_min = request.form['humedad_min']
        humedad_max = request.form['humedad_max']

        # Crear instancia de ModuloEscolar
        nuevo_modulo = ModuloEscolar(nombre=numero)
        db.session.add(nuevo_modulo)
        db.session.commit()  # Guardar para obtener el ID del módulo

        # Crear una nueva planta asociada al módulo
        nueva_planta = Planta(especie=especie)
        db.session.add(nueva_planta)
        db.session.commit()

        # Asociar la planta al módulo
        nuevo_modulo.id_planta = nueva_planta.id
        db.session.commit()

        # Crear los rangos asociados a la planta
        nuevos_rangos = Rangos(
            id_planta=nueva_planta.id,
            temperatura_min=temperatura_min,
            temperatura_max=temperatura_max,
            ph_min=ph_min,
            ph_max=ph_max,
            humedad_min=humedad_min,
            humedad_max=humedad_max
        )
        db.session.add(nuevos_rangos)
        db.session.commit()

        flash("Módulo agregado exitosamente.")
        return redirect(url_for('main.index'))

    return render_template('create.html')

@main.route('/modulos/<int:id>')
def show(id):
    modulo = ModuloEscolar.query.get_or_404(id)
    return render_template('show.html', modulo=modulo, rangos=modulo.planta.rangos if modulo.planta else None)

@main.route('/simulate/<int:id>')
def simulate(id):
    modulo = ModuloEscolar.query.get_or_404(id)
    rangos = modulo.planta.rangos if modulo.planta else None

    if not rangos:
        flash("No se encontraron rangos para este módulo.")
        return redirect(url_for('main.index'))

    # Generar valores simulados
    import random
    valores_simulados = {
        'temperatura': random.uniform(10, 40),
        'ph': random.uniform(4, 9),
        'humedad': random.randint(10, 100)
    }

    # Determinar si están dentro del rango ideal
    condiciones = {
        'temperatura': rangos.temperatura_min <= valores_simulados['temperatura'] <= rangos.temperatura_max,
        'ph': rangos.ph_min <= valores_simulados['ph'] <= rangos.ph_max,
        'humedad': rangos.humedad_min <= valores_simulados['humedad'] <= rangos.humedad_max
    }

    # Determinar estado general (verde, amarillo, naranja, rojo)
    estado_color = 'green'
    if not all(condiciones.values()):
        estado_color = 'yellow' if sum(condiciones.values()) == 2 else 'orange' if sum(condiciones.values()) == 1 else 'red'

    return render_template(
        'simulate.html',
        modulo=modulo,
        valores_simulados=valores_simulados,
        condiciones=condiciones,
        estado_color=estado_color
    )

@main.route('/modulos/<int:id>/delete', methods=['POST'])
def delete(id):
    modulo = ModuloEscolar.query.get_or_404(id)
    
    # Eliminar la planta y sus rangos antes de eliminar el módulo
    if modulo.planta:
        if modulo.planta.rangos:
            db.session.delete(modulo.planta.rangos)
        db.session.delete(modulo.planta)

    db.session.delete(modulo)
    db.session.commit()

    flash("Módulo eliminado exitosamente.")
    return redirect(url_for('main.index'))
'''