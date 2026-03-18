from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = FastAPI()

# URL de conexión (asegúrate de que la contraseña sea correcta)
DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:Samirphite2006@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
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
    cur.execute("CREATE TABLE IF NOT EXISTS detalle_venta (id SERIAL PRIMARY KEY, venta_id INTEGER REFERENCES ventas(id) ON DELETE CASCADE, producto TEXT, cantidad INTEGER, subtotal REAL);")
    conn.commit()
    cur.close()
    conn.close()

init_db()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
    prods = cur.fetchall()
    cur.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": prods})

@app.post("/add_producto_catalogo")
def add_catalogo(nombre: str = Form(...), p100: float = Form(...), p250: float = Form(...), p500: float = Form(...), p1000: float = Form(...), unidad: bool = Form(False)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO productos (nombre, p_100, p_250, p_500, p_1000, es_unidad) 
        VALUES (%s,%s,%s,%s,%s,%s) 
        ON CONFLICT (nombre) DO UPDATE SET p_100=EXCLUDED.p_100, p_250=EXCLUDED.p_250, p_500=EXCLUDED.p_500, p_1000=EXCLUDED.p_1000, es_unidad=EXCLUDED.es_unidad
    """, (nombre, p100, p250, p500, p1000, unidad))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.post("/venta_rapida")
def venta_rapida(producto: str = Form(...), cantidad: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos WHERE nombre=%s", (producto,))
    p = cur.fetchone()
    
    if not p: return JSONResponse({"error": "No existe el producto"}, status_code=404)
    if p['stock_gramos'] < cantidad: return JSONResponse({"error": f"Stock insuficiente ({p['stock_gramos']} disp.)"}, status_code=400)
    
    # Lógica de precios
    if p['es_unidad']: 
        precio = p['p_1000'] * cantidad
    else:
        if cantidad <= 100: precio = p['p_100']
        elif cantidad <= 250: precio = p['p_250']
        elif cantidad <= 500: precio = p['p_500']
        else: precio = p['p_1000']

    cur.execute("INSERT INTO ventas (total) VALUES (%s) RETURNING id", (precio,))
    vid = cur.fetchone()['id']
    cur.execute("INSERT INTO detalle_venta (venta_id, producto, cantidad, subtotal) VALUES (%s,%s,%s,%s)", (vid, producto, cantidad, precio))
    cur.execute("UPDATE productos SET stock_gramos = stock_gramos - %s WHERE nombre = %s", (cantidad, producto))
    
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.post("/reponer_stock")
def reponer(producto: str = Form(...), cantidad: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre = %s", (cantidad, producto))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.get("/dashboard_data")
def dashboard_data():
    conn = get_db_connection()
    cur = conn.cursor()
    # Ventas hoy
    cur.execute("SELECT COALESCE(SUM(total),0) as hoy, COUNT(*) as n FROM ventas WHERE DATE(fecha) = CURRENT_DATE")
    stats = cur.fetchone()
    # Producto estrella
    cur.execute("SELECT producto, COUNT(*) as veces FROM detalle_venta GROUP BY producto ORDER BY veces DESC LIMIT 1")
    top = cur.fetchone()
    # Alerta Stock bajo (< 500g/unidades)
    cur.execute("SELECT nombre, stock_gramos FROM productos WHERE stock_gramos < 500")
    bajos = cur.fetchall()
    
    cur.close()
    conn.close()
    return {
        "hoy": stats['hoy'], 
        "ventas_n": stats['n'], 
        "top_prod": top['producto'] if top else "N/A",
        "bajos": bajos
    }

@app.get("/historial")
def historial():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT v.id, v.fecha, v.total, d.producto, d.cantidad 
        FROM ventas v JOIN detalle_venta d ON v.id = d.venta_id 
        ORDER BY v.fecha DESC LIMIT 20
    """)
    res = cur.fetchall()
    cur.close()
    conn.close()
    return {"historial": res}

@app.post("/borrar_venta")
def borrar(id: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT producto, cantidad FROM detalle_venta WHERE venta_id=%s", (id,))
    det = cur.fetchone()
    if det:
        cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre=%s", (det['cantidad'], det['producto']))
    cur.execute("DELETE FROM ventas WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}
