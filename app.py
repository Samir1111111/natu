import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    # Añadimos sslmode para seguridad y eliminamos parámetros extra
    return psycopg2.connect(DATABASE_URL, sslmode='require', cursor_factory=RealDictCursor)

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM productos ORDER BY nombre ASC')
        productos = cur.fetchall()
        cur.execute('SELECT v.*, p.nombre FROM ventas v JOIN productos p ON v.producto_id = p.id ORDER BY v.fecha DESC LIMIT 10')
        ventas = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('index.html', productos=productos, ventas=ventas)
    except Exception as e:
        return f"Error de conexión: {str(e)}"

@app.route('/agregar_producto', methods=['POST'])
def agregar_producto():
    nombre = request.form['nombre']
    precio = float(request.form['precio'])
    stock = float(request.form['stock'])
    es_unidad = request.form.get('es_unidad') == 'true'
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO productos (nombre, precio_unitario, stock_actual, es_unidad) VALUES (%s, %s, %s, %s)',
                (nombre, precio, stock, es_unidad))
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
    cur.execute('SELECT * FROM productos WHERE id = %s', (producto_id,))
    producto = cur.fetchone()
    
    if producto and producto['stock_actual'] >= cantidad:
        subtotal = float(producto['precio_unitario']) * cantidad
        cur.execute('INSERT INTO ventas (producto_id, cantidad, subtotal) VALUES (%s, %s, %s)',
                    (producto_id, cantidad, subtotal))
        cur.execute('UPDATE productos SET stock_actual = stock_actual - %s WHERE id = %s',
                    (cantidad, producto_id))
        conn.commit()
    
    cur.close()
    conn.close()
    return redirect(url_for('index'))
