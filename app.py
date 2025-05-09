from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from flask_mail import Mail, Message
import random
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'clave_secreta_segura'

# Función para obtener conexión
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='1234',
        database='polimero_db'
    )

# Configuración de Flask-Mail
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='pipecifuentes204@gmail.com',
    MAIL_PASSWORD='cinlwepiphhrmpaz',
    MAIL_DEFAULT_SENDER='pipecifuentes204@gmail.com'
)
mail = Mail(app)

@app.route('/')
def home():
    return redirect(url_for('login'))

# ====================== LOGIN ==========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()
        if usuario and check_password_hash(usuario['contrasena'], contrasena):
            session['usuario_id'] = usuario['id']
            session['nombre'] = usuario['nombre']
            session['rol'] = usuario['rol']
            return redirect(url_for('calculadora'))
        flash('Correo o contraseña incorrectos', 'error')
    return render_template('login.html')

# ====================== REGISTRO ========================
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip().capitalize()
        apellido = request.form['apellido'].strip().capitalize()
        correo = request.form['correo'].strip()
        contrasena = request.form['contrasena']
        if len(contrasena) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'error')
            return redirect(url_for('registro'))
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        if cur.fetchone():
            flash('El correo ya está registrado.', 'error')
            cur.close(); conn.close()
            return redirect(url_for('registro'))
        contrasena_hash = generate_password_hash(contrasena)
        rol = 'cliente'
        cur.execute(
            "INSERT INTO usuarios (nombre, apellido, correo, contrasena, rol) VALUES (%s,%s,%s,%s,%s)",
            (nombre, apellido, correo, contrasena_hash, rol)
        )
        conn.commit()
        cur.close(); conn.close()
        flash('Usuario registrado con éxito', 'mensaje')
        return redirect(url_for('login'))
    return render_template('registro.html')

# ====================== CALCULADORA =====================
@app.route('/calculadora')
def calculadora():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return render_template('calculadora.html')

# ====================== COTIZACIÓN ======================
@app.route('/cotizar', methods=['POST'])
def cotizar():
    if 'usuario_id' not in session:
        return jsonify(success=False, message="No estás autenticado.")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    # Verificar cotización pendiente
    cur.execute(
        "SELECT * FROM cotizaciones WHERE cliente_id=%s AND habilitado=FALSE",
        (session['usuario_id'],)
    )
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify(success=False, message="Ya tienes una cotización pendiente.")
    # Datos calculados
    datos = {k: float(request.form[k]) for k in ('largo','ancho','profundidad','aggrebind','agua','total')}
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cotizaciones
          (cliente_id,longitud,ancho,profundidad,aggrebind,agua,total,habilitado)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        session['usuario_id'],
        datos['largo'], datos['ancho'], datos['profundidad'],
        datos['aggrebind'], datos['agua'], datos['total'],
        False
    ))
    conn.commit()
    cur.close(); conn.close()
    return jsonify(success=True, message="Cotización enviada con éxito al administrador.")

# ================= NOTIFICACIONES ======================
# app.py (fragmento)

# … rutas anteriores …

# ---------------- NOTIFICACIONES ----------------
@app.route('/notificaciones')
def notificaciones():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión primero.', 'error')
        return redirect(url_for('login'))

    conexion = get_db_connection()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("""
        SELECT mensaje, fecha
        FROM notificaciones
        WHERE usuario_id = %s
        ORDER BY fecha DESC
    """, (session['usuario_id'],))
    notis = cursor.fetchall()
    cursor.close()
    conexion.close()

    return render_template('notificaciones.html', notificaciones=notis)

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
    if session.get('rol') != 'administrador':
        flash('Acceso denegado', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT c.*,u.nombre,u.apellido
          FROM cotizaciones c
          JOIN usuarios u ON c.cliente_id=u.id
      ORDER BY c.id DESC
    """)
    all_cots = cur.fetchall()
    cur.close(); conn.close()
    return render_template('ver_cotizaciones.html', cotizaciones=all_cots)

# ============ ADMIN: HABILITAR =======================
@app.route('/habilitar_cotizacion/<int:id>')
def habilitar_cotizacion(id):
    if session.get('rol') != 'administrador':
        flash('Acceso denegado', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE cotizaciones SET habilitado=TRUE WHERE id=%s", (id,))
    conn.commit()
    cur.close(); conn.close()
    flash('Cotización habilitada correctamente', 'mensaje')
    return redirect(url_for('ver_cotizaciones'))

# ====================== LOGOUT ==========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ========= RECUPERAR / CAMBIAR CONTRASEÑA =============
@app.route('/recuperar_contrasena', methods=['GET','POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        correo = request.form['correo']
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT correo FROM usuarios WHERE correo=%s", (correo,))
        if cur.fetchone():
            codigo = random.randint(100000,999999)
            msg = Message("Recuperación", recipients=[correo])
            msg.body = f"Tu código: {codigo}"
            mail.send(msg)
            cur.execute("UPDATE usuarios SET codigo_recuperacion=%s WHERE correo=%s", (codigo,correo))
            conn.commit()
            cur.close(); conn.close()
            session['correo_recuperacion']=correo
            flash('Código enviado.', 'mensaje')
            return redirect(url_for('verificar_codigo'))
        flash('Correo no registrado.', 'error')
        cur.close(); conn.close()
    return render_template('recuperar_contrasena.html')

@app.route('/verificar_codigo', methods=['GET','POST'])
def verificar_codigo():
    if request.method=='POST':
        correo = request.form['correo']
        codigo = request.form['codigo']
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM usuarios WHERE correo=%s AND codigo_recuperacion=%s", (correo,codigo))
        if cur.fetchone():
            cur.close(); conn.close()
            return redirect(url_for('cambiar_contrasena', correo=correo))
        flash('Código incorrecto','error')
        cur.close(); conn.close()
    return render_template('verificar_codigo.html')

@app.route('/cambiar_contrasena/<correo>', methods=['GET','POST'])
def cambiar_contrasena(correo):
    if request.method=='POST':
        nueva = request.form['nueva_contrasena']
        if len(nueva)<6:
            flash('Debe tener 6+ carácteres.','error')
            return redirect(request.url)
        hashp = generate_password_hash(nueva)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET contrasena=%s WHERE correo=%s", (hashp, correo))
        conn.commit()
        cur.close(); conn.close()
        flash('Contraseña cambiada.','mensaje')
        return redirect(url_for('login'))
    return render_template('cambiar_contrasena.html')

if __name__ == '__main__':
    app.run(debug=True)
