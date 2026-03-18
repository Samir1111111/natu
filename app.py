from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor
import json

app = FastAPI()
DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:Samirphite2006@aws-1-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- INICIALIZACIÓN ---
@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE,
            p_100 REAL, p_250 REAL, p_500 REAL, p_1000 REAL,
            es_unitario BOOLEAN DEFAULT FALSE,
            stock INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id SERIAL PRIMARY KEY,
            fecha TIMESTAMP DEFAULT NOW(),
            total REAL
        );
        CREATE TABLE IF NOT EXISTS detalle_ventas (
            id SERIAL PRIMARY KEY,
            venta_id INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
            producto TEXT,
            cantidad INTEGER,
            subtotal REAL
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

templates = Jinja2Templates(directory="templates")

# --- RUTAS ---

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
    prods = cur.fetchall()
    cur.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": prods})

@app.post("/catalogo")
def guardar_catalogo(nombre: str = Form(...), p100: float = Form(...), p250: float = Form(...), p500: float = Form(...), p1000: float = Form(...), unidad: str = Form("false")):
    is_uni = unidad.lower() == "true"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO productos (nombre, p_100, p_250, p_500, p_1000, es_unitario)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (nombre) DO UPDATE SET 
        p_100=EXCLUDED.p_100, p_250=EXCLUDED.p_250, p_500=EXCLUDED.p_500, p_1000=EXCLUDED.p_1000, es_unitario=EXCLUDED.es_unitario
    """, (nombre, p100, p250, p500, p1000, is_uni))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/reponer")
def reponer_stock(producto: str = Form(...), cantidad: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE productos SET stock = stock + %s WHERE nombre = %s", (cantidad, producto))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/venta")
def procesar_venta(carrito: str = Form(...)):
    data = json.loads(carrito)
    conn = get_db_connection()
    cur = conn.cursor()
    total_venta = 0
    try:
        cur.execute("INSERT INTO ventas (total) VALUES (0) RETURNING id")
        v_id = cur.fetchone()['id']
        
        for item in data:
            cur.execute("SELECT * FROM productos WHERE nombre = %s", (item['nombre'],))
            p = cur.fetchone()
            cant = int(item['cantidad'])
            
            # Lógica de precio escalonado
            if p['es_unitario']: sub = p['p_1000'] * cant
            elif cant <= 100: sub = p['p_100']
            elif cant <= 250: sub = p['p_250']
            elif cant <= 500: sub = p['p_500']
            else: sub = p['p_1000']
            
            total_venta += sub
            cur.execute("INSERT INTO detalle_ventas (venta_id, producto, cantidad, subtotal) VALUES (%s,%s,%s,%s)", (v_id, p['nombre'], cant, sub))
            cur.execute("UPDATE productos SET stock = stock - %s WHERE nombre = %s", (cant, p['nombre']))
            
        cur.execute("UPDATE ventas SET total = %s WHERE id = %s", (total_venta, v_id))
        conn.commit()
        return {"id": v_id}
    finally:
        conn.close()

@app.get("/historial")
def ver_historial():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT v.id, v.fecha, v.total, 
        string_agg(d.producto || ' (' || d.cantidad || ')', ', ') as items
        FROM ventas v 
        LEFT JOIN detalle_ventas d ON v.id = d.venta_id
        GROUP BY v.id ORDER BY v.fecha DESC LIMIT 50
    """)
    res = cur.fetchall()
    conn.close()
    return res

@app.post("/borrar_venta")
def borrar_venta(id: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    # Devolver stock
    cur.execute("SELECT producto, cantidad FROM detalle_ventas WHERE venta_id = %s", (id,))
    detalles = cur.fetchall()
    for d in detalles:
        cur.execute("UPDATE productos SET stock = stock + %s WHERE nombre = %s", (d['cantidad'], d['producto']))
    cur.execute("DELETE FROM ventas WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}
