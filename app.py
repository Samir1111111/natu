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

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY nombre ASC")
    prods = cur.fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "productos": prods})


@app.post("/add_producto_catalogo")
def add_catalogo(
    nombre: str = Form(...),
    p100: float = Form(...),
    p250: float = Form(...),
    p500: float = Form(...),
    p1000: float = Form(...),
    unidad: str = Form("false")
):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO productos (nombre, p_100, p_250, p_500, p_1000, es_unitario, stock_gramos)
        VALUES (%s,%s,%s,%s,%s,%s,0)
        ON CONFLICT (nombre) DO UPDATE SET
        p_100=EXCLUDED.p_100,
        p_250=EXCLUDED.p_250,
        p_500=EXCLUDED.p_500,
        p_1000=EXCLUDED.p_1000,
        es_unitario=EXCLUDED.es_unitario
    """, (nombre, p100, p250, p500, p1000, unidad == "true"))

    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/registrar_venta_carrito")
def registrar_venta(carrito: str = Form(...)):
    items = json.loads(carrito)

    conn = get_db_connection()
    cur = conn.cursor()

    total = 0

    cur.execute("INSERT INTO ventas (total) VALUES (0) RETURNING id")
    venta_id = cur.fetchone()['id']

    for item in items:
        nombre = item['producto']
        cantidad = int(item['cantidad'])

        cur.execute("SELECT * FROM productos WHERE nombre=%s", (nombre,))
        p = cur.fetchone()

        if not p:
            return JSONResponse({"error": "Producto no existe"}, status_code=400)

        if p['stock_gramos'] < cantidad:
            return JSONResponse({"error": f"Sin stock de {nombre}"}, status_code=400)

        if p['es_unitario']:
            subtotal = p['p_1000'] * cantidad
        else:
            if cantidad <= 100:
                subtotal = p['p_100']
            elif cantidad <= 250:
                subtotal = p['p_250']
            elif cantidad <= 500:
                subtotal = p['p_500']
            else:
                subtotal = p['p_1000']

        total += subtotal

        cur.execute("""
            INSERT INTO detalle_venta (venta_id, producto, cantidad, subtotal)
            VALUES (%s,%s,%s,%s)
        """, (venta_id, nombre, cantidad, subtotal))

        cur.execute("""
            UPDATE productos SET stock_gramos = stock_gramos - %s
            WHERE nombre = %s
        """, (cantidad, nombre))

    cur.execute("UPDATE ventas SET total=%s WHERE id=%s", (total, venta_id))

    conn.commit()
    conn.close()

    return {"ok": True}


@app.post("/reponer_stock")
def reponer(producto: str = Form(...), cantidad: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE productos SET stock_gramos = stock_gramos + %s
        WHERE nombre = %s
    """, (cantidad, producto))

    conn.commit()
    conn.close()

    return {"ok": True}
