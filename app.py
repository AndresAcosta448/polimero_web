from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, send_file
)
import mysql.connector
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from mysql.connector import Error
from flask_mail import Mail, Message
import random
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import math

import pandas as pd

from io import BytesIO
import os

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

import pdfkit  

app = Flask(__name__)
app.secret_key = 'clave_secreta_segura'

def generar_recibo_pdf(pedido):
    """
    Recibe un objeto pedido (con atributos cliente, productos, total, fecha, id, etc.)
    y devuelve los bytes del PDF.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Encabezado
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Recibo de Compra")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Número de pedido: {pedido.id}")
    c.drawString(50, height - 85, f"Fecha: {pedido.fecha.strftime('%d/%m/%Y')}")

    # Datos del cliente
    c.drawString(50, height - 115, "Cliente:")
    c.drawString(80, height - 130, f"{pedido.cliente.nombre} {pedido.cliente.apellido}")
    c.drawString(80, height - 145, f"{pedido.cliente.email}")

    # Tabla de productos
    y = height - 180
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Producto")
    c.drawString(300, y, "Cantidad")
    c.drawString(400, y, "Precio unitario")
    c.drawString(500, y, "Subtotal")
    c.setFont("Helvetica", 10)
    y -= 20
    for item in pedido.lineas:
        c.drawString(50, y, item.producto.nombre)
        c.drawString(300, y, str(item.cantidad))
        c.drawString(400, y, f"${item.precio:,.2f}")
        c.drawString(500, y, f"${item.subtotal:,.2f}")
        y -= 15

    # Total
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, y - 10, "Total:")
    c.drawString(500, y - 10, f"${pedido.total:,.2f}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()


def generar_recibo_simple_bytes(pedido_id, cliente_nombre, fecha, metodo, detalle_pago, direccion, total):
    """
    Crea un PDF en memoria con los datos más básicos del recibo.
    Devuelve los bytes del PDF.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    w, h = letter

    # Encabezado
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 50, "Recibo de Compra")
    c.setFont("Helvetica", 10)
    c.drawString(50, h - 70, f"Nº pedido: {pedido_id}")
    c.drawString(50, h - 85, f"Fecha: {fecha}")

    # Datos
    c.drawString(50, h - 110, f"Cliente: {cliente_nombre}")
    c.drawString(50, h - 125, f"Método de pago: {metodo} ({detalle_pago})")
    c.drawString(50, h - 140, f"Dirección: {direccion}")
    c.drawString(50, h - 155, f"Total: ${total:,.2f}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()

# ————————————————————————————————————————————————————————————————————————————————————
@app.route('/admin/reportes/compras/pdf')
def compras_pdf():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    # ---- recoger filtros igual que antes ----
    modo        = request.args.get('modo','todos')
    nombre      = request.args.get('nombre','').strip()
    fecha_desde = request.args.get('fecha_desde','').strip()
    fecha_hasta = request.args.get('fecha_hasta','').strip()

    filtros = []; params = []
    if modo == 'cliente' and nombre:
        filtros.append("(u.nombre LIKE %s OR u.apellido LIKE %s)")
        params.extend([f"%{nombre}%", f"%{nombre}%"])
    if modo == 'fecha' and fecha_desde:
        filtros.append("o.fecha_creacion >= %s"); params.append(fecha_desde)
    if modo == 'fecha' and fecha_hasta:
        filtros.append("o.fecha_creacion <= %s"); params.append(f"{fecha_hasta} 23:59:59")

    sql = """
      SELECT o.id, u.nombre, u.apellido, o.monto, o.metodo_pago, o.estado_pago, o.fecha_creacion
        FROM ordenes o
        JOIN usuarios u ON o.cliente_id = u.id
    """
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY o.fecha_creacion DESC"

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()

    # ---- Generar PDF en memoria ----
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=letter, title="Reporte de Órdenes")
    styles = getSampleStyleSheet()
    elements = []

    # Título
    elements.append(Paragraph("Reporte de Órdenes", styles['Title']))
    elements.append(Spacer(1, 12))

    # Cabecera de tabla
    data = [["ID", "Cliente", "Monto", "Método", "Estado", "Fecha"]]
    for o in rows:
        cliente = f"{o['nombre']} {o['apellido']}"
        fecha   = o['fecha_creacion'].strftime("%Y-%m-%d %H:%M")
        monto   = f"${o['monto']:,.2f}"
        data.append([o['id'], cliente, monto, o['metodo_pago'], o['estado_pago'], fecha])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgreen),
        ('TEXTCOLOR',   (0,0), (-1,0), colors.white),
        ('ALIGN',       (0,0), (-1,-1), 'CENTER'),
        ('GRID',        (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
    ]))

    elements.append(table)
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=ordenes.pdf'
    return response

#  Conexión base de datos

def get_db_connection():
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
def get_usuario_correo(usuario_id):
    """
    Retorna el correo del usuario dado su ID.
    """
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute("SELECT correo FROM usuarios WHERE id = %s", (usuario_id,))
    fila = cur.fetchone()
    cur.close()
    conn.close()
    return fila[0] if fila else None

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
print("✅ Conectado a base:", os.getenv('DB_NAME'))

#  CRUD ÓRDENES (PAGOS SIMULADOS) – ahora con dirección de envío

def crear_orden(cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio):
    sql = """
      INSERT INTO ordenes
        (cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio)
      VALUES (%s,%s,%s,%s,%s)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        print("[DEBUG] SQL:", sql)
        print("[DEBUG] Parámetros:", (cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio))
        cursor.execute(sql, (cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio))
        conn.commit()
        print("[DEBUG] lastrowid =", cursor.lastrowid)
        return cursor.lastrowid
    except Error as e:
        print("[ERROR crear_orden]:", e)      # <— aquí verás la causa exacta
        return None
    finally:
        cursor.close()
        conn.close()


def actualizar_estado_orden(orden_id, nuevo_estado):
    """
    Cambia el estado_pago de la orden (e.g. de 'Pendiente' a 'Aprobado' o 'Rechazado').
    Actualiza la fecha_actualizacion.
    """
    if nuevo_estado not in ("Pendiente", "Aprobado", "Rechazado"):
        flash("Estado de orden inválido.", "danger")
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        sql = """
        UPDATE ordenes
        SET estado_pago = %s,
            fecha_actualizacion = NOW()
        WHERE id = %s
        """
        cursor.execute(sql, (nuevo_estado, orden_id))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error] al actualizar estado de orden: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# ----------------------------------------------------
#  RUTAS DE CLIENTE (Cotizaciones Habilitadas y Pago)
# ----------------------------------------------------



@app.route('/cliente/cotizaciones_habilitadas')
def cotizaciones_habilitadas_cliente():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    # 🔹 Obtenemos todas las cotizaciones, indicando si están pagadas o no
    cur.execute("""
        SELECT c.*,
               CASE
                   WHEN o.id IS NOT NULL THEN TRUE
                   ELSE FALSE
               END AS pagada
        FROM cotizaciones c
        LEFT JOIN ordenes o ON c.id = o.cotizacion_id
        WHERE c.cliente_id = %s
    """, (session['usuario_id'],))
    cotizaciones = cur.fetchall()

    # 🔹 Historial de pagos
    cur.execute("""
        SELECT p.id, p.monto, p.fecha_pago, o.id AS orden_id
        FROM pagos p
        JOIN ordenes o ON p.orden_id = o.id
        WHERE p.cliente_id = %s
        ORDER BY p.fecha_pago DESC
    """, (session['usuario_id'],))
    pagos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('cliente/cotizaciones_habilitadas.html',
                           cotizaciones=cotizaciones, pagos=pagos)






# ──────────────────────────────────────────────────────────────────────────────

@app.route("/cliente/pagar/<int:cotizacion_id>", methods=["GET", "POST"])
def pagar_cotizacion(cotizacion_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # 1) Recuperar cotización habilitada
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, total
        FROM cotizaciones
        WHERE id = %s
          AND cliente_id = %s
          AND habilitado = TRUE
    """, (cotizacion_id, session['usuario_id']))
    cot = cur.fetchone()
    cur.close(); conn.close()

    if not cot:
        flash("Cotización no válida o no habilitada.", "danger")
        return redirect(url_for('cotizaciones_habilitadas_cliente'))

    if request.method == "POST":
        # 2) Recoger datos del formulario
        metodo        = request.form.get("metodo_pago")
        direccion     = request.form.get("direccion_envio","").strip()
        ciudad        = request.form.get("ciudad","").strip()
        codigo_postal = request.form.get("codigo_postal","").strip()
        monto         = cot["total"]

        # 3) Validaciones...
        if metodo not in ("PSE", "Tarjeta"):
            flash("Debes seleccionar un método de pago válido.", "warning")
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))
        if not direccion or not ciudad or not codigo_postal:
            flash("Debes completar todos los datos de dirección.", "warning")
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))

        # 4) Detalles de tarjeta (si aplica)
        ultimos4 = None
        if metodo == "Tarjeta":
            numero = request.form.get("numero_tarjeta","").strip()
            venc   = request.form.get("vencimiento","").strip()
            cvv    = request.form.get("cvv","").strip()
            if len(numero)!=16 or not numero.isdigit() or not venc or not cvv:
                flash("Datos de tarjeta inválidos.", "danger")
                return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))
            ultimos4 = numero[-4:]
            detalle_pago = f"Tarjeta terminada en {ultimos4}"
        else:
            detalle_pago = "PSE (transferencia)"

        dir_completa = f"{direccion}, {ciudad}, CP {codigo_postal}"

        # 5) Crear orden en BD
        nueva_orden_id = crear_orden(cot["id"], session["usuario_id"],
                                    monto, metodo, dir_completa)
        if not nueva_orden_id:
            flash("Error al generar la orden, intenta de nuevo.", "danger")
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))

        # 6) Enviar correo de confirmación habitual
        asunto = "Confirmación de compra - Polímeros S.A."
        cuerpo = (
            f"¡Hola {session['nombre']}!\n\n"
            f"Tu compra (cotización #{cotizacion_id}) se ha realizado con éxito.\n"
            f"Monto pagado: ${monto:,.2f}\n"
            f"Método de pago: {metodo} ({detalle_pago})\n"
            f"Dirección de envío: {dir_completa}\n\n"
            "Un administrador coordinará el envío a la brevedad.\n\n"
            "Gracias por confiar en Polímeros S.A.\n"
        )
        msg = Message(subject=asunto,
                      recipients=[ get_usuario_correo(session["usuario_id"]) ])
        msg.body = cuerpo
        mail.send(msg)

        # 7) Generar recibo en PDF **con ReportLab** y enviarlo
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        w, h = letter

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, h-50, "Recibo de Compra")
        c.setFont("Helvetica", 10)
        c.drawString(50, h-70, f"Nº pedido: {nueva_orden_id}")
        c.drawString(50, h-85, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")

        c.drawString(50, h-110, f"Cliente: {session['nombre']} {session.get('apellido','')}")
        c.drawString(50, h-125, f"Método de pago: {metodo} ({detalle_pago})")
        c.drawString(50, h-140, f"Dirección: {dir_completa}")
        c.drawString(50, h-155, f"Total: ${monto:,.2f}")

        c.showPage()
        c.save()
        buffer.seek(0)
        pdf_data = buffer.read()

        msg_recibo = Message(
            subject=f"Recibo de tu pedido #{nueva_orden_id}",
            recipients=[ get_usuario_correo(session["usuario_id"]) ]
        )
        msg_recibo.body = (
            f"Hola {session['nombre']},\n\n"
            "Adjunto está tu recibo en PDF con los detalles de la compra.\n\n"
            "¡Gracias por tu compra!"
        )
        msg_recibo.attach(
            filename=f"recibo_{nueva_orden_id}.pdf",
            content_type="application/pdf",
            data=pdf_data
        )
        mail.send(msg_recibo)

        # 8) Mostrar pantalla de confirmación
        return render_template(
            "cliente/confirmacion_pago.html",
            nombre_cliente=session["nombre"],
            cot_id=cotizacion_id,
            monto=monto,
            metodo=metodo,
            detalle_pago=detalle_pago,
            direccion=dir_completa
        )

    # GET: muestra formulario
    return render_template("cliente/pagar_cotizacion.html", cotizacion=cot)



# Reporte de cotizaciones habilitadas
@app.route('/admin/reportes/cotizaciones')
def reporte_cotizaciones():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
      SELECT c.id, c.longitud, c.ancho, c.profundidad, c.total, c.aggrebind, c.agua,
             u.nombre, u.apellido
        FROM cotizaciones c
        JOIN usuarios u ON c.cliente_id = u.id
       WHERE c.habilitado = TRUE
       ORDER BY c.id DESC
    """)
    cots = cur.fetchall()
    cur.close(); conn.close()
    return render_template('reportes/cotizaciones.html', cotizaciones=cots)

# Reporte de envíos realizados (estado 'Entregado')
@app.route('/admin/reportes/envios')
def reporte_envios():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
      SELECT e.id, e.origen, e.destino, e.cantidad_litros, e.fecha_salida, e.fecha_entrega,
             v.placa AS vehiculo, c.nombre AS conductor
        FROM envios e
        LEFT JOIN vehiculos v ON e.vehiculo_id = v.id
        LEFT JOIN conductores c ON e.conductor_id = c.id
       WHERE e.estado = 'Entregado'
       ORDER BY e.fecha_entrega DESC
    """)
    envs = cur.fetchall()
    cur.close(); conn.close()
    return render_template('reportes/envios.html', envios=envs)

# Reporte de inventario actual y movimientos
@app.route('/admin/reportes/inventario')
def reporte_inventario():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    # Historial completo
    cur.execute("SELECT * FROM inventario ORDER BY fecha DESC")
    historial = cur.fetchall()
    # Totales
    cur.execute("""
      SELECT IFNULL(SUM(entrada_inventario), 0) AS entradas,
             IFNULL(SUM(salida_inventario), 0) AS salidas
        FROM inventario
    """)
    tot = cur.fetchone()
    cur.close(); conn.close()
    total_actual = tot['entradas'] - tot['salidas']
    return render_template('reportes/inventario.html',
                           historial=historial,
                           total_actual=total_actual)

@app.route('/admin/reportes/compras')
def reporte_compras():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    # Leer filtros de query string
    nombre      = request.args.get('nombre', '').strip()
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    monto_min   = request.args.get('monto_min', '').strip()
    monto_max   = request.args.get('monto_max', '').strip()

    filtros = []
    params  = []

    if nombre:
        filtros.append("(u.nombre LIKE %s OR u.apellido LIKE %s)")
        params.extend([f"%{nombre}%", f"%{nombre}%"])

    if fecha_desde:
        filtros.append("o.fecha_creacion >= %s")
        params.append(fecha_desde)

    if fecha_hasta:
        filtros.append("o.fecha_creacion <= %s")
        params.append(f"{fecha_hasta} 23:59:59")

    if monto_min:
        filtros.append("o.monto >= %s")
        params.append(monto_min)

    if monto_max:
        filtros.append("o.monto <= %s")
        params.append(monto_max)

    sql = """
        SELECT
            o.id,
            o.fecha_creacion,
            o.monto,
            o.metodo_pago,
            o.estado_pago,
            u.nombre,
            u.apellido
        FROM ordenes o
        JOIN usuarios u ON o.cliente_id = u.id
    """
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY o.fecha_creacion DESC"

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    compras = cur.fetchall()
    cur.close()
    conn.close()

    # ------------------- Órdenes & Cotizaciones -------------------

def crear_orden(cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio):
    sql = """
      INSERT INTO ordenes (cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio)
      VALUES (%s,%s,%s,%s,%s)
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (cotizacion_id, cliente_id, monto, metodo_pago, direccion_envio))
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"[ERROR crear_orden]: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def listar_ordenes_pendientes():
    sql = """
    SELECT
      o.id,
      o.cotizacion_id,
      o.cliente_id,
      o.monto,
      o.metodo_pago,
      o.estado_pago,
      o.fecha_creacion,
      u.nombre AS cliente_nombre,
      u.apellido AS cliente_apellido,
      c.total AS total_cotizacion,
      o.direccion_envio AS ciudad
    FROM ordenes o
    JOIN usuarios u ON o.cliente_id = u.id
    JOIN cotizaciones c ON o.cotizacion_id = c.id
    WHERE o.estado_pago = 'Pendiente'
    ORDER BY o.fecha_creacion DESC
    """
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return filas


def actualizar_estado_orden(orden_id, nuevo_estado):
    if nuevo_estado not in ('Pendiente','Aprobado','Rechazado'):
        flash('Estado inválido.', 'danger')
        return False
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ordenes SET estado_pago=%s, fecha_actualizacion=NOW() WHERE id=%s",
            (nuevo_estado, orden_id)
        )
        conn.commit()
        return True
    except Error as e:
        print(f"[Error actualizar_estado_orden]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def obtener_orden_por_id(envio_id):
    # Reusa listar_envios para buscar
    envs = listar_envios()
    return next((e for e in envs if e['id']==envio_id), None)

# ------------------- Vehículos, Conductores & Envios -------------------

def crear_envio(origen, destino, cantidad_litros):
    sql = """
    INSERT INTO envios (origen, destino, cantidad_litros)
    VALUES (%s, %s, %s)
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (origen, destino, cantidad_litros))
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"[Error crear_envio]: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def listar_envios():
    sql = """
    SELECT 
      e.id, e.origen, e.destino, e.cantidad_litros,
      e.fecha_creacion, e.estado,
      v.placa AS vehiculo_placa, v.capacidad_litros AS vehiculo_cap,
      c.nombre AS conductor_nombre,
      e.fecha_salida, e.fecha_entrega
    FROM envios e
    LEFT JOIN vehiculos v ON e.vehiculo_id=v.id
    LEFT JOIN conductores c ON e.conductor_id=c.id
    ORDER BY e.fecha_creacion DESC
    """
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return filas


def calcular_carrotanques(cantidad_total, capacidad_carrotanque):
    return math.ceil(cantidad_total / capacidad_carrotanque)


def asignar_envio(envio_id, vehiculo_id, conductor_id):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor(dictionary=True)
        sql_info = """
        SELECT e.cantidad_litros AS cant, v.capacidad_litros AS cap
        FROM envios e
        JOIN vehiculos v ON v.id=%s
        WHERE e.id=%s
        """
        cursor.execute(sql_info, (vehiculo_id, envio_id))
        datos = cursor.fetchone()
        if not datos:
            return False
        cant, cap = datos['cant'], datos['cap']
        num = calcular_carrotanques(cant, cap)
        if cant>cap:
            flash(f"Capacidad insuficiente ({cap}L) para {cant}L. Hacen falta {num} carrotanques.", 'warning')
        # Asignar
        cursor.execute(
            "UPDATE envios SET vehiculo_id=%s, conductor_id=%s, estado='En ruta', fecha_salida=NOW() WHERE id=%s",
            (vehiculo_id, conductor_id, envio_id)
        )
        cursor.execute("UPDATE vehiculos SET disponible=0 WHERE id=%s", (vehiculo_id,))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error asignar_envio]: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


@app.route('/admin/actualizar_estado_envio', methods=["POST"])
def actualizar_estado_envio():
    envio_id = request.form.get("envio_id")
    nuevo_estado = request.form.get("estado")

    if not envio_id or not nuevo_estado:
        flash("Datos inválidos.", "warning")
        return redirect(url_for("envios_asignados"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        if nuevo_estado == "Entregado":
            # Liberar vehículo y conductor
            cur.execute("SELECT vehiculo_id FROM envios WHERE id = %s", (envio_id,))
            veh = cur.fetchone()
            if veh and veh["vehiculo_id"]:
                cur.execute("UPDATE vehiculos SET disponible = 1 WHERE id = %s", (veh["vehiculo_id"],))

            cur.execute("""
                UPDATE envios SET estado = %s, fecha_entrega = NOW()
                WHERE id = %s
            """, (nuevo_estado, envio_id))
        else:
            cur.execute("UPDATE envios SET estado = %s WHERE id = %s", (nuevo_estado, envio_id))

        conn.commit()
        flash("Estado del envío actualizado correctamente.", "success")
    except Exception as e:
        print("Error:", e)
        flash("Error al actualizar el estado del envío.", "danger")
    finally:
        cur.close(); conn.close()

    return redirect(url_for("envios_asignados"))


# ------------------- CRUD Vehículos & Conductores -------------------

def agregar_vehiculo(tipo, placa, capacidad_litros):
    sql = "INSERT INTO vehiculos(tipo,placa,capacidad_litros) VALUES(%s,%s,%s)"
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(sql,(tipo,placa,capacidad_litros))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error agregar_vehiculo]: {e}")
        return False
    finally:
        cur.close(); conn.close()

def listar_vehiculos(disponibles_solo=False):
    sql = "SELECT id,tipo,placa,capacidad_litros,disponible FROM vehiculos"
    if disponibles_solo:
        sql += " WHERE disponible=1"
    conn = get_db_connection()
    if not conn:
        return []
    cur = conn.cursor(dictionary=True)
    cur.execute(sql)
    r = cur.fetchall()
    cur.close(); conn.close()
    return r

def agregar_conductor(nombre, cedula, telefono=None):
    sql = "INSERT INTO conductores(nombre,cedula,telefono) VALUES(%s,%s,%s)"
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(sql,(nombre,cedula,telefono))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error agregar_conductor]: {e}")
        return False
    finally:
        cur.close(); conn.close()

def listar_conductores():
    sql = "SELECT id,nombre,cedula,telefono FROM conductores"
    conn = get_db_connection()
    if not conn:
        return []
    cur = conn.cursor(dictionary=True)
    cur.execute(sql)
    r = cur.fetchall()
    cur.close()
    conn.close()
    return r


# ------------------- Rutas Envios -------------------

@app.route('/envios')
def listar_envios_route():
    envs = listar_envios()
    return render_template('gestion_envios/listar_envios.html', envios=envs)

@app.route('/envios/nuevo', methods=['GET','POST'])
def crear_envio_route():
    if request.method=='POST':
        origen=request.form.get('origen','').strip()
        destino=request.form.get('destino','').strip()
        cantidad=request.form.get('cantidad_litros','').strip()
        if not origen or not destino or not cantidad:
            flash('Todos los campos obligatorios','warning')
            return redirect(url_for('crear_envio_route'))
        try:
            cant=int(cantidad)
            if cant<=0: raise ValueError
        except:
            flash('Cantidad inválida','danger')
            return redirect(url_for('crear_envio_route'))
        nid=crear_envio(origen,destino,cant)
        if nid:
            flash(f'Envío registrado ID={nid}','success')
            return redirect(url_for('asignar_envio_route',envio_id=nid))
        flash('Error al crear envío','danger')
        return redirect(url_for('crear_envio_route'))
    return render_template('gestion_envios/crear_envio.html')

@app.route("/envios/<int:envio_id>/asignar", methods=["GET", "POST"])
def asignar_envio_route(envio_id):
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    if request.method == "POST":
        vehiculo_id  = request.form.get("vehiculo_id")
        conductor_id = request.form.get("conductor_id")
        if not vehiculo_id or not conductor_id:
            flash("Debes seleccionar vehículo y conductor.", "warning")
            return redirect(url_for("asignar_envio_route", envio_id=envio_id))

        conn = get_db_connection()
        cur  = conn.cursor()
        # 1) Actualizar ordenes con vehículo y conductor
        cur.execute("""
            UPDATE ordenes
            SET vehiculo_id        = %s,
                conductor_id       = %s,
                estado_pago        = 'Aprobado',
                fecha_actualizacion = NOW()
            WHERE id = %s
        """, (vehiculo_id, conductor_id, envio_id))
        # 2) Marcar vehículo como no disponible
        cur.execute("UPDATE vehiculos SET disponible = 0 WHERE id = %s", (vehiculo_id,))
        conn.commit()
        cur.close()
        conn.close()

        flash(f"Orden #{envio_id} asignada correctamente.", "success")
        return redirect(url_for("ordenes_pendientes"))

    # GET: recuperar y mostrar datos
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT 
          o.id,
          u.nombre AS cliente_nombre,
          u.apellido AS cliente_apellido,
          c.aggrebind AS cantidad_polimero,
          c.agua      AS cantidad_agua,
          o.direccion_envio
        FROM ordenes o
        JOIN usuarios u     ON u.id = o.cliente_id
        JOIN cotizaciones c ON c.id = o.cotizacion_id
        WHERE o.id = %s
    """, (envio_id,))
    envio = cur.fetchone()
    cur.close(); conn.close()

    if not envio:
        flash(f"Orden #{envio_id} no encontrada.", "danger")
        return redirect(url_for("ordenes_pendientes"))

    vehiculos   = listar_vehiculos(disponibles_solo=True)
    conductores = listar_conductores()

    return render_template(
        "admin/asignar_envio.html",
        envio=envio,
        vehiculos=vehiculos,
        conductores=conductores
    )
def listar_ordenes_pendientes_envio():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT o.id, u.nombre, u.apellido, u.correo, c.aggrebind, o.direccion_envio
        FROM ordenes o
        JOIN usuarios u ON o.cliente_id = u.id
        JOIN cotizaciones c ON o.cotizacion_id = c.id
        WHERE o.estado_envio = 'Pendiente' AND o.estado_pago = 'Aprobado'
        ORDER BY o.fecha_creacion DESC
    """)
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return filas
@app.route('/admin/ordenes_pendientes_envio')
def ordenes_pendientes_envio():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    ordenes = listar_ordenes_pendientes_envio()
    vehiculos = listar_vehiculos(disponibles_solo=True)
    conductores = listar_conductores()
    return render_template('admin/ordenes_pendientes_envio.html', ordenes=ordenes, vehiculos=vehiculos, conductores=conductores)

@app.route('/admin/asignar_envio', methods=['POST'])
def asignar_envio_cliente():
    orden_id = request.form['orden_id']
    vehiculo_id = request.form['vehiculo_id']
    conductor_id = request.form['conductor_id']

    conn = get_db_connection()
    cur = conn.cursor()

    # Actualiza la orden a 'En curso'
    cur.execute("""
        UPDATE ordenes SET estado_envio='En curso', vehiculo_id=%s, conductor_id=%s WHERE id=%s
    """, (vehiculo_id, conductor_id, orden_id))

    # Marca vehículo como no disponible
    cur.execute("UPDATE vehiculos SET disponible=0 WHERE id=%s", (vehiculo_id,))

    conn.commit()

    # Obtener correo cliente
    cur.execute("SELECT u.correo FROM ordenes o JOIN usuarios u ON o.cliente_id=u.id WHERE o.id=%s", (orden_id,))
    cliente_correo = cur.fetchone()[0]

    cur.close()
    conn.close()

    # Enviar correo al cliente
    msg = Message(
        subject="Tu pedido está en camino",
        recipients=[cliente_correo],
        body="Tu pedido de polímero ya ha sido asignado y está en camino."
    )
    mail.send(msg)

    flash("Envío asignado y cliente notificado.", "success")
    return redirect(url_for('ordenes_pendientes_envio'))

    # GET: mostrar datos + selects
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT 
          o.id,
          u.nombre AS cliente_nombre,
          u.apellido AS cliente_apellido,
          c.aggrebind AS cantidad_polimero,
          c.agua      AS cantidad_agua,
          o.direccion_envio
        FROM ordenes o
        JOIN usuarios u ON u.id = o.cliente_id
        JOIN cotizaciones c ON c.id = o.cotizacion_id
        WHERE o.id = %s
    """, (envio_id,))
    envio = cur.fetchone()
    cur.close(); conn.close()

    if not envio:
        flash(f"Orden #{envio_id} no encontrada.", "danger")
        return redirect(url_for("ordenes_pendientes"))

    vehiculos   = listar_vehiculos(disponibles_solo=True)
    conductores = listar_conductores()

    return render_template(
        "admin/asignar_envio.html",
        envio=envio,
        vehiculos=vehiculos,
        conductores=conductores
    )



@app.route('/admin/envios_en_curso')
def envios_en_curso():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT o.id, u.nombre, u.apellido, v.placa, c.nombre AS conductor, o.direccion_envio
        FROM ordenes o
        JOIN usuarios u ON o.cliente_id = u.id
        JOIN vehiculos v ON o.vehiculo_id = v.id
        JOIN conductores c ON o.conductor_id = c.id
        WHERE o.estado_envio = 'En curso'
    """)
    envios = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin/envios_en_curso.html', envios=envios)

@app.route('/admin/ordenes_pendientes')
def ordenes_pendientes():
    if session.get('rol')!='admin': return redirect(url_for('login'))
    ordenes=listar_ordenes_pendientes()
    return render_template('admin/ordenes_pendientes.html', ordenes=ordenes, nombre=session.get('usuario_nombre'))
@app.route('/admin/envios_asignados', methods=['GET', 'POST'])
def envios_asignados():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    if request.method == 'POST':
        envio_id = request.form['envio_id']
        nuevo_estado = request.form['estado_envio']

        cur.execute("""
            UPDATE ordenes
            SET estado_envio = %s
            WHERE id = %s
        """, (nuevo_estado, envio_id))

        conn.commit()
        flash("Estado del envío actualizado correctamente", "success")

    # Obtén los envíos asignados para mostrar
    cur.execute("""
        SELECT o.id, u.nombre, u.apellido, o.direccion_envio, o.estado_envio, v.placa, c.nombre AS conductor
        FROM ordenes o
        JOIN usuarios u ON o.cliente_id = u.id
        JOIN vehiculos v ON o.vehiculo_id = v.id
        JOIN conductores c ON o.conductor_id = c.id
        WHERE o.estado_envio IN ('En curso', 'Pendiente', 'En ruta')
        ORDER BY o.fecha_creacion DESC
    """)

    envios = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('admin/envios_asignados.html', envios=envios)

# ------------------------------
# 7. RUTAS FLASK (Gestión de Envíos)
# ------------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/vehiculos/nuevo", methods=["GET", "POST"])
def agregar_vehiculo_route():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        tipo      = request.form.get("tipo","").strip()
        placa     = request.form.get("placa","").strip()
        capacidad = request.form.get("capacidad_litros","").strip()

        # Normalización
        tipo = tipo.lower().replace(" ", "_")

        if not tipo or not placa or not capacidad.isdigit():
            flash("Todos los campos son obligatorios y válidos.", "danger")
        else:
            ok = agregar_vehiculo(tipo, placa, int(capacidad))
            if ok:
                flash("Vehículo agregado con éxito.", "success")
            else:
                flash("Error al agregar vehículo.", "danger")
        return redirect(url_for("agregar_vehiculo_route"))

        if not (6 <= len(placa) <= 10):
          flash("La placa debe tener entre 6 y 10 caracteres.", "danger")
        return redirect(url_for("agregar_vehiculo_route"))


    cur.execute("SELECT * FROM vehiculos ORDER BY id DESC")
    vehiculos = cur.fetchall()
    cur.close(); conn.close()

    return render_template("gestion_envios/agregar_vehiculo.html", vehiculos=vehiculos)



@app.route("/vehiculos/eliminar", methods=["POST"])
def eliminar_vehiculo():
    vehiculo_id = request.form.get("vehiculo_id")
    if not vehiculo_id:
        flash("Debes seleccionar un vehículo válido.", "warning")
        return redirect(url_for("agregar_vehiculo_route"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        # ¿Está asignado a algún envío activo?
        cur.execute("""
            SELECT COUNT(*) AS total FROM envios
            WHERE vehiculo_id = %s AND estado IN ('Pendiente', 'En ruta')
        """, (vehiculo_id,))
        if cur.fetchone()["total"] > 0:
            flash("❌ No se puede eliminar: el vehículo está asignado a un envío activo.", "danger")
        else:
            cur.execute("DELETE FROM vehiculos WHERE id = %s", (vehiculo_id,))
            conn.commit()
            flash("✅ Vehículo eliminado correctamente.", "success")
    except:
        flash("⚠️ Error al eliminar el vehículo.", "danger")
    finally:
        cur.close(); conn.close()

    return redirect(url_for("agregar_vehiculo_route"))




    
@app.route("/conductores/nuevo", methods=["GET", "POST"])
def agregar_conductor_route():
    if request.method == "POST":
        nombre   = request.form.get("nombre", "").strip()
        cedula   = request.form.get("cedula", "").strip()
        telefono = request.form.get("telefono", "").strip()

        if not nombre or not cedula or not telefono:
            flash("Todos los campos son obligatorios", "danger")
        elif len(nombre) < 2 or len(nombre) > 20:
            flash("El nombre debe tener entre 2 y 20 letras", "danger")
        elif not cedula.isdigit() or len(cedula) != 10:
            flash("La cédula debe tener exactamente 10 números", "danger")
        elif not telefono.isdigit() or not (7 <= len(telefono) <= 10):
            flash("El teléfono debe tener entre 7 y 10 números", "danger")
        else:
            ok = agregar_conductor(nombre, cedula, telefono)
            if ok:
                flash("Conductor agregado exitosamente", "success")
            else:
                flash("Error al agregar conductor", "danger")
        return redirect(url_for("agregar_conductor_route"))

    # GET: mostrar también los disponibles
    conductores = listar_conductores()
    return render_template("gestion_envios/agregar_conductor.html", conductores=conductores)




@app.route("/conductores/eliminar", methods=["POST"])
def eliminar_conductor_route():
    conductor_id = request.form.get("conductor_id")
    if not conductor_id:
        flash("Debes seleccionar un conductor válido.", "warning")
        return redirect(url_for("agregar_conductor_route"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        # ¿Está asignado a algún envío activo?
        cur.execute("""
            SELECT COUNT(*) AS total FROM envios
            WHERE conductor_id = %s AND estado IN ('Pendiente', 'En ruta')
        """, (conductor_id,))
        if cur.fetchone()["total"] > 0:
            flash("❌ No se puede eliminar: el conductor está asignado a un envío activo.", "danger")
        else:
            cur.execute("DELETE FROM conductores WHERE id = %s", (conductor_id,))
            conn.commit()
            flash("✅ Conductor eliminado correctamente.", "success")
    except:
        flash("⚠️ Error al eliminar el conductor.", "danger")
    finally:
        cur.close(); conn.close()

    return redirect(url_for("agregar_conductor_route"))




# ------------------------------
# RUTAS EXISTENTES DEL APP (Autenticación, Inventario, Cotizaciones, etc.)
# ------------------------------

#-------- 2. Configuración de Flask-Mail --------------------------------------
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='pipecifuentes204@gmail.com',
    MAIL_PASSWORD='cinlwepiphhrmpaz',
    MAIL_DEFAULT_SENDER='pipecifuentes204@gmail.com'
)
mail = Mail(app)

#-------- 2.1. FUNCIONES DE INVENTARIO ---------------------------------------
def obtener_inventario_disponible():
    """
    Obtiene el inventario total disponible actual
    """
    conn = get_db_connection()
    if not conn:
        return 0
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT SUM(entrada_inventario) as total_entradas, SUM(salida_inventario) as total_salidas FROM inventario")
    result = cur.fetchone()
    cur.close()
    conn.close()
    entradas = float(result['total_entradas']) if result['total_entradas'] else 0.0
    salidas = float(result['total_salidas']) if result['total_salidas'] else 0.0
    return entradas - salidas

def validar_stock_disponible(cantidad_requerida):
    """
    Valida si hay suficiente stock para la cotización
    """
    stock_actual = obtener_inventario_disponible()
    return stock_actual >= cantidad_requerida

def reducir_inventario(cantidad_utilizada):
    """
    Reduce el inventario cuando se aprueba una cotización
    """
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    # Insertar movimiento de salida (cantidad negativa)
    cur.execute("""
        INSERT INTO inventario (total_inventario, salida_inventario, fecha, fecha_creacion, fecha_actualizacion)
        VALUES (%s, %s, %s, NOW(), NOW())
    """, (-cantidad_utilizada, cantidad_utilizada, datetime.now().date()))
    conn.commit()
    cur.close()
    conn.close()

#-------- 3. Rutas de Autenticación -------------------------------------------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo'].strip()
        contrasena = request.form['contrasena'].strip()

        if not correo or not contrasena:
            flash('Debes completar todos los campos.', 'danger')
            return redirect(url_for('login'))

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM usuarios WHERE correo=%s", (correo,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if not usuario:
            flash('El correo no está registrado.', 'danger')
            return redirect(url_for('login'))

        if not check_password_hash(usuario['contrasena'], contrasena):
            flash('La contraseña es incorrecta.', 'danger')
            return redirect(url_for('login'))

        # Inicio de sesión exitoso
        session['usuario_id'] = usuario['id']
        session['nombre']     = usuario['nombre']
        session['rol']        = usuario['rol']
        if usuario['rol'] == 'admin':
            return redirect(url_for('admin_panel'))
        return redirect(url_for('calculadora'))

    return render_template('login.html')

@app.route('/registro', methods=['GET','POST'])
def registro():
    if request.method == 'POST':
        nombre      = request.form['nombre'].strip().capitalize()
        apellido    = request.form['apellido'].strip().capitalize()
        correo      = request.form['correo'].strip()
        contrasena  = request.form['contrasena']

        if len(contrasena) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(url_for('registro'))

        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("SELECT 1 FROM usuarios WHERE correo=%s", (correo,))
        if cur.fetchone():
            flash('El correo ya está registrado.', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('registro'))

        hash_ = generate_password_hash(contrasena)
        cur.execute(
            "INSERT INTO usuarios (nombre,apellido,correo,contrasena,rol) "
            "VALUES (%s,%s,%s,%s,%s)",
            (nombre, apellido, correo, hash_, 'cliente')
        )
        conn.commit()
        cur.close()
        conn.close()

        flash('Usuario registrado con éxito', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')

#-------- 4. Calculadora & Cotización -----------------------------------------
@app.route('/calculadora')
def calculadora():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    # Obtener inventario disponible para mostrar al cliente
    inventario_disponible = obtener_inventario_disponible()
    
    return render_template('calculadora.html', inventario_disponible=inventario_disponible)

import math  # ya está importado arriba

@app.route('/cotizar', methods=['POST'])
def cotizar():
    if 'usuario_id' not in session:
        return jsonify(success=False, message="No estás autenticado"), 401

    # Leer dimensiones
    largo = float(request.form['largo'])
    ancho = float(request.form['ancho'])
    profundidad = float(request.form['profundidad'])

    volumen = largo * ancho * profundidad

    POLY_FACTOR  = 4.0
    WATER_FACTOR = 1.3
    PRECIO_POLIMERO_POR_LITRO = 15000

    aggrebind_necesario = math.ceil(POLY_FACTOR * volumen)  # redondeado
    agua_necesaria = math.ceil(WATER_FACTOR * volumen)
    total_en_dinero = aggrebind_necesario * PRECIO_POLIMERO_POR_LITRO

    # Validar inventario disponible
    if not validar_stock_disponible(aggrebind_necesario):
        inventario_actual = obtener_inventario_disponible()
        return jsonify(
            success=False, 
            message=f"Inventario insuficiente. Disponible: {inventario_actual:.2f}L, Requerido: {aggrebind_necesario}L"
        ), 400

    # Verificar cotización pendiente
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT 1 FROM cotizaciones WHERE cliente_id=%s AND habilitado=FALSE",
        (session['usuario_id'],)
    )
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify(success=False, message="Ya tienes una cotización pendiente."), 400

    # Insertar en la base de datos
    cur.execute("""
        INSERT INTO cotizaciones 
          (cliente_id, longitud, ancho, profundidad, aggrebind, agua, total, habilitado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        session['usuario_id'],
        largo, ancho, profundidad,
        aggrebind_necesario,
        agua_necesaria,
        total_en_dinero,
        False
    ))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify(
        success=True,
        message=f"Cotización enviada: Total ${total_en_dinero:.2f}. Pendiente de aprobación."
    )



@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return render_template('calculadora.html', nombre=session['nombre'])

# Umbrales para destacar filas
UMBRAL_CRITICO = 500    # litros para marcar salida crítica
UMBRAL_STOCK = 1000     # litros mínimos antes de alerta de stock bajo

# Umbrales para destacar filas
UMBRAL_CRITICO = 500    # litros para marcar salida crítica
UMBRAL_STOCK = 1000     # litros mínimos antes de alerta de stock bajo

#-------- 5. GESTIÓN DE INVENTARIO (SOLO ADMIN) -----------------------------
@app.route('/admin/inventario')
def gestionar_inventario():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # Historial ordenado (más reciente primero)
    cur.execute("""
        SELECT *
        FROM inventario
        ORDER BY fecha DESC, fecha_creacion DESC
    """)
    historial = cur.fetchall()

    # Total acumulado
    cur.execute("""
        SELECT 
            IFNULL(SUM(entrada_inventario), 0) AS total_entradas,
            IFNULL(SUM(salida_inventario), 0) AS total_salidas
        FROM inventario
    """)
    resultado = cur.fetchone()
    entradas = float(resultado['total_entradas'])
    salidas = float(resultado['total_salidas'])
    total = entradas - salidas

    # Métricas diarias
    # Agregado hoy
    cur.execute("SELECT IFNULL(SUM(entrada_inventario), 0) AS agregado_hoy FROM inventario WHERE DATE(fecha) = CURDATE()")
    agregado_hoy = float(cur.fetchone()['agregado_hoy'])
    # Eliminado hoy
    cur.execute("SELECT IFNULL(SUM(salida_inventario), 0) AS eliminado_hoy FROM inventario WHERE DATE(fecha) = CURDATE()")
    eliminado_hoy = float(cur.fetchone()['eliminado_hoy'])

    # Consumo promedio diario (últimos 7 días)
    cur.execute("""
        SELECT AVG(daily.salidas) AS consumo_promedio FROM (
            SELECT DATE(fecha) AS dia, SUM(salida_inventario) AS salidas
            FROM inventario
            WHERE fecha >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(fecha)
        ) AS daily
    """)
    consumo_promedio = round(float(cur.fetchone()['consumo_promedio'] or 0), 2)

    cur.close()
    conn.close()

    # Datos para la gráfica (ejemplo con historial reciente)
    history_labels = [item['fecha'].strftime('%d/%m') for item in historial[::-1]]
    history_values = [item['total_inventario'] for item in historial[::-1]]

    return render_template(
        'gestionar_inventario.html',
        historial=historial,
        total=total,
        agregado_hoy=agregado_hoy,
        eliminado_hoy=eliminado_hoy,
        consumo_promedio=consumo_promedio,
        history_labels=history_labels,
        history_values=history_values,
        umbral_critico=UMBRAL_CRITICO,
        umbral_stock=UMBRAL_STOCK
    )

@app.route('/admin/agregar_inventario', methods=['POST'])
def agregar_inventario():
    if session.get('rol') != 'admin':
        return jsonify(success=False, message="Acceso denegado"), 403

    try:
        cantidad = float(request.form['cantidad'])
        if cantidad <= 0:
            flash('La cantidad debe ser mayor a 0', 'danger')
            return redirect(url_for('gestionar_inventario'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO inventario (
                total_inventario,
                entrada_inventario,
                fecha,
                fecha_creacion,
                fecha_actualizacion
            ) VALUES (%s, %s, NOW(), NOW(), NOW())
            """, (cantidad, cantidad)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash(f'Inventario actualizado: +{cantidad}L agregados', 'success')
        return redirect(url_for('gestionar_inventario'))

    except ValueError:
        flash('Cantidad inválida', 'danger')
        return redirect(url_for('gestionar_inventario'))
    except Exception:
        flash('Error al agregar inventario', 'danger')
        return redirect(url_for('gestionar_inventario'))

@app.route('/admin/eliminar_inventario', methods=['POST'])
def eliminar_inventario():
    if session.get('rol') != 'admin':
        return jsonify(success=False, message="Acceso denegado"), 403

    try:
        cantidad = float(request.form['cantidad'])
        if cantidad <= 0:
            flash('La cantidad debe ser mayor a 0', 'danger')
            return redirect(url_for('gestionar_inventario'))

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                COALESCE(SUM(entrada_inventario), 0) AS entradas,
                COALESCE(SUM(salida_inventario), 0) AS salidas
            FROM inventario
            """
        )
        res = cur.fetchone()
        actual = float(res['entradas']) - float(res['salidas'])

        if cantidad > actual:
            flash('No hay suficiente inventario para eliminar esa cantidad', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('gestionar_inventario'))

        nuevo_total = actual - cantidad
        cur.execute(
            """
            INSERT INTO inventario (
                total_inventario,
                salida_inventario,
                fecha,
                fecha_creacion,
                fecha_actualizacion
            ) VALUES (%s, %s, NOW(), NOW(), NOW())
            """, (nuevo_total, cantidad)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash(f'Se eliminaron {cantidad}L del inventario', 'success')
        return redirect(url_for('gestionar_inventario'))

    except Exception:
        flash('Error al eliminar inventario', 'danger')
        return redirect(url_for('gestionar_inventario'))
@app.route('/admin/inventario/export_excel')
def export_excel():
    # 1) Traer los datos de la base
    conn = get_db_connection()
    df = pd.read_sql(
        "SELECT fecha, entrada_inventario, salida_inventario, total_inventario "
        "FROM inventario ORDER BY fecha DESC",
        conn
    )
    conn.close()

    # 2) Volcarlos en un Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    output.seek(0)

    # 3) Devolver como descarga
    return send_file(
        output,
        as_attachment=True,
        download_name='inventario.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/admin/inventario/export_pdf')
def export_pdf():
    # 1) Obtener filas de la tabla
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT fecha, entrada_inventario, salida_inventario, total_inventario "
        "FROM inventario ORDER BY fecha DESC"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 2) Crear PDF en memoria usando ReportLab
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Historial de Inventario AggreBind", styles['Heading1'])]

    # Cabecera + datos
    data = [['Fecha y hora', 'Entrada (L)', 'Salida (L)', 'Total (L)']]
    for fecha, ent, sal, tot in rows:
        data.append([
            fecha.strftime('%Y-%m-%d %H:%M:%S'),
            f"{ent:.2f}",
            f"{sal:.2f}",
            f"{tot:.2f}"
        ])

    table = Table(data, hAlign='CENTER')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkgreen),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN',(1,1),(-1,-1),'CENTER'),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    # 3) Devolver como descarga
    return send_file(
        buffer,
        as_attachment=True,
        download_name='inventario.pdf',
        mimetype='application/pdf'
    )
@app.route('/api/inventario/actual')
def api_inventario_actual():
    inventario = obtener_inventario_disponible()
    return jsonify({
        'inventario_disponible': inventario,
        'timestamp': datetime.now().isoformat()
    })

#-------- 6. Eliminar cotización (admin o cliente) --------------------------
@app.route('/eliminar_cotizacion/<int:id>', methods=['POST'])
def eliminar_cotizacion(id):
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión primero.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    if session.get('rol') == 'admin':
        # Admin elimina cualquier cotización
        cur.execute("DELETE FROM cotizaciones WHERE id = %s", (id,))
        conn.commit()
        cur.close(); conn.close()
        flash(f'Cotización #{id} eliminada correctamente', 'success')
        return redirect(url_for('ver_cotizaciones'))

    # Cliente solo su propia cotización pendiente
    cur.execute(
        "SELECT cliente_id FROM cotizaciones WHERE id = %s AND habilitado = FALSE",
        (id,)
    )
    fila = cur.fetchone()
    if not fila or fila['cliente_id'] != session['usuario_id']:
        cur.close(); conn.close()
        flash('No puedes eliminar esta cotización', 'danger')
        return redirect(url_for('mis_cotizaciones_pendientes'))

    cur.execute("DELETE FROM cotizaciones WHERE id = %s", (id,))
    conn.commit()
    cur.close(); conn.close()
    flash('Tu cotización ha sido eliminada', 'success')
    return redirect(url_for('mis_cotizaciones_pendientes'))

#-------- 7. Panel del Admin -------------------------------------------------
@app.route('/admin/panel')
def admin_panel():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    # Obtener estadísticas para el dashboard
    inventario_actual = obtener_inventario_disponible()
    
    return render_template('admin_panel.html', 
                         nombre=session['nombre'],
                         inventario_actual=inventario_actual)

@app.route('/admin/gestionar_admins', methods=['GET','POST'])
def gestionar_admins():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    if request.method == 'POST':
        n = request.form['nombre']
        c = request.form['correo']
        p = request.form['contrasena']
        if len(p) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
        else:
            cur.execute(
                "INSERT INTO usuarios (nombre,correo,contrasena,rol) VALUES (%s,%s,%s,'admin')",
                (n, c, generate_password_hash(p))
            )
            conn.commit()
            flash('Administrador creado exitosamente', 'success')

    cur.execute("SELECT id,nombre,correo FROM usuarios WHERE rol='admin'")
    admins = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('gestionar_admins.html', admins=admins, mi_id=session['usuario_id'])

@app.route('/admin/eliminar_admin/<int:id>', methods=['POST'])
def eliminar_admin(id):
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    if id == session['usuario_id']:
        flash('No puedes eliminar tu propia cuenta', 'danger')
        return redirect(url_for('gestionar_admins'))

    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM usuarios WHERE id=%s AND rol='admin'", (id,))
    conn.commit()
    cur.close()
    conn.close()

    flash('Administrador eliminado', 'success')
    return redirect(url_for('gestionar_admins'))

#--------Admin: Enviar Notificaciones -----------------------------
@app.route('/admin/enviar_notificaciones', methods=['GET','POST'])
def enviar_notificaciones():
    # Solo admin
    if session.get('rol') != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    # Traer todos los clientes
    cur.execute("SELECT id, nombre, apellido, correo FROM usuarios WHERE rol IN ('cliente','usuario')")
    clientes = cur.fetchall()

    if request.method == 'POST':
        seleccion = request.form.getlist('clientes')   # lista de ids como strings
        mensaje   = request.form['mensaje'].strip()

        for uid in seleccion:
            # 1) Guardar notificación en BD
            cur.execute(
                "INSERT INTO notificaciones (usuario_id, mensaje, fecha) VALUES (%s, %s, NOW())",
                (uid, mensaje)
            )
            # 2) Obtener correo del cliente
            cur2 = conn.cursor()
            cur2.execute("SELECT correo FROM usuarios WHERE id = %s", (uid,))
            correo_cliente = cur2.fetchone()[0]
            cur2.close()
            # 3) Enviar e-mail
            msg = Message(
                subject="Tienes una nueva notificación",
                recipients=[correo_cliente]
            )
            msg.body = (
                f"Un administrador se ha comunicado contigo:\n\n"
                f"\"{mensaje}\"\n\n"
                "Por favor, ingresa a tu cuenta y revisa tus notificaciones."
            )
            mail.send(msg)

        conn.commit()
        cur.close()
        conn.close()
        flash('Notificaciones enviadas correctamente', 'success')
        return redirect(url_for('admin_panel'))

    cur.close()
    conn.close()
    return render_template('enviar_notificaciones.html', clientes=clientes)

#-------- 8. Cotizaciones para Admin & Cliente -------------------------------
@app.route('/ver_cotizaciones')
def ver_cotizaciones():
    if session.get('rol') != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
          c.id,
          c.longitud,
          c.ancho,
          c.profundidad,
          c.aggrebind,         -- litros de polímero
          c.agua,              -- litros de agua
          c.total,
          u.nombre,
          u.apellido
        FROM cotizaciones c
        JOIN usuarios u ON c.cliente_id = u.id
       WHERE c.habilitado = FALSE
    ORDER BY c.id DESC
    """)
    all_cots = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('ver_cotizaciones.html', cotizaciones=all_cots)

@app.route('/habilitar_cotizacion/<int:id>')
def habilitar_cotizacion(id):
    # Sólo admin puede
    if session.get('rol') != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    # 1) Obtener datos de la cotización
    cur.execute("""
        SELECT u.correo, c.aggrebind
          FROM cotizaciones c
          JOIN usuarios u ON c.cliente_id = u.id
         WHERE c.id = %s
    """, (id,))
    fila = cur.fetchone()
    if not fila:
        cur.close()
        conn.close()
        flash('Cotización no encontrada', 'danger')
        return redirect(url_for('ver_cotizaciones'))
    
    correo_cliente = fila['correo']
    cantidad_polimero = fila['aggrebind']

    # 2) Verificar inventario antes de habilitar
    if not validar_stock_disponible(cantidad_polimero):
        cur.close()
        conn.close()
        flash('No hay suficiente inventario para aprobar esta cotización', 'danger')
        return redirect(url_for('ver_cotizaciones'))

    # 3) Marcar habilitada y reducir inventario
    cur.execute("UPDATE cotizaciones SET habilitado=TRUE WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    
    # Reducir inventario
    reducir_inventario(cantidad_polimero)

    # 4) Enviar correo al cliente
    msg = Message(
        subject="Tu cotización ha sido aceptada",
        recipients=[correo_cliente]
    )
    msg.body = (
        f"¡Hola!\n\n"
        f"Tu cotización #{id} ha sido aceptada con éxito. Ya puedes iniciar el proceso de compra.\n\n"
        f"Saludos,\nEquipo Polímeros S.A."
    )
    mail.send(msg)

    flash('Cotización habilitada, inventario actualizado y correo enviado al cliente', 'success')
    return redirect(url_for('ver_cotizaciones'))

#-------- 9. Rutas de Cliente ------------------------------------------------
@app.route('/mis_cotizaciones_pendientes')
def mis_cotizaciones_pendientes():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión primero.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, longitud, ancho, profundidad, total
          FROM cotizaciones
         WHERE cliente_id=%s AND habilitado=FALSE
         ORDER BY id DESC
    """, (session['usuario_id'],))
    cotizaciones = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('ver_cotizaciones_cliente.html', cotizaciones=cotizaciones)

#-------- 10. Notificaciones --------------------------------------------------
@app.route('/notificaciones')
def notificaciones():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT mensaje, fecha "
        "FROM notificaciones "
        "WHERE usuario_id=%s "
        "ORDER BY fecha DESC",
        (session['usuario_id'],)
    )
    notis = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('notificaciones.html', notificaciones=notis)

#-------- 11. Recuperar y Cambiar Contraseña ----------------------------------
@app.route('/recuperar_contrasena', methods=['GET','POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        correo = request.form['correo']
        conn   = get_db_connection()
        cur    = conn.cursor(dictionary=True)
        cur.execute("SELECT correo FROM usuarios WHERE correo=%s", (correo,))
        if cur.fetchone():
            codigo = random.randint(100000,999999)
            msg    = Message("Recuperación de contraseña", recipients=[correo])
            msg.body= f"Tu código de recuperación es: {codigo}"
            mail.send(msg)
            cur.execute("UPDATE usuarios SET codigo_recuperacion=%s WHERE correo=%s", (codigo,correo))
            conn.commit()
            session['correo_recuperacion'] = correo
            flash('Código enviado', 'success')
            cur.close()
            conn.close()
            return redirect(url_for('verificar_codigo'))
        flash('Correo no registrado', 'danger')
        cur.close()
        conn.close()
    return render_template('recuperar_contrasena.html')

@app.route('/verificar_codigo', methods=['GET','POST'])
def verificar_codigo():
    if request.method == 'POST':
        correo = request.form['correo']
        codigo = request.form['codigo']
        conn   = get_db_connection()
        cur    = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT 1 FROM usuarios WHERE correo=%s AND codigo_recuperacion=%s",
            (correo, codigo)
        )
        if cur.fetchone():
            cur.close()
            conn.close()
            return redirect(url_for('cambiar_contrasena', correo=correo))
        flash('Código incorrecto', 'danger')
        cur.close()
        conn.close()
    return render_template('verificar_codigo.html')

@app.route('/cambiar_contrasena/<correo>', methods=['GET','POST'])
def cambiar_contrasena(correo):
    if request.method == 'POST':
        nueva = request.form['nueva_contrasena']
        if len(nueva) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(request.url)
        hashp = generate_password_hash(nueva)
        conn  = get_db_connection()
        cur   = conn.cursor()
        cur.execute("UPDATE usuarios SET contrasena=%s WHERE correo=%s", (hashp, correo))
        conn.commit()
        cur.close()
        conn.close()
        flash('Contraseña cambiada con éxito', 'success')
        return redirect(url_for('login'))
    return render_template('cambiar_contrasena.html')

#-------- 12. Logout ---------------------------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

#------------------------------#
#  FIN DEL APP.PY COMPLETO     #
#------------------------------#

if __name__ == '__main__':
    # Descomenta la siguiente línea la primera vez para crear las tablas de Envíos:
    # crear_tablas()
    app.run(debug=True)
