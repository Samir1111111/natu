from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import DictCursor
import os
from datetime import datetime

app = FastAPI()

# URL CORREGIDA: Usamos el host del pooler con el puerto 5432 y el usuario completo
# Reemplaza [TU-CONTRASEÑA] con la real.
DATABASE_URL = "postgresql://postgres:[Samirphite2006]@db.wxgqlovvyqjbgahxdyil.supabase.co:5432/postgres"

def get_db_connection():
    # Conexión directa con SSL requerido para Render
    return psycopg2.connect(DATABASE_URL)

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
    productos = cur.fetchall()
    cur.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": productos})

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
