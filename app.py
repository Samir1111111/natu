from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import DictCursor
import os
from datetime import datetime

app = FastAPI()

DATABASE_URL = "postgresql://postgres:[YOUR-PASSWORD]@db.wxgqlovvyqjbgahxdyil.supabase.co:5432/postgres"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

templates = Jinja2Templates(directory="templates")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Tabla de productos actualizada con stock y tipo de venta
    cur.execute("""
        CREATE TABLE IF NOT EXISTS productos(
            id SERIAL PRIMARY KEY, 
            nombre TEXT UNIQUE, 
            precio_base REAL, 
            stock_actual REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 1,
            es_unidad BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS ventas(id SERIAL PRIMARY KEY, fecha TEXT, total REAL)")
    cur.execute("CREATE TABLE IF NOT EXISTS detalle_venta(id SERIAL PRIMARY KEY, venta_id INTEGER, producto TEXT, cantidad REAL, precio REAL)")
    conn.commit()
    cur.close()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
    productos = cur.fetchall()
    cur.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": productos})

@app.post("/agregar_producto_catalogo")
def agregar_catalogo(nombre: str = Form(...), precio: float = Form(...), stock: float = Form(...), stock_min: float = Form(...), es_unidad: bool = Form(False)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO productos (nombre, precio_base, stock_actual, stock_minimo, es_unidad) 
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (nombre) DO UPDATE SET 
            precio_base = EXCLUDED.precio_base,
            stock_actual = EXCLUDED.stock_actual,
            stock_minimo = EXCLUDED.stock_minimo,
            es_unidad = EXCLUDED.es_unidad
    """, (nombre, precio, stock, stock_min, es_unidad))
    conn.commit()
    cur.close()
    conn.close()
    return {"mensaje": "OK"}

@app.post("/reponer_stock")
def reponer_stock(producto_id: int = Form(...), cantidad: float = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE productos SET stock_actual = stock_actual + %s WHERE id = %s", (cantidad, producto_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"mensaje": "Stock actualizado"}

@app.get("/nueva_venta")
def nueva_venta():
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO ventas(fecha, total) VALUES(%s, %s) RETURNING id", (fecha, 0))
    venta_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"venta_id": venta_id}

@app.post("/agregar_producto")
def agregar_producto(venta_id: int = Form(...), producto: str = Form(...), cantidad: float = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, precio_base, es_unidad, stock_actual FROM productos WHERE nombre=%s", (producto,))
    res = cur.fetchone()
    if res:
        p_id, precio_base, es_unidad, stock_actual = res
        # Cálculo de precio: si es unidad es directo, si es peso es precio_base/1000 * cantidad
        total_prod = precio_base * cantidad if es_unidad else (precio_base / 1000) * cantidad
        
        # Descontar stock
        cur.execute("UPDATE productos SET stock_actual = stock_actual - %s WHERE id = %s", (cantidad, p_id))
        cur.execute("INSERT INTO detalle_venta(venta_id, producto, cantidad, precio) VALUES(%s,%s,%s,%s)",
                   (venta_id, producto, cantidad, total_prod))
        conn.commit()
        cur.close()
        conn.close()
        return {"subtotal": total_prod}
    return {"error": "No encontrado"}

@app.post("/finalizar_venta")
def finalizar_venta(venta_id: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT SUM(precio) FROM detalle_venta WHERE venta_id=%s", (venta_id,))
    total = cur.fetchone()[0] or 0
    cur.execute("UPDATE ventas SET total=%s WHERE id=%s", (total, venta_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"total": total}

@app.get("/ventas")
def ver_ventas():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT v.id, v.fecha, 
        string_agg(d.producto || ' (' || d.cantidad || ')', ' + ') as detalle, 
        v.total FROM ventas v
        LEFT JOIN detalle_venta d ON v.id = d.venta_id
        GROUP BY v.id, v.fecha, v.total ORDER BY v.id DESC LIMIT 20
    """)
    ventas = cur.fetchall()
    cur.close()
    conn.close()
    return {"ventas": ventas}

@app.get("/ticket/{venta_id}")
def obtener_ticket(venta_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, fecha, total FROM ventas WHERE id=%s", (venta_id,))
    venta = cur.fetchone()
    cur.execute("SELECT producto, cantidad, precio FROM detalle_venta WHERE venta_id=%s", (venta_id,))
    detalles = cur.fetchall()
    cur.close()
    conn.close()
    return {"venta": venta, "detalles": detalles}
