from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import psycopg2
import os
from datetime import datetime

app = FastAPI()

DATABASE_URL = "postgresql://postgres.tcdkapcrcntrawckkaex:Samirphite2006@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY,
        nombre TEXT UNIQUE,
        precio_100 REAL,
        precio_250 REAL,
        precio_500 REAL,
        precio_1000 REAL,
        stock_gramos INTEGER DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id SERIAL PRIMARY KEY,
        fecha TIMESTAMP,
        total REAL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS detalle_venta (
        id SERIAL PRIMARY KEY,
        venta_id INTEGER,
        producto TEXT,
        gramos INTEGER,
        precio REAL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS movimientos_stock (
        id SERIAL PRIMARY KEY,
        producto TEXT,
        cantidad INTEGER,
        tipo TEXT,
        fecha TIMESTAMP
    );
    """)

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
    productos = cur.fetchall()
    cur.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": productos})

@app.get("/dashboard")
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE DATE(fecha)=CURRENT_DATE")
    hoy = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date_trunc('month', fecha)=date_trunc('month', CURRENT_DATE)")
    mes = cur.fetchone()[0]

    cur.close()
    conn.close()
    return {"hoy": hoy, "mes": mes}

@app.get("/nueva_venta")
def nueva_venta():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO ventas(fecha,total) VALUES(NOW(),0) RETURNING id")
    vid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"venta_id": vid}

@app.post("/agregar_producto")
def agregar_producto(venta_id: int = Form(...), producto: str = Form(...), gramos: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT precio_100,precio_250,precio_500,precio_1000,stock_gramos FROM productos WHERE nombre=%s",(producto,))
    p = cur.fetchone()

    if not p:
        return {"error":"Producto no encontrado"}

    if p[4] < gramos:
        return {"error":"Stock insuficiente"}

    if gramos <= 100:
        precio = p[0]
    elif gramos <= 250:
        precio = p[1]
    elif gramos <= 500:
        precio = p[2]
    else:
        precio = p[3]

    cur.execute("INSERT INTO detalle_venta VALUES(DEFAULT,%s,%s,%s,%s)",(venta_id,producto,gramos,precio))

    cur.execute("UPDATE productos SET stock_gramos=stock_gramos-%s WHERE nombre=%s",(gramos,producto))

    cur.execute("INSERT INTO movimientos_stock(producto,cantidad,tipo,fecha) VALUES(%s,%s,'venta',NOW())",(producto,-gramos))

    conn.commit()
    cur.close()
    conn.close()
    return {"subtotal": precio}

@app.post("/reponer_stock")
def reponer(producto: str = Form(...), cantidad: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("UPDATE productos SET stock_gramos=stock_gramos+%s WHERE nombre=%s",(cantidad,producto))

    cur.execute("INSERT INTO movimientos_stock(producto,cantidad,tipo,fecha) VALUES(%s,%s,'reposicion',NOW())",(producto,cantidad))

    conn.commit()
    cur.close()
    conn.close()
    return {"ok":True}

@app.get("/movimientos")
def movimientos():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT producto,cantidad,tipo,fecha FROM movimientos_stock ORDER BY fecha DESC LIMIT 20")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return {"movimientos": data}
