from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import DictCursor
import os
from datetime import datetime

app = FastAPI()

# NUEVA URL (Sustituí [TU-CONTRASEÑA] y fijate en el puerto 6543)
# Reemplaza [TU-CONTRASEÑA] con la real. 
# El usuario DEBE ser postgres.tcdkapcrcntrawckkaex
DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:[Samirphite2006]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# FUNCIÓN QUE CREA LAS TABLAS AUTOMÁTICAMENTE
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Tabla de Productos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY, 
                nombre TEXT UNIQUE, 
                precio_kg REAL
            );
        """)
        
        # Tabla de Ventas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id SERIAL PRIMARY KEY, 
                fecha TEXT, 
                total REAL
            );
        """)
        
        # Tabla de Detalle de Venta
        cur.execute("""
            CREATE TABLE IF NOT EXISTS detalle_venta (
                id SERIAL PRIMARY KEY, 
                venta_id INTEGER REFERENCES ventas(id) ON DELETE CASCADE, 
                producto TEXT, 
                gramos INTEGER, 
                precio REAL
            );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tablas verificadas/creadas con éxito.")
    except Exception as e:
        print(f"❌ Error al iniciar la DB: {e}")

# Ejecutar la creación de tablas al encender la app
init_db()

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
@app.head("/")
def home(request: Request):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
        productos = cur.fetchall()
        cur.close()
        conn.close()
        return templates.TemplateResponse("index.html", {"request": request, "productos": productos})
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error de conexión:</h1><p>{e}</p>", status_code=500)

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
def agregar_producto(venta_id: int = Form(...), producto: str = Form(...), gramos: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT precio_kg FROM productos WHERE nombre=%s", (producto,))
    res = cur.fetchone()
    if res:
        total_prod = (res[0] / 1000) * gramos
        cur.execute("INSERT INTO detalle_venta(venta_id, producto, gramos, precio) VALUES(%s,%s,%s,%s)",
                   (venta_id, producto, gramos, total_prod))
        conn.commit()
        cur.close()
        conn.close()
        return {"subtotal": total_prod}
    return {"error": "Producto no encontrado"}

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
        string_agg(d.producto || ' (' || d.gramos || 'g)', ' + ') as detalle, 
        v.total FROM ventas v
        LEFT JOIN detalle_venta d ON v.id = d.venta_id
        GROUP BY v.id, v.fecha, v.total ORDER BY v.id DESC
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
    cur.execute("SELECT producto, gramos, precio FROM detalle_venta WHERE venta_id=%s", (venta_id,))
    detalles = cur.fetchall()
    cur.close()
    conn.close()
    return {"venta": venta, "detalles": detalles}

@app.post("/agregar_producto_catalogo")
def agregar_catalogo(nombre: str = Form(...), precio_kg: float = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO productos (nombre, precio_kg) VALUES (%s, %s)
        ON CONFLICT (nombre) DO UPDATE SET precio_kg = EXCLUDED.precio_kg
    """, (nombre, precio_kg))
    conn.commit()
    cur.close()
    conn.close()
    return {"mensaje": "OK"}

@app.post("/eliminar_venta")
def eliminar_venta(venta_id: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM detalle_venta WHERE venta_id=%s", (venta_id,))
    cur.execute("DELETE FROM ventas WHERE id=%s", (venta_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"mensaje": "Eliminado"}

@app.post("/reset_sistema")
def reset_sistema():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE detalle_venta, ventas, productos RESTART IDENTITY")
    conn.commit()
    cur.close()
    conn.close()
    return {"mensaje": "Reseteado"}
