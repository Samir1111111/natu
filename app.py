from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

app = FastAPI()

DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:Samirphite2006@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Agregamos 'es_unidad' para distinguir productos pesables de fijos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY,
        nombre TEXT UNIQUE,
        p_100 REAL, p_250 REAL, p_500 REAL, p_1000 REAL,
        es_unidad BOOLEAN DEFAULT FALSE,
        stock_gramos INTEGER DEFAULT 0
    );
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS ventas (id SERIAL PRIMARY KEY, fecha TIMESTAMP DEFAULT NOW(), total REAL DEFAULT 0);")
    cur.execute("CREATE TABLE IF NOT EXISTS detalle_venta (id SERIAL PRIMARY KEY, venta_id INTEGER, producto TEXT, cantidad INTEGER, subtotal REAL);")
    conn.commit()
    cur.close()
    conn.close()

init_db()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY nombre")
    prods = cur.fetchall()
    cur.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": prods})

@app.post("/add_producto_catalogo")
def add_catalogo(nombre: str = Form(...), p100: float = Form(...), p250: float = Form(...), p500: float = Form(...), p1000: float = Form(...), unidad: bool = Form(False)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO productos (nombre, p_100, p_250, p_500, p_1000, es_unidad) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (nombre) DO UPDATE SET p_100=EXCLUDED.p_100, p_250=EXCLUDED.p_250, p_500=EXCLUDED.p_500, p_1000=EXCLUDED.p_1000", (nombre, p100, p250, p500, p1000, unidad))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.post("/venta_rapida")
def venta_rapida(producto: str = Form(...), cantidad: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    # 1. Buscar precio y stock
    cur.execute("SELECT * FROM productos WHERE nombre=%s", (producto,))
    p = cur.fetchone()
    
    if p['stock_gramos'] < cantidad: return {"error": "Sin stock"}
    
    # 2. Calcular precio según escala
    if p['es_unidad']: precio = p['p_1000'] * cantidad
    else:
        if cantidad <= 100: precio = p['p_100']
        elif cantidad <= 250: precio = p['p_250']
        elif cantidad <= 500: precio = p['p_500']
        else: precio = p['p_1000']

    # 3. Registrar Venta
    cur.execute("INSERT INTO ventas (total) VALUES (%s) RETURNING id", (precio,))
    vid = cur.fetchone()['id']
    cur.execute("INSERT INTO detalle_venta (venta_id, producto, cantidad, subtotal) VALUES (%s,%s,%s,%s)", (vid, producto, cantidad, precio))
    cur.execute("UPDATE productos SET stock_gramos = stock_gramos - %s WHERE nombre = %s", (cantidad, producto))
    
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.get("/historial")
def historial():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT v.id, v.fecha, v.total, d.producto, d.cantidad 
        FROM ventas v JOIN detalle_venta d ON v.id = d.venta_id 
        ORDER BY v.fecha DESC LIMIT 50
    """)
    res = cur.fetchall()
    cur.close()
    conn.close()
    return {"historial": res}

@app.post("/borrar_venta")
def borrar(id: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    # Devolver stock antes de borrar
    cur.execute("SELECT producto, cantidad FROM detalle_venta WHERE venta_id=%s", (id,))
    det = cur.fetchone()
    if det:
        cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre=%s", (det['cantidad'], det['producto']))
    cur.execute("DELETE FROM ventas WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.get("/stats")
def stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT SUM(total) as hoy FROM ventas WHERE DATE(fecha) = CURRENT_DATE")
    hoy = cur.fetchone()['hoy'] or 0
    cur.execute("SELECT COUNT(*) as cant FROM ventas WHERE DATE(fecha) = CURRENT_DATE")
    cant = cur.fetchone()['cant'] or 0
    cur.close()
    conn.close()
    return {"hoy": hoy, "ventas_n": cant}
