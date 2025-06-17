import os
import io
import math
import random
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file, make_response
)
import pandas as pd
import mysql.connector
from mysql.connector import Error
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import pdfkit  # pip install pdfkit

# Cargar variables de entorno desde .env
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'clave_secreta_segura')

# Configuración de Flask-Mail

app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 587)),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'True') == 'True',
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))
)
mail = Mail(app)

# Umbrales de inventario
UMBRAL_STOCK = float(os.getenv('UMBRAL_STOCK', 50))
UMBRAL_CRITICO = float(os.getenv('UMBRAL_CRITICO', 20))


def get_db_connection():
    """
    Retorna una conexión a MySQL usando variables de entorno.
    """
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 3306)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        return conn
    except Error as e:
        print(f"[Error] No se pudo conectar a MySQL: {e}")
        return None


# ---------------- Admin: Exportar Excel ----------------
@app.route('/admin/inventario/export_excel')
def export_excel():
    conn = get_db_connection()
    df = pd.read_sql(
        "SELECT fecha, entrada_inventario, salida_inventario FROM inventario ORDER BY fecha DESC",
        conn
    )
    conn.close()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    output.seek(0)

    return send_file(
        output,
        attachment_filename='inventario.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ---------------- Admin: Exportar PDF Inventario ----------------
@app.route('/admin/inventario/pdf')
def descargar_reporte_pdf():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT fecha, entrada_inventario, salida_inventario FROM inventario ORDER BY fecha DESC")
    filas = cur.fetchall()
    cur.close()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Reporte de Inventario", styles['Title']), Spacer(1, 12)]

    data = [["Fecha", "Entradas", "Salidas"]]
    for r in filas:
        data.append([r['fecha'].strftime("%Y-%m-%d"), r['entrada_inventario'], r['salida_inventario']])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
    ]))
    elements.append(table)
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=inventario.pdf'
    return response


# ---------------- Admin: Exportar PDF Compras ----------------
@app.route('/admin/reportes/compras/pdf')
def compras_pdf():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    modo = request.args.get('modo', 'todos')
    nombre = request.args.get('nombre', '').strip()
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()

    filtros, params = [], []
    if modo == 'cliente' and nombre:
        filtros.append("(u.nombre LIKE %s OR u.apellido LIKE %s)")
        params.extend([f"%{nombre}%", f"%{nombre}%"])
    if modo == 'fecha':
        if fecha_desde:
            filtros.append("o.fecha_creacion >= %s")
            params.append(fecha_desde)
        if fecha_hasta:
            filtros.append("o.fecha_creacion <= %s")
            params.append(f"{fecha_hasta} 23:59:59")

    sql = (
        "SELECT o.id, u.nombre, u.apellido, o.monto,"
        " o.metodo_pago, o.estado_pago, o.fecha_creacion"
        " FROM ordenes o JOIN usuarios u ON o.cliente_id = u.id"
    )
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY o.fecha_creacion DESC"

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Reporte de Órdenes")
    styles = getSampleStyleSheet()
    elements = [Paragraph("Reporte de Órdenes", styles['Title']), Spacer(1, 12)]

    data = [["ID", "Cliente", "Monto", "Método", "Estado", "Fecha"]]
    for o in rows:
        cliente = f"{o['nombre']} {o['apellido']}"
        fecha = o['fecha_creacion'].strftime("%Y-%m-%d %H:%M")
        monto = f"${o['monto']:,.2f}"
        data.append([o['id'], cliente, monto, o['metodo_pago'], o['estado_pago'], fecha])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgreen),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ]))
    elements.append(table)
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    resp = make_response(pdf)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = 'attachment; filename=ordenes.pdf'
    return resp


# ---------------- Admin: Panel ----------------
@app.route('/admin/panel')
def admin_panel():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    inv = obtener_inventario_disponible()
    return render_template('admin_panel.html', nombre=session['nombre'], inventario_actual=inv)


# ---------------- Admin: Gestionar Inventario ----------------
@app.route('/admin/inventario')
def gestionar_inventario():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM inventario ORDER BY fecha DESC")
    historial = cur.fetchall()
    cur.execute("SELECT IFNULL(SUM(entrada_inventario),0) AS ent, IFNULL(SUM(salida_inventario),0) AS sal FROM inventario")
    r = cur.fetchone()
    entradas = float(r['ent'] or 0)
    salidas = float(r['sal'] or 0)
    total = entradas - salidas
    cur.close(); conn.close()

    return render_template(
        'gestionar_inventario.html',
        historial=historial,
        total=total,
        umbral_stock=UMBRAL_STOCK,
        umbral_critico=UMBRAL_CRITICO
    )


# ---------------- Inventario Utils ----------------
def obtener_inventario_disponible():
    conn = get_db_connection()
    if not conn:
        return 0.0
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT IFNULL(SUM(entrada_inventario),0) AS ent, IFNULL(SUM(salida_inventario),0) AS sal FROM inventario")
    r = cur.fetchone()
    cur.close(); conn.close()
    return r['ent'] - r['sal']

def validar_stock_disponible(c):
    return obtener_inventario_disponible() >= c

def reducir_inventario(cantidad):
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO inventario (entrada_inventario, salida_inventario, fecha, fecha_creacion, fecha_actualizacion) VALUES(%s,%s,%s,NOW(),NOW())",
        (0, cantidad, datetime.now().date())
    )
    conn.commit(); cur.close(); conn.close()


# ---------------- Autenticación ----------------
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo'].strip()
        pwd = request.form['contrasena'].strip()
        if not correo or not pwd:
            flash('Completa todos los campos.', 'danger')
            return redirect(url_for('login'))
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM usuarios WHERE correo=%s", (correo,))
        u = cur.fetchone()
        cur.close(); conn.close()
        if not u or not check_password_hash(u['contrasena'], pwd):
            flash('Usuario o contraseña incorrectos.', 'danger')
            return redirect(url_for('login'))
        session['usuario_id'] = u['id']
        session['nombre'] = u['nombre']
        session['rol'] = u['rol']
        return redirect(url_for('admin_panel') if u['rol']=='admin' else url_for('calculadora'))
    return render_template('login.html')

@app.route('/registro', methods=['GET','POST'])
def registro():
    if request.method == 'POST':
        n = request.form['nombre'].strip().capitalize()
        a = request.form['apellido'].strip().capitalize()
        c = request.form['correo'].strip()
        p = request.form['contrasena']
        if len(p) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(url_for('registro'))
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM usuarios WHERE correo=%s", (c,))
        if cur.fetchone():
            flash('El correo ya está registrado.', 'danger')
            cur.close(); conn.close()
            return redirect(url_for('registro'))
        hashp = generate_password_hash(p)
        cur.execute(
            "INSERT INTO usuarios(nombre,apellido,correo,contrasena,rol) VALUES(%s,%s,%s,%s,'cliente')",
            (n, a, c, hashp)
        )
        conn.commit(); cur.close(); conn.close()
        flash('Usuario registrado con éxito', 'success')
        return redirect(url_for('login'))
    return render_template('registro.html')


# ---------------- Cliente: Calculadora & Cotizaciones ----------------
@app.route('/calculadora')
def calculadora():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    inv = obtener_inventario_disponible()
    return render_template('calculadora.html', inventario_disponible=inv)

@app.route('/cotizar', methods=['POST'])
def cotizar():
    if 'usuario_id' not in session:
        return jsonify(success=False, message="No estás autenticado"), 401
    largo = float(request.form['largo'])
    ancho = float(request.form['ancho'])
    prof = float(request.form['profundidad'])
    vol = largo * ancho * prof
    pol = math.ceil(4.0 * vol)
    agua = math.ceil(1.3 * vol)
    total = pol * 15000
    if not validar_stock_disponible(pol):
        return jsonify(success=False, message=f"Inventario insuficiente ({obtener_inventario_disponible():.2f}L)"), 400
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT 1 FROM cotizaciones WHERE cliente_id=%s AND habilitado=FALSE", (session['usuario_id'],))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify(success=False, message="Ya tienes una cotización pendiente."), 400
    cur.execute(
        "INSERT INTO cotizaciones(cliente_id,longitud,ancho,profundidad,aggrebind,agua,total,habilitado) VALUES(%s,%s,%s,%s,%s,%s,%s,False)",
        (session['usuario_id'], largo, ancho, prof, pol, agua, total)
    )
    conn.commit(); cur.close(); conn.close()
    return jsonify(success=True, message=f"Cotización enviada: ${total:.2f}. Pediente de aprobación.")

@app.route('/mis_cotizaciones_pendientes')
def mis_cotizaciones_pendientes():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión primero.', 'danger')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id,longitud,ancho,profundidad,total FROM cotizaciones WHERE cliente_id=%s AND habilitado=FALSE ORDER BY id DESC",
        (session['usuario_id'],)
    )
    cots = cur.fetchall()
    cur.close(); conn.close()
    return render_template('ver_cotizaciones_pendientes.html', cotizaciones=cots)

@app.route('/cliente/cotizaciones_habilitadas')
def cotizaciones_habilitadas_cliente():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT c.id,c.longitud,c.ancho,c.profundidad,c.aggrebind,c.agua,c.total FROM cotizaciones c WHERE c.cliente_id=%s AND c.habilitado=TRUE AND NOT EXISTS(SELECT 1 FROM ordenes o WHERE o.cotizacion_id=c.id) ORDER BY c.id DESC",
        (session['usuario_id'],)
    )
    habil = cur.fetchall()
    cur.close(); conn.close()
    return render_template('cliente/cotizaciones_habilitadas.html', cotizaciones=habil)

@app.route('/cliente/pagar/<int:cid>', methods=['GET','POST'])
def pagar_cotizacion(cid):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id,total FROM cotizaciones WHERE id=%s AND cliente_id=%s AND habilitado=TRUE", (cid, session['usuario_id']))
    cot = cur.fetchone()
    cur.close(); conn.close()
    if not cot:
        flash('Cotización no válida.', 'danger')
        return redirect(url_for('cotizaciones_habilitadas_cliente'))
    if request.method == 'POST':
        met = request.form['metodo_pago']
        dir_env = request.form['direccion_envio'].strip()
        ciudad = request.form['ciudad'].strip()
        cp = request.form['codigo_postal'].strip()
        if met not in ('PSE','Tarjeta') or not dir_env or not ciudad or not cp:
            flash('Datos faltan.', 'warning')
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cid))
        if met == 'Tarjeta':
            num = request.form['numero_tarjeta'].strip()
            ven = request.form['vencimiento'].strip()
            cvv = request.form['cvv'].strip()
            if len(num)!=16 or not num.isdigit():
                flash('Tarjeta inválida.', 'danger')
                return redirect(url_for('pagar_cotizacion', cotizacion_id=cid))
            detalle = f"Tarjeta ****{num[-4:]}"
        else:
            detalle = 'PSE'
        direccion_full = f"{dir_env}, {ciudad}, CP {cp}"
        orden_id = crear_orden(cid, session['usuario_id'], cot['total'], met, direccion_full)
        if not orden_id:
            flash('Error generando orden.', 'danger')
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cid))
        msg = Message('Confirmación de compra', recipients=[get_usuario_correo(session['usuario_id'])])
        msg.body = (
            f"¡Hola {session['nombre']}! Tu compra #{cid} fue exitosa.\n"
            f"Monto: ${cot['total']:.2f}\n"
            f"Método: {detalle}\n"
            f"Dirección: {direccion_full}\n"
        )
        mail.send(msg)
        return render_template('cliente/confirmacion_pago.html',
                               nombre_cliente=session['nombre'],
                               cot_id=cid,
                               monto=cot['total'],
                               metodo=detalle,
                               direccion=direccion_full)
    return render_template('cliente/pagar_cotizacion.html', cotizacion=cot)


def get_usuario_correo(uid):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute("SELECT correo FROM usuarios WHERE id=%s", (uid,))
    r = cur.fetchone()
    cur.close(); conn.close()
    return r[0] if r else None


def crear_orden(cot_id, user_id, monto, met, dir_env):
    sql = (
        "INSERT INTO ordenes"
        " (cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio)"
        " VALUES(%s,%s,%s,%s,%s)"
    )
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, (cot_id, user_id, monto, met, dir_env))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"[Error crear_orden]: {e}")
        return None
    finally:
        cur.close(); conn.close()


def listar_envios():
    sql = (
        "SELECT e.id,e.origen,e.destino,e.cantidad_litros,e.estado,"  
        "e.fecha_creacion,e.fecha_salida,e.fecha_entrega,v.placa AS vehiculo_placa,"  
        "v.capacidad_litros AS vehiculo_cap,c.nombre AS conductor_nombre "
        "FROM envios e "
        "LEFT JOIN vehiculos v ON e.vehiculo_id=v.id "
        "LEFT JOIN conductores c ON e.conductor_id=c.id "
        "ORDER BY e.fecha_creacion DESC"
    )
    conn = get_db_connection()
    if not conn:
        return []
    cur = conn.cursor(dictionary=True)
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def crear_envio(origen, destino, cantidad):
    sql = (
        "INSERT INTO envios(origen, destino, cantidad_litros)"
        " VALUES(%s,%s,%s)"
    )
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(sql, (origen, destino, cantidad))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"[Error crear_envio]: {e}")
        return None
    finally:
        cur.close(); conn.close()


def asignar_envio(envio_id, vehiculo_id, conductor_id):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT cantidad_litros FROM envios WHERE id=%s", (envio_id,)
        )
        cantidad = cur.fetchone()['cantidad_litros']
        cur.execute(
            "SELECT capacidad_litros FROM vehiculos WHERE id=%s", (vehiculo_id,)
        )
        capacidad = cur.fetchone()['capacidad_litros']
        needed = math.ceil(cantidad / capacidad)
        if cantidad > capacidad * needed:
            flash(f"Necesitan {needed} carrotanques", "warning")
        cur.execute(
            "UPDATE envios SET vehiculo_id=%s,conductor_id=%s,estado='En ruta',fecha_salida=NOW() WHERE id=%s",
            (vehiculo_id, conductor_id, envio_id)
        )
        cur.execute("UPDATE vehiculos SET disponible=0 WHERE id=%s", (vehiculo_id,))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error asignar_envio]: {e}")
        return False
    finally:
        cur.close(); conn.close()


def actualizar_estado_envio(envio_id, nuevo_estado):
    if nuevo_estado not in ('Pendiente','En ruta','Entregado','Cancelado'):
        flash('Estado inválido','danger')
        return False
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        if nuevo_estado == 'Entregado':
            cur.execute(
                "UPDATE envios SET estado=%s,fecha_entrega=NOW() WHERE id=%s",(nuevo_estado, envio_id)
            )
            cur.execute(
                "UPDATE vehiculos SET disponible=1 WHERE id=(SELECT vehiculo_id FROM envios WHERE id=%s)",
                (envio_id,)
            )
        else:
            cur.execute("UPDATE envios SET estado=%s WHERE id=%s", (nuevo_estado, envio_id))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error actualizar_estado_envio]: {e}")
        return False
    finally:
        cur.close(); conn.close()


@app.route('/envios')
def listar_envios_route():
    envs = listar_envios()
    return render_template('gestion_envios/listar_envios.html', envios=envs)

@app.route('/envios/nuevo', methods=['GET','POST'])
def crear_envio_route():
    if request.method == 'POST':
        origen = request.form['origen'].strip()
        destino = request.form['destino'].strip()
        cantidad = request.form['cantidad_litros'].strip()
        if not origen or not destino or not cantidad:
            flash('Todos los campos obligatorios','warning')
            return redirect(url_for('crear_envio_route'))
        try:
            cant_int = int(cantidad)
        except ValueError:
            flash('Cantidad inválida','danger')
            return redirect(url_for('crear_envio_route'))
        nid = crear_envio(origen,destino,cant_int)
        if nid:
            flash(f'Envío registrado ID={nid}','success')
            return redirect(url_for('asignar_envio_route',envio_id=nid))
        flash('Error creando envío','danger')
        return redirect(url_for('crear_envio_route'))
    return render_template('gestion_envios/crear_envio.html')

@app.route('/envios/<int:envio_id>/asignar', methods=['GET','POST'])
def asignar_envio_route(envio_id):
    if request.method == 'POST':
        vehiculo_id = int(request.form['vehiculo_id'])
        conductor_id = int(request.form['conductor_id'])
        ok = asignar_envio(envio_id, vehiculo_id, conductor_id)
        flash('Envío en ruta' if ok else 'Error asignando','success' if ok else 'danger')
        return redirect(url_for('listar_envios_route'))
    vehiculos = listar_vehiculos(disponibles_solo=True)
    conductores = listar_conductores()
    return render_template('gestion_envios/asignar_envio.html', envio_id=envio_id, vehiculos=vehiculos, conductores=conductores)

@app.route('/envios/<int:envio_id>/actualizar_estado', methods=['POST'])
def actualizar_estado_route(envio_id):
    nuevo = request.form['estado']
    ok = actualizar_estado_envio(envio_id, nuevo)
    flash(f"Estado actualizado a {nuevo}" if ok else "Error actualizando","success" if ok else "danger")
    return redirect(url_for('listar_envios_route'))

# Continuación CRUD Vehículos, Conductores, Reportes...


# Ruta alias para compatibilidad con templates
@app.route('/mis_cotizaciones_pendientes')
def mis_cotizaciones_pendientes():
    return redirect(url_for('ver_cotizaciones_pendientes'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)), debug=True)
