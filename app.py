import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# Configuración de la base de datos
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    # Usamos RealDictCursor para que los resultados sean como diccionarios
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Crear tablas si no existen (Sintaxis PostgreSQL)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio_unitario REAL NOT NULL,
            stock_actual REAL DEFAULT 0,
            es_unidad BOOLEAN DEFAULT TRUE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id SERIAL PRIMARY KEY,
            producto_id INTEGER REFERENCES productos(id),
            cantidad REAL NOT NULL,
            subtotal REAL NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM productos ORDER BY nombre ASC')
    productos = cur.fetchall()
    cur.execute('''
        SELECT v.*, p.nombre 
        FROM ventas v 
        JOIN productos p ON v.producto_id = p.id 
        ORDER BY v.fecha DESC
    ''')
    ventas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', productos=productos, ventas=ventas)

@app.route('/agregar_producto', methods=['POST'])
def agregar_producto():
    nombre = request.form['nombre']
    precio = float(request.form['precio'])
    stock = float(request.form['stock'])
    es_unidad = request.form.get('es_unidad') == 'true'
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO productos (nombre, precio_unitario, stock_actual, es_unidad)
        VALUES (%s, %s, %s, %s)
    ''', (nombre, precio, stock, es_unidad))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/venta', methods=['POST'])
def venta():
    producto_id = int(request.form['producto_id'])
    cantidad = float(request.form['cantidad'])
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Obtener info del producto
    cur.execute('SELECT * FROM productos WHERE id = %s', (producto_id,))
    producto = cur.fetchone()
    
    if producto and producto['stock_actual'] >= cantidad:
        subtotal = producto['precio_unitario'] * cantidad
        # Registrar venta
        cur.execute('''
            INSERT INTO ventas (producto_id, cantidad, subtotal)
            VALUES (%s, %s, %s)
        ''', (producto_id, cantidad, subtotal))
        # Descontar stock
        cur.execute('''
            UPDATE productos SET stock_actual = stock_actual - %s WHERE id = %s
        ''', (cantidad, producto_id))
        conn.commit()
    
    cur.close()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
