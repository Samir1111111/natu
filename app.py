from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json # Importante para procesar el carrito

app = FastAPI()

# URL CON PUERTO 6543 (Modo Transacción para evitar bloqueo de conexiones)
DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:Samirphite2006@aws-1-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                nombre TEXT UNIQUE,
                p_100 REAL, p_250 REAL, p_500 REAL, p_1000 REAL,
                es_unitario BOOLEAN DEFAULT FALSE,
                stock_gramos INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ventas (
                id SERIAL PRIMARY KEY, 
                fecha TIMESTAMP DEFAULT NOW(), 
                total REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS detalle_venta (
                id SERIAL PRIMARY KEY, 
                venta_id INTEGER REFERENCES ventas(id) ON DELETE CASCADE, 
                producto TEXT, 
                cantidad INTEGER, 
                subtotal REAL
            );
        """)
        conn.commit()
        print("✅ Tablas verificadas correctamente.")
    except Exception as e:
        print(f"❌ Error inicializando DB: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

init_db()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
        prods = cur.fetchall()
        return templates.TemplateResponse("index.html", {"request": request, "productos": prods})
    finally:
        if conn:
            cur.close()
            conn.close()

@app.get("/dashboard_data")
def dashboard_data():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(total),0) as hoy, COUNT(*) as n FROM ventas WHERE DATE(fecha) = CURRENT_DATE")
        stats = cur.fetchone()
        cur.execute("SELECT COALESCE(SUM(total),0) as mes FROM ventas WHERE date_trunc('month', fecha) = date_trunc('month', CURRENT_DATE)")
        mes = cur.fetchone()['mes']
        cur.execute("SELECT producto, COUNT(*) as veces FROM detalle_venta GROUP BY producto ORDER BY veces DESC LIMIT 1")
        top = cur.fetchone()
        cur.execute("SELECT nombre FROM productos WHERE stock_gramos < 500")
        bajos = cur.fetchall()
        return {
            "hoy": round(stats['hoy'], 2), 
            "mes": round(mes, 2),
            "ventas_n": stats['n'], 
            "top_prod": top['producto'] if top else "N/A",
            "bajos": bajos
        }
    finally:
        if conn:
            cur.close()
            conn.close()

@app.get("/chart_data")
def chart_data():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT TO_CHAR(fecha, 'DD/MM') as dia, SUM(total) as suma 
            FROM ventas 
            WHERE fecha > CURRENT_DATE - INTERVAL '7 days'
            GROUP BY dia ORDER BY MIN(fecha) ASC
        """)
        return cur.fetchall()
    finally:
        if conn:
            cur.close()
            conn.close()

@app.post("/venta_rapida")
def venta_rapida(producto: str = Form(...), cantidad: int = Form(...)):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM productos WHERE nombre=%s", (producto,))
        p = cur.fetchone()
        if not p: return JSONResponse({"error": "Producto no existe"}, status_code=404)
        if p['stock_gramos'] < cantidad: return JSONResponse({"error": "Stock insuficiente"}, status_code=400)
        
        if p['es_unitario']: precio = p['p_1000'] * cantidad
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
        return {"ok": True}
    finally:
        if conn:
            cur.close()
            conn.close()


@app.post("/add_producto_catalogo")
def add_catalogo(nombre: str = Form(...), p100: float = Form(...), p250: float = Form(...), p500: float = Form(...), p1000: float = Form(...), unidad: str = Form("false")):
    is_unidad = unidad.lower() == "true"
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO productos (nombre, p_100, p_250, p_500, p_1000, es_unitario, stock_gramos) 
            VALUES (%s,%s,%s,%s,%s,%s, 0) 
            ON CONFLICT (nombre) DO UPDATE SET 
                p_100=EXCLUDED.p_100, p_250=EXCLUDED.p_250, 
                p_500=EXCLUDED.p_500, p_1000=EXCLUDED.p_1000, es_unitario=EXCLUDED.es_unitario
        """, (nombre, p100, p250, p500, p1000, is_unidad))
        conn.commit()
        return {"ok": True}
    finally:
        if conn: conn.close()

@app.post("/registrar_venta_carrito")
def registrar_venta(carrito: str = Form(...)):
    items = json.loads(carrito) # Recibe la lista de productos del carrito
    total_venta = 0
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Crear la cabecera de la venta
        cur.execute("INSERT INTO ventas (total) VALUES (0) RETURNING id")
        venta_id = cur.fetchone()['id']
        
        for item in items:
            nombre = item['producto']
            cantidad = int(item['cantidad'])
            
            cur.execute("SELECT * FROM productos WHERE nombre=%s", (nombre,))
            p = cur.fetchone()
            
            # Calcular precio escalonado
            if p['es_unitario']: subtotal = p['p_1000'] * cantidad
            else:
                if cantidad <= 100: subtotal = p['p_100']
                elif cantidad <= 250: subtotal = p['p_250']
                elif cantidad <= 500: subtotal = p['p_500']
                else: subtotal = p['p_1000']
            
            total_venta += subtotal
            
            # Insertar detalle y descontar stock
            cur.execute("INSERT INTO detalle_venta (venta_id, producto, cantidad, subtotal) VALUES (%s,%s,%s,%s)", 
                        (venta_id, nombre, cantidad, subtotal))
            cur.execute("UPDATE productos SET stock_gramos = stock_gramos - %s WHERE nombre = %s", (cantidad, nombre))
        
        # Actualizar total final
        cur.execute("UPDATE ventas SET total = %s WHERE id = %s", (total_venta, venta_id))
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        conn.close()

@app.post("/reponer_stock")
def reponer(producto: str = Form(...), cantidad: int = Form(...)):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre = %s", (cantidad, producto))
        conn.commit()
        return {"ok": True}
    finally:
        if conn:
            cur.close()
            conn.close()

@app.get("/historial")
def historial():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT v.id, v.fecha, v.total, d.producto, d.cantidad 
            FROM ventas v JOIN detalle_venta d ON v.id = d.venta_id 
            ORDER BY v.fecha DESC LIMIT 20
        """)
        return {"historial": cur.fetchall()}
    finally:
        if conn:
            cur.close()
            conn.close()

@app.post("/borrar_venta")
def borrar(id: int = Form(...)):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT producto, cantidad FROM detalle_venta WHERE venta_id=%s", (id,))
        det = cur.fetchone()
        if det: cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre=%s", (det['cantidad'], det['producto']))
        cur.execute("DELETE FROM ventas WHERE id=%s", (id,))
        conn.commit()
        return {"ok": True}
    finally:
        if conn:
            cur.close()
            conn.close()
