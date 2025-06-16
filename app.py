from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from mysql.connector import Error
from flask_mail import Mail, Message
import random
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import math
from flask import send_file
import io
from flask import make_response, request
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import pdfkit  # instala con `pip install pdfkit`
app = Flask(__name__)
app.secret_key = 'clave_secreta_segura'


@app.route('/admin/inventario/export_excel')
def export_excel():
    # 1) Leer inventario
    conn = get_db_connection()
    df = pd.read_sql("SELECT fecha, entrada_inventario, salida_inventario FROM inventario ORDER BY fecha DESC", conn)
    conn.close()

    # 2) Generar Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    output.seek(0)

    # 3) Devolver descarga
    return send_file(
        output,
        attachment_filename='inventario.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    @app.route('/admin/inventario/pdf')
def descargar_reporte_pdf():
    # 1) Consulta inventario
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT fecha, entrada_inventario, salida_inventario FROM inventario ORDER BY fecha DESC")
    filas = cur.fetchall()
    cur.close(); conn.close()

    # 2) Generar PDF en memoria (usando ReportLab)
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Reporte de Inventario", styles['Title']), Spacer(1,12)]

    # Tabla
    data = [["Fecha", "Entradas", "Salidas"]]
    for r in filas:
        data.append([r['fecha'].strftime("%Y-%m-%d"), r['entrada_inventario'], r['salida_inventario']])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.lightblue),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey),
        ('ALIGN',(1,1),(-1,-1),'CENTER'),
    ]))
    elements.append(table)
    doc.build(elements)

    # 3) Devolver PDF
    pdf = buffer.getvalue()
    buffer.close()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=inventario.pdf'
    return response

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
    data = [[
        "ID", "Cliente", "Monto", "Método", "Estado", "Fecha"
    ]]
    # Filas
    for o in rows:
        cliente = f"{o['nombre']} {o['apellido']}"
        fecha   = o['fecha_creacion'].strftime("%Y-%m-%d %H:%M")
        monto   = f"${o['monto']:,.2f}"
        data.append([o['id'], cliente, monto, o['metodo_pago'], o['estado_pago'], fecha])

    # Crear tabla
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

    # Devolver como descarga
    pdf = buffer.getvalue()
    buffer.close()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=ordenes.pdf'
    return response
# Conexión a Railway
def get_db_connection():
    """
    Retorna un objeto de conexión a MySQL en Railway.
    """
    try:
        conn = mysql.connector.connect(
            host='mainline.proxy.rlwy.net',
            port=23787,
            user='root',
            password='UZBILEBsVmNsDlZKcQNvIvEuhtGqpeTT',  # tu contraseña de Railway
            database='railway'  # nombre de la base en Railway
        )
        print("✅ Conectado a base: railway")
        return conn
    except Error as e:
        print(f"[Error] No se pudo conectar a MySQL: {e}")
        return None

# Obtener el correo de un usuario por su ID
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



def listar_ordenes_pendientes():
    """
    Retorna todas las órdenes cuyo estado_pago = 'Pendiente', 
    con información del cliente y el total de cotización.
    """
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
      c.total AS total_cotizacion
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
@app.route("/cliente/cotizaciones_habilitadas")
def cotizaciones_habilitadas_cliente():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT c.id, c.longitud, c.ancho, c.profundidad, c.aggrebind, c.agua, c.total
          FROM cotizaciones c
         WHERE c.cliente_id = %s
           AND c.habilitado = TRUE
           AND NOT EXISTS (
               SELECT 1 FROM ordenes o WHERE o.cotizacion_id = c.id
           )
         ORDER BY c.id DESC
    """, (session['usuario_id'],))
    habilitadas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("cliente/cotizaciones_habilitadas.html", cotizaciones=habilitadas)


@app.route("/cliente/pagar/<int:cotizacion_id>", methods=["GET", "POST"])
def pagar_cotizacion(cotizacion_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    #— Obtener datos de la cotización habilitada
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
    cur.close()
    conn.close()

    if not cot:
        flash("Cotización no válida o no habilitada.", "danger")
        return redirect(url_for('cotizaciones_habilitadas_cliente'))

    if request.method == "POST":
        metodo        = request.form.get("metodo_pago")
        direccion     = request.form.get("direccion_envio", "").strip()
        ciudad        = request.form.get("ciudad", "").strip()
        codigo_postal = request.form.get("codigo_postal", "").strip()
        monto         = cot["total"]

        # Validaciones básicas
        if metodo not in ("PSE", "Tarjeta"):
            flash("Debes seleccionar un método de pago válido.", "warning")
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))

        if not direccion or not ciudad or not codigo_postal:
            flash("Debes completar todos los datos de dirección.", "warning")
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))

        # Si el usuario eligió "Tarjeta", leemos los campos adicionales:
        ultimos4 = None
        if metodo == "Tarjeta":
            numero_tarjeta = request.form.get("numero_tarjeta", "").strip()
            vencimiento    = request.form.get("vencimiento", "").strip()
            cvv            = request.form.get("cvv", "").strip()

            # Validación mínima: que sean no vacíos y tengan la longitud esperada
            if not numero_tarjeta or len(numero_tarjeta) != 16 or not numero_tarjeta.isdigit():
                flash("Número de tarjeta inválido.", "danger")
                return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))
            if not vencimiento or not cvv:
                flash("Completa todos los datos de tarjeta.", "danger")
                return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))

            # Tomamos solo los últimos 4 dígitos para mostrarlos
            ultimos4 = numero_tarjeta[-4:]
            detalle_pago = f"Tarjeta terminada en {ultimos4}"
        else:
            detalle_pago = "PSE (transferencia)"

        # Concatenar la dirección completa:
        dir_completa = f"{direccion}, {ciudad}, CP {codigo_postal}"

        # Crear la orden en BD (solo guardamos dirección, no tarjeta completa)
        nueva_orden_id = crear_orden(cot["id"], session["usuario_id"], monto, metodo, dir_completa)
        if not nueva_orden_id:
            flash("Error al generar la orden, intenta de nuevo.", "danger")
            return redirect(url_for('pagar_cotizacion', cotizacion_id=cotizacion_id))

        # Enviar correo de confirmación al cliente (igual que antes)
        asunto = "Confirmación de compra - Polímeros S.A."
        cuerpo = (
            f"¡Hola {session['nombre']}!\n\n"
            f"Tu compra (cotización #{cotizacion_id}) se ha realizado con éxito.\n"
            f"Monto pagado: ${monto:.2f}\n"
            f"Método de pago: {metodo} ({detalle_pago})\n"
            f"Dirección de envío: {dir_completa}\n\n"
            "Un administrador coordinará el envío del polímero a la brevedad.\n\n"
            "Puedes comunicarte con un administrador desde la pagina web si tienes alguna inquietud.\n\n"
            "Gracias por confiar en Polímeros S.A.\n"
        )
        msg = Message(
            subject=asunto,
            recipients=[ get_usuario_correo(session["usuario_id"]) ]
        )
        msg.body = cuerpo
        mail.send(msg)

        # ———————— AQUI devolvemos un template de confirmación en pantalla ————————
        return render_template(
            "cliente/confirmacion_pago.html",
            nombre_cliente=session["nombre"],
            cot_id=cotizacion_id,
            monto=monto,
            metodo=metodo,
            detalle_pago=detalle_pago,
            direccion=dir_completa
        )

    # Si es GET, mostramos el formulario de pago
    return render_template("cliente/pagar_cotizacion.html", cotizacion=cot)


# Ruta principal de reportes (opcional: página índice)
@app.route('/admin/reportes')
def reportes_index():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    return render_template('reportes/index.html')  # donde muestres tarjetas/clasificaciones

# Reporte de compras (órdenes aprobadas)
# Reporte de compras (órdenes)
@app.route('/admin/reportes/compras')
def reporte_compras():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    # Leer filtros de query string
    nombre = request.args.get('nombre', '').strip()
    desde = request.args.get('fecha_desde', '').strip()
    hasta = request.args.get('fecha_hasta', '').strip()
    monto_min = request.args.get('monto_min', '').strip()
    monto_max = request.args.get('monto_max', '').strip()

    filtros = []
    params = []

    if nombre:
        filtros.append("(u.nombre LIKE %s OR u.apellido LIKE %s)")
        params.extend([f"%{nombre}%", f"%{nombre}%"])

    if desde:
        filtros.append("o.fecha_creacion >= %s")
        params.append(desde)

    if hasta:
        # incluir todo el día
        filtros.append("o.fecha_creacion <= %s")
        params.append(f"{hasta} 23:59:59")

    if monto_min:
        filtros.append("o.monto >= %s")
        params.append(monto_min)

    if monto_max:
        filtros.append("o.monto <= %s")
        params.append(monto_max)

    consulta_base = """
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
        consulta_base += " WHERE " + " AND ".join(filtros)

    consulta_base += " ORDER BY o.fecha_creacion DESC"

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(consulta_base, params)
    compras = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('reportes/compras.html', compras=compras)



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


# ------------------------------
# RUTA: Agregar Vehículo (GET/POST)
# ------------------------------
@app.route("/vehiculos/nuevo", methods=["GET", "POST"])
def agregar_vehiculo_route():
    if request.method == "POST":
        tipo = request.form.get("tipo", "").strip()
        placa = request.form.get("placa", "").strip()
        capacidad = request.form.get("capacidad_litros", "").strip()

        if not tipo or not placa or not capacidad:
            flash("Debe completar todos los campos.", "warning")
            return redirect(url_for("agregar_vehiculo_route"))

        try:
            cap_int = int(capacidad)
            if cap_int <= 0:
                raise ValueError
        except ValueError:
            flash("La capacidad debe ser un número entero mayor que cero.", "danger")
            return redirect(url_for("agregar_vehiculo_route"))

        ok = agregar_vehiculo(tipo, placa, cap_int)
        if ok:
            flash(f"Vehículo '{tipo}' (placa {placa}) agregado correctamente.", "success")
            return redirect(url_for("listar_envios_route"))
        else:
            flash("Error al insertar el vehículo. Verifica la consola.", "danger")
            return redirect(url_for("agregar_vehiculo_route"))

    return render_template("gestion_envios/agregar_vehiculo.html")

# ------------------------------
# RUTA: Agregar Conductor (GET/POST)
# ------------------------------
@app.route("/conductores/nuevo", methods=["GET", "POST"])
def agregar_conductor_route():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        cedula = request.form.get("cedula", "").strip()
        telefono = request.form.get("telefono", "").strip()

        if not nombre or not cedula:
            flash("Nombre y cédula son obligatorios.", "warning")
            return redirect(url_for("agregar_conductor_route"))

        ok = agregar_conductor(nombre, cedula, telefono)
        if ok:
            flash(f"Conductor '{nombre}' agregado correctamente.", "success")
            return redirect(url_for("listar_envios_route"))
        else:
            flash("Error al insertar el conductor. Verifica la consola.", "danger")
            return redirect(url_for("agregar_conductor_route"))

    return render_template("gestion_envios/agregar_conductor.html")

# ------------------------------
# 2. FUNCIONES DE TABLAS (DDL)
#    (Usar solo si quieres crear tablas desde Python)
# ------------------------------
def crear_tablas():
    """
    Crea las tablas vehiculos, conductores y envios si no existen.
    Ejecuta esta función la primera vez o si necesitas que el propio
    script cree las tablas.
    """
    ddl_vehiculos = """
    CREATE TABLE IF NOT EXISTS vehiculos (
      id INT AUTO_INCREMENT PRIMARY KEY,
      tipo VARCHAR(50) NOT NULL,
      placa VARCHAR(20) NOT NULL UNIQUE,
      capacidad_litros INT NOT NULL,
      disponible TINYINT(1) NOT NULL DEFAULT 1,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    ddl_conductores = """
    CREATE TABLE IF NOT EXISTS conductores (
      id INT AUTO_INCREMENT PRIMARY KEY,
      nombre VARCHAR(100) NOT NULL,
      cedula VARCHAR(20) NOT NULL UNIQUE,
      telefono VARCHAR(20),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    ddl_envios = """
    CREATE TABLE IF NOT EXISTS envios (
      id INT AUTO_INCREMENT PRIMARY KEY,
      origen VARCHAR(200) NOT NULL,
      destino VARCHAR(200) NOT NULL,
      cantidad_litros INT NOT NULL,
      fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      vehiculo_id INT,
      conductor_id INT,
      estado ENUM('Pendiente','En ruta','Entregado','Cancelado')
             NOT NULL DEFAULT 'Pendiente',
      fecha_salida DATETIME NULL,
      fecha_entrega DATETIME NULL,
      FOREIGN KEY (vehiculo_id) REFERENCES vehiculos(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
      FOREIGN KEY (conductor_id) REFERENCES conductores(id)
        ON DELETE SET NULL ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute(ddl_vehiculos)
        cursor.execute(ddl_conductores)
        cursor.execute(ddl_envios)
        conn.commit()
        cursor.close()
        conn.close()
        print("Tablas creadas (o ya existían).")
    else:
        print("No se pudo crear las tablas. Verifica la conexión.")

# ------------------------------
# 3. UTILIDAD: CÁLCULO CARROTANQUES
# ------------------------------
def calcular_carrotanques(cantidad_total, capacidad_carrotanque):
    """
    Retorna el número mínimo de carrotanques de capacidad fija
    que hacen falta para transportar `cantidad_total` litros.
    """
    return math.ceil(cantidad_total / capacidad_carrotanque)

# ------------------------------
# 4. CRUD VEHÍCULOS
# ------------------------------
def agregar_vehiculo(tipo, placa, capacidad_litros):
    sql = """
    INSERT INTO vehiculos (tipo, placa, capacidad_litros)
    VALUES (%s, %s, %s)
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (tipo, placa, capacidad_litros))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error] al insertar vehículo: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def listar_vehiculos(disponibles_solo=False):
    """
    Retorna lista de vehículos. Si disponibles_solo=True, filtra por disponible=1.
    Cada fila sale como dict.
    """
    if disponibles_solo:
        sql = "SELECT id, tipo, placa, capacidad_litros, disponible FROM vehiculos WHERE disponible = 1"
    else:
        sql = "SELECT id, tipo, placa, capacidad_litros, disponible FROM vehiculos"
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return filas

# ------------------------------
# 5. CRUD CONDUCTORES
# ------------------------------
def agregar_conductor(nombre, cedula, telefono=None):
    sql = """
    INSERT INTO conductores (nombre, cedula, telefono)
    VALUES (%s, %s, %s)
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (nombre, cedula, telefono))
        conn.commit()
        return True
    except Error as e:
        print(f"[Error] al insertar conductor: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def listar_conductores():
    sql = "SELECT id, nombre, cedula, telefono FROM conductores"
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    filas = cursor.fetchall()
    cursor.close()
    conn.close()
    return filas

# ------------------------------
# 6. CRUD ENVÍOS
# ------------------------------
def crear_envio(origen, destino, cantidad_litros):
    """
    Inserta un nuevo envío con estado 'Pendiente'.
    Devuelve el nuevo ID o None si falla.
    """
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
        print(f"[Error] al crear envío: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def listar_envios():
    """
    Retorna lista de envíos con JOIN a vehículos y conductores.
    Cada fila es dict con campos:
      id, origen, destino, cantidad_litros, fecha_creacion, estado,
      vehiculo_placa, vehiculo_cap, conductor_nombre,
      fecha_salida, fecha_entrega
    """
    sql = """
    SELECT 
      e.id,
      e.origen,
      e.destino,
      e.cantidad_litros,
      e.fecha_creacion,
      e.estado,
      v.placa AS vehiculo_placa,
      v.capacidad_litros AS vehiculo_cap,
      c.nombre AS conductor_nombre,
      e.fecha_salida,
      e.fecha_entrega
    FROM envios e
    LEFT JOIN vehiculos v ON e.vehiculo_id = v.id
    LEFT JOIN conductores c ON e.conductor_id = c.id
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

def asignar_envio(envio_id, vehiculo_id, conductor_id):
    """
    Asigna un vehículo y conductor a un envío.
    Cambia estado a 'En ruta', pone fecha_salida = NOW() y marca vehículo como no disponible.
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor(dictionary=True)

        # 1) Obtener cantidad_litros del envío y capacidad del vehículo
        sql_info = """
        SELECT e.cantidad_litros AS cant, v.capacidad_litros AS cap
        FROM envios e
        JOIN vehiculos v ON v.id = %s
        WHERE e.id = %s
        """
        cursor.execute(sql_info, (vehiculo_id, envio_id))
        datos = cursor.fetchone()
        if not datos:
            print(f"[Error] No existe envío ID={envio_id} o vehículo ID={vehiculo_id}.")
            return False

        cantidad = datos["cant"]
        capacidad = datos["cap"]
        num_carrotanques = calcular_carrotanques(cantidad, capacidad)

        # Aviso si la capacidad es insuficiente
        if cantidad > capacidad:
            flash(
                f"¡Ojo! Vehículo seleccionado ({capacidad}L) no cubre los {cantidad}L del envío. "
                f"Hacen falta {num_carrotanques} carrotanques.",
                "warning"
            )

        # 2) Actualizar el envío
        sql_asignar = """
        UPDATE envios
        SET vehiculo_id = %s,
            conductor_id = %s,
            estado = 'En ruta',
            fecha_salida = NOW()
        WHERE id = %s
        """
        cursor.execute(sql_asignar, (vehiculo_id, conductor_id, envio_id))

        # 3) Marcar vehículo como no disponible
        sql_disp = "UPDATE vehiculos SET disponible = 0 WHERE id = %s"
        cursor.execute(sql_disp, (vehiculo_id,))

        conn.commit()
        return True

    except Error as e:
        print(f"[Error] al asignar envío: {e}")
        return False

    finally:
        cursor.close()
        conn.close()

def actualizar_estado_envio(envio_id, nuevo_estado):
    """
    Cambia el estado de un envío.
    Si es 'Entregado', fija fecha_entrega = NOW() y libera el vehículo.
    """
    if nuevo_estado not in ("Pendiente", "En ruta", "Entregado", "Cancelado"):
        flash("Estado inválido.", "danger")
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor(dictionary=True)

        vehiculo_id = None
        if nuevo_estado == "Entregado":
            cursor.execute("SELECT vehiculo_id FROM envios WHERE id = %s", (envio_id,))
            row = cursor.fetchone()
            if row:
                vehiculo_id = row["vehiculo_id"]

        if nuevo_estado == "Entregado":
            sql_upd = """
            UPDATE envios
            SET estado = %s,
                fecha_entrega = NOW()
            WHERE id = %s
            """
            cursor.execute(sql_upd, (nuevo_estado, envio_id))
        else:
            sql_upd = "UPDATE envios SET estado = %s WHERE id = %s"
            cursor.execute(sql_upd, (nuevo_estado, envio_id))

        if vehiculo_id:
            sql_liberar = "UPDATE vehiculos SET disponible = 1 WHERE id = %s"
            cursor.execute(sql_liberar, (vehiculo_id,))

        conn.commit()
        return True

    except Error as e:
        print(f"[Error] al actualizar estado: {e}")
        return False

    finally:
        cursor.close()
        conn.close()

# ------------------------------
# 7. RUTAS FLASK (Gestión de Envíos)
# ------------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/envios")
def listar_envios_route():
    envs = listar_envios()
    return render_template("gestion_envios/listar_envios.html", envios=envs)

@app.route("/envios/nuevo", methods=["GET", "POST"])
def crear_envio_route():
    if request.method == "POST":
        origen = request.form.get("origen", "").strip()
        destino = request.form.get("destino", "").strip()
        cantidad = request.form.get("cantidad_litros", "").strip()

        if not origen or not destino or not cantidad:
            flash("Todos los campos son obligatorios.", "warning")
            return redirect(url_for("crear_envio_route"))

        try:
            cantidad_int = int(cantidad)
            if cantidad_int <= 0:
                raise ValueError
        except ValueError:
            flash("Cantidad de litros no válida.", "danger")
            return redirect(url_for("crear_envio_route"))

        nuevo_id = crear_envio(origen, destino, cantidad_int)
        if nuevo_id:
            flash(f"Envío registrado (ID={nuevo_id}). Ahora asigna vehículo y conductor.", "success")
            return redirect(url_for("asignar_envio_route", envio_id=nuevo_id))
        else:
            flash("Error al crear envío. Revisa la consola.", "danger")
            return redirect(url_for("crear_envio_route"))

    return render_template("gestion_envios/crear_envio.html")

@app.route("/envios/<int:envio_id>/asignar", methods=["GET", "POST"])
def asignar_envio_route(envio_id):
    if request.method == "POST":
        vehiculo_id = request.form.get("vehiculo_id")
        conductor_id = request.form.get("conductor_id")

        if not vehiculo_id or not conductor_id:
            flash("Debes seleccionar vehículo y conductor.", "warning")
            return redirect(url_for("asignar_envio_route", envio_id=envio_id))

        success = asignar_envio(envio_id, int(vehiculo_id), int(conductor_id))
        if success:
            flash(f"Envío #{envio_id} puesto en ruta.", "success")
        else:
            flash("No se pudo asignar el envío. Revisa la consola.", "danger")

        return redirect(url_for("listar_envios_route"))

    vehiculos = listar_vehiculos(disponibles_solo=True)
    conductores = listar_conductores()
    envios = listar_envios()
    envio = next((e for e in envios if e["id"] == envio_id), None)
    if envio is None:
        flash(f"El envío ID={envio_id} no existe.", "danger")
        return redirect(url_for("listar_envios_route"))

    return render_template(
        "gestion_envios/asignar_envio.html",
        envio=envio,
        vehiculos=vehiculos,
        conductores=conductores
    )

@app.route("/envios/<int:envio_id>/actualizar_estado", methods=["POST"])
def actualizar_estado_route(envio_id):
    nuevo_estado = request.form.get("estado")
    if not nuevo_estado:
        flash("Debes escoger un estado.", "warning")
    else:
        success = actualizar_estado_envio(envio_id, nuevo_estado)
        if success:
            flash(f"Envío #{envio_id} actualizado a '{nuevo_estado}'.", "info")
        else:
            flash("Error al actualizar estado. Revisa la consola.", "danger")
    return redirect(url_for("listar_envios_route"))

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
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM usuarios WHERE correo=%s", (correo,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if usuario and check_password_hash(usuario['contrasena'], contrasena):
            session['usuario_id'] = usuario['id']
            session['nombre']     = usuario['nombre']
            session['rol']        = usuario['rol']
            if usuario['rol'] == 'admin':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('calculadora'))

        flash('Correo o contraseña incorrectos', 'danger')
        return redirect(url_for('login'))

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

@app.route('/cotizar', methods=['POST'])
def cotizar():
    #— 4.1. Validación de sesión
    if 'usuario_id' not in session:
        return jsonify(success=False, message="No estás autenticado"), 401

    #— 4.2. Leer dimensiones del form
    largo       = float(request.form['largo'])
    ancho       = float(request.form['ancho'])
    profundidad = float(request.form['profundidad'])

    #— 4.3. Cálculo de volúmenes
    volumen = largo * ancho * profundidad

    #— 4.4. Factores: litros necesarios
    POLY_FACTOR  = 4.0    # litros de polímero por m³
    WATER_FACTOR = 1.3    # litros de agua por m³

    aggrebind_necesario = POLY_FACTOR  * volumen   # litros de polímero
    agua_necesaria      = WATER_FACTOR * volumen   # litros de agua

    #— 4.5. Calcular el total en dinero
    PRECIO_POLIMERO_POR_LITRO = 15000  # coincide con tu JS
    total_en_dinero = aggrebind_necesario * PRECIO_POLIMERO_POR_LITRO

    #— 4.6. VALIDAR INVENTARIO DISPONIBLE
    if not validar_stock_disponible(aggrebind_necesario):
        inventario_actual = obtener_inventario_disponible()
        return jsonify(
            success=False, 
            message=f"Inventario insuficiente. Disponible: {inventario_actual:.2f}L, Requerido: {aggrebind_necesario:.2f}L"
        ), 400

    #— 4.7. Verificar cotización pendiente existente
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

    #— 4.8. Insertar en la base de datos: guardamos total_en_dinero
    cur.execute("""
        INSERT INTO cotizaciones 
          (cliente_id, longitud, ancho, profundidad, aggrebind, agua, total, habilitado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        session['usuario_id'],
        largo, ancho, profundidad,
        aggrebind_necesario,
        agua_necesaria,
        total_en_dinero,  # <-- aquí va el total en $ (no la suma de litros)
        False
    ))
    conn.commit()
    cur.close()
    conn.close()

    #— 4.9. Responder al cliente
    return jsonify(
        success=True,
        message=f"Cotización enviada: Total ${total_en_dinero:.2f}. Pendiente de aprobación."
    )


@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return render_template('calculadora.html', nombre=session['nombre'])

#-------- 5. GESTIÓN DE INVENTARIO (SOLO ADMIN) -----------------------------
@app.route('/admin/inventario')
def gestionar_inventario():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # Obtener historial completo
    cur.execute("SELECT * FROM inventario ORDER BY fecha DESC")
    historial = cur.fetchall()

    # Calcular total actualizado: entradas - salidas
    cur.execute("""
        SELECT 
            IFNULL(SUM(entrada_inventario), 0) AS total_entradas,
            IFNULL(SUM(salida_inventario), 0) AS total_salidas
        FROM inventario
    """)
    resultado = cur.fetchone()
    
    entradas = float(resultado['total_entradas']) if resultado['total_entradas'] is not None else 0.0
    salidas = float(resultado['total_salidas']) if resultado['total_salidas'] is not None else 0.0
    total = entradas - salidas

    cur.close()
    conn.close()

    return render_template('gestionar_inventario.html', historial=historial, total=total)

@app.route('/admin/agregar_inventario', methods=['POST'])
def agregar_inventario():
    """
    Agregar entrada de inventario (solo admin)
    """
    if session.get('rol') != 'admin':
        return jsonify(success=False, message="Acceso denegado"), 403
    
    try:
        cantidad = float(request.form['cantidad'])
        fecha = request.form['fecha']
        
        if cantidad <= 0:
            flash('La cantidad debe ser mayor a 0', 'danger')
            return redirect(url_for('gestionar_inventario'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO inventario (total_inventario, entrada_inventario, fecha, fecha_creacion, fecha_actualizacion)
            VALUES (%s, %s, %s, NOW(), NOW())
        """, (cantidad, cantidad, fecha))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'Inventario actualizado: +{cantidad}L agregados', 'success')
        return redirect(url_for('gestionar_inventario'))
        
    except ValueError:
        flash('Cantidad inválida', 'danger')
        return redirect(url_for('gestionar_inventario'))
    except Exception as e:
        flash('Error al agregar inventario', 'danger')
        return redirect(url_for('gestionar_inventario'))
    
@app.route('/admin/eliminar_inventario', methods=['POST'])
def eliminar_inventario():
    if session.get('rol') != 'admin':
        return jsonify(success=False, message="Acceso denegado"), 403

    try:
        cantidad = float(request.form['cantidad'])
        fecha = request.form['fecha']

        if cantidad <= 0:
            flash('La cantidad debe ser mayor a 0', 'danger')
            return redirect(url_for('gestionar_inventario'))

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        # Obtener inventario actual: entradas - salidas
        cur.execute("""
            SELECT COALESCE(SUM(entrada_inventario), 0) AS entradas,
                   COALESCE(SUM(salida_inventario), 0) AS salidas
            FROM inventario
        """)
        resultado = cur.fetchone()
        actual = float(resultado['entradas']) - float(resultado['salidas'])

        if cantidad > actual:
            flash('No hay suficiente inventario para eliminar esa cantidad', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('gestionar_inventario'))

        # Insertar la salida
        nuevo_total = actual - cantidad
        cur.execute("""
            INSERT INTO inventario (total_inventario, salida_inventario, fecha, fecha_creacion, fecha_actualizacion)
            VALUES (%s, %s, %s, NOW(), NOW())
        """, (nuevo_total, cantidad, fecha))

        conn.commit()
        cur.close()
        conn.close()

        flash(f'Se eliminaron {cantidad}L del inventario', 'success')
        return redirect(url_for('gestionar_inventario'))

    except Exception as e:
        print("Error:", e)  # Para depurar en consola
        flash('Error al eliminar inventario', 'danger')
        return redirect(url_for('gestionar_inventario'))

@app.route('/api/inventario/actual')
def api_inventario_actual():
    """
    API endpoint para obtener el inventario actual
    """
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
