from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Cotizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    correo = db.Column(db.String(100))
    largo = db.Column(db.Float)
    ancho = db.Column(db.Float)
    profundidad = db.Column(db.Float)
    polimero = db.Column(db.Float)
