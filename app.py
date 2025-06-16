import os
import random
import math
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
import mysql.connector
from mysql.connector import Error
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

# 1) Carga variables de tu .env en local (en Render, las lee del entorno)
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'clave_secreta_segura')  # también puedes llevarla a .env

# 2) Función para obtener conexión usando vars de entorno
def get_db_connection():
    """
    Conexión a MySQL usando variables de entorno.
    """
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 3306)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        print(f"✅ Conectado a base: {os.getenv('DB_NAME')}")
        return conn
    except Error as e:
        print(f"[Error] No se pudo conectar a MySQL: {e}")
        return None

# Configuración de Flask-Mail
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_USERNAME')
)
mail = Mail(app)

#-------- 2. Funciones de Inventario ---------------------------------------
def obtener_inventario_disponible():
    conn = get_db_connection()
    if not conn:
        return 0.0
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT SUM(entrada_inventario) AS total_entradas,"
        " SUM(salida_inventario) AS total_salidas FROM inventario"
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    entradas = float(result['total_entradas'] or 0)
    salidas = float(result['total_salidas'] or 0)
    return entradas - salidas

def validar_stock_disponible(cantidad_requerida):
    stock_actual = obtener_inventario_disponible()
    return stock_actual >= cantidad_requerida

def reducir_inventario(cantidad_utilizada):
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO inventario
          (total_inventario, salida_inventario, fecha, fecha_creacion, fecha_actualizacion)
        VALUES (%s, %s, %s, NOW(), NOW())
        """, (
            -cantidad_utilizada,
            cantidad_utilizada,
            datetime.now().date()
        )
    )
    conn.commit()
    cur.close()
    conn.close()

#-------- 3. Rutas de Autenticación ----------------------------------------
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
        nombre     = request.form['nombre'].strip().capitalize()
        apellido   = request.form['apellido'].strip().capitalize()
        correo     = request.form['correo'].strip()
        contrasena = request.form['contrasena']

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

        hashp = generate_password_hash(contrasena)
        cur.execute(
            "INSERT INTO usuarios (nombre,apellido,correo,contrasena,rol) VALUES (%s,%s,%s,%s,%s)",
            (nombre, apellido, correo, hashp, 'cliente')
        )
        conn.commit()
        cur.close()
        conn.close()

        flash('Usuario registrado con éxito', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')

#-------- 4. Calculadora & Cotización --------------------------------------
@app.route('/calculadora')
def calculadora():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    inventario_disponible = obtener_inventario_disponible()
    return render_template('calculadora.html', inventario_disponible=inventario_disponible)

@app.route('/cotizar', methods=['POST'])
def cotizar():
    if 'usuario_id' not in session:
        return jsonify(success=False, message="No estás autenticado"), 401

    largo       = float(request.form['largo'])
    ancho       = float(request.form['ancho'])
    profundidad = float(request.form['profundidad'])
    volumen     = largo * ancho * profundidad

    aggrebind_necesario = math.ceil(4.0 * volumen)
    agua_necesaria      = math.ceil(1.3 * volumen)
    total_en_dinero     = aggrebind_necesario * 15000

    if not validar_stock_disponible(aggrebind_necesario):
        disponible = obtener_inventario_disponible()
        return jsonify(
            success=False,
            message=f"Inventario insuficiente. Disponible: {disponible:.2f}L, Requerido: {aggrebind_necesario}L"
        ), 400

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

    cur.execute(
        "INSERT INTO cotizaciones (cliente_id,longitud,ancho,profundidad,aggrebind,agua,total,habilitado)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (session['usuario_id'], largo, ancho, profundidad, aggrebind_necesario, agua_necesaria, total_en_dinero, False)
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify(success=True, message=f"Cotización enviada: Total ${total_en_dinero:.2f}. Pendiente de aprobación.")

#-------- 5. Notificaciones & Dashboard ------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT mensaje, fecha FROM notificaciones WHERE usuario_id=%s ORDER BY fecha DESC",
        (session['usuario_id'],)
    )
    notis = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('notificaciones.html', notificaciones=notis)


# =========== COTIZACIONES PENDIENTES ===============
@app.route('/ver_cotizaciones_pendientes')
def ver_cotizaciones_pendientes():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión primero.', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id,longitud,ancho,profundidad,total
          FROM cotizaciones
         WHERE cliente_id=%s AND habilitado=FALSE
         ORDER BY id DESC
    """, (session['usuario_id'],))
    cotizaciones = cur.fetchall()
    cur.close(); conn.close()
    return render_template('ver_cotizaciones_pendientes.html', cotizaciones=cotizaciones)

# ====================== ADMIN: VER ======================
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



# ========= RECUPERAR / CAMBIAR CONTRASEÑA =============
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