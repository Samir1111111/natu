import json
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

# URL con puerto 6543 para evitar bloqueos de conexión
DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:Samirphite2006@aws-1-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

def get_db_connection():
    # Usamos RealDictCursor para que los resultados sean como diccionarios p['nombre']
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

templates = Jinja2Templates(directory="templates")

# --- RUTA PRINCIPAL ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
        prods = cur.fetchall()
        return templates.TemplateResponse("index.html", {"request": request, "productos": prods})
    finally:
        if conn: conn.close()

# --- GESTIÓN DE CATÁLOGO ---
@app.post("/catalogo")
def guardar_catalogo(nombre: str = Form(...), p100: float = Form(...), p250: float = Form(...), p500: float = Form(...), p1000: float = Form(...), unidad: str = Form("false")):
    is_uni = unidad.lower() == "true"
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO productos (nombre, p_100, p_250, p_500, p_1000, es_unitario)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (nombre) DO UPDATE SET 
            p_100=EXCLUDED.p_100, p_250=EXCLUDED.p_250, p_500=EXCLUDED.p_500, p_1000=EXCLUDED.p_1000, es_unitario=EXCLUDED.es_unitario
        """, (nombre.strip(), p100, p250, p500, p1000, is_uni))
        conn.commit()
        return {"status": "ok"}
    finally:
        if conn: conn.close()

# --- REPOSICIÓN DE STOCK ---
@app.post("/reponer")
def reponer_stock(producto: str = Form(...), cantidad: int = Form(...)):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre = %s", (cantidad, producto))
        conn.commit()
        return {"status": "ok"}
    finally:
        if conn: conn.close()

# --- PROCESAR VENTA (CARRITO) ---
@app.post("/venta")
def procesar_venta(carrito: str = Form(...)):
    data = json.loads(carrito)
    conn = get_db_connection()
    cur = conn.cursor()
    total_venta = 0
    try:
        # 1. Crear la cabecera de la venta
        cur.execute("INSERT INTO ventas (total) VALUES (0) RETURNING id")
        v_id = cur.fetchone()['id']
        
        for item in data:
            cur.execute("SELECT * FROM productos WHERE nombre = %s", (item['nombre'],))
            p = cur.fetchone()
            cant = int(item['cantidad'])
            
            # 2. Lógica de precio escalonado
            if p['es_unitario']: 
                sub = p['p_1000'] * cant
            else:
                if cant <= 100: sub = p['p_100']
                elif cant <= 250: sub = p['p_250']
                elif cant <= 500: sub = p['p_500']
                else: sub = p['p_1000']
            
            total_venta += sub
            
            # 3. Insertar detalle y descontar stock_gramos
            cur.execute("INSERT INTO detalle_venta (venta_id, producto, cantidad, subtotal) VALUES (%s,%s,%s,%s)", 
                        (v_id, p['nombre'], cant, sub))
            cur.execute("UPDATE productos SET stock_gramos = stock_gramos - %s WHERE nombre = %s", (cant, p['nombre']))
            
        # 4. Actualizar total final de la venta
        cur.execute("UPDATE ventas SET total = %s WHERE id = %s", (total_venta, v_id))
        conn.commit()
        return {"id": v_id}
    except Exception as e:
        conn.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        conn.close()

# --- VER HISTORIAL ---
@app.get("/historial")
def ver_historial():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Ajuste para que el historial muestre 'g' o 'u' automáticamente
        cur.execute("""
            SELECT v.id, v.fecha, v.total, 
            string_agg(d.producto || ' (' || d.cantidad || (CASE WHEN p.es_unitario THEN 'u' ELSE 'g' END) || ')', ', ') as items
            FROM ventas v 
            LEFT JOIN detalle_venta d ON v.id = d.venta_id
            LEFT JOIN productos p ON d.producto = p.nombre
            GROUP BY v.id ORDER BY v.fecha DESC LIMIT 50
        """)
        return cur.fetchall()
    finally:
        if conn: conn.close()

# --- BORRAR VENTA ---
@app.post("/borrar_venta")
def borrar_venta(id: int = Form(...)):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # 1. Devolver stock antes de borrar
        cur.execute("SELECT producto, cantidad FROM detalle_venta WHERE venta_id = %s", (id,))
        detalles = cur.fetchall()
        for d in detalles:
            cur.execute("UPDATE productos SET stock_gramos = stock_gramos + %s WHERE nombre = %s", (d['cantidad'], d['producto']))
        
        # 2. Borrar la venta (el detalle se borra por CASCADE)
        cur.execute("DELETE FROM ventas WHERE id = %s", (id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        if conn: conn.close()

    # --- AGREGAR ESTAS RUTAS AL APP.PY ---

@app.get("/stats_hoy")
def stats_hoy():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Suma el total de las ventas cuya fecha sea hoy
        cur.execute("SELECT COALESCE(SUM(total), 0) as total_dia, COUNT(*) as cantidad_ventas FROM ventas WHERE DATE(fecha) = CURRENT_DATE")
        return cur.fetchone()
    finally:
        if conn: conn.close()

@app.post("/borrar_producto")
def borrar_producto(nombre: str = Form(...)):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Borra el producto (esto fallará si tiene ventas asociadas a menos que uses CASCADE o limpies historial)
        # Por seguridad, el SQL que ejecutamos antes ya maneja las relaciones.
        cur.execute("DELETE FROM productos WHERE nombre = %s", (nombre,))
        conn.commit()
        return {"status": "ok"}
    finally:
        if conn: conn.close()
