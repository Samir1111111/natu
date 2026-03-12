from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import sqlite3
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Conexión a la base de datos
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# Configuración de tablas
cursor.execute("CREATE TABLE IF NOT EXISTS productos(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio_kg REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS ventas(id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, total REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS detalle_venta(id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto TEXT, gramos INTEGER, precio REAL)")
conn.commit()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    productos = cursor.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    return templates.TemplateResponse("index.html", {"request": request, "productos": productos})

@app.get("/nueva_venta")
def nueva_venta():
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    cursor.execute("INSERT INTO ventas(fecha, total) VALUES(?,?)", (fecha, 0))
    conn.commit()
    return {"venta_id": cursor.lastrowid}

@app.post("/agregar_producto")
def agregar_producto(venta_id: int = Form(...), producto: str = Form(...), gramos: int = Form(...)):
    res = cursor.execute("SELECT precio_kg FROM productos WHERE nombre=?", (producto,)).fetchone()
    if res:
        total_prod = (res[0] / 1000) * gramos
        cursor.execute("INSERT INTO detalle_venta(venta_id, producto, gramos, precio) VALUES(?,?,?,?)",
                       (venta_id, producto, gramos, total_prod))
        conn.commit()
        return {"subtotal": total_prod}
    return {"error": "No encontrado"}

@app.post("/finalizar_venta")
def finalizar_venta(venta_id: int = Form(...)):
    total = cursor.execute("SELECT SUM(precio) FROM detalle_venta WHERE venta_id=?", (venta_id,)).fetchone()[0] or 0
    cursor.execute("UPDATE ventas SET total=? WHERE id=?", (total, venta_id))
    conn.commit()
    return {"total": total}

@app.get("/ventas")
def ver_ventas():
    # Agrupamos productos para la tabla principal
    ventas = cursor.execute("""
        SELECT v.id, v.fecha, 
        GROUP_CONCAT(d.producto || ' (' || d.gramos || 'g)', ' + ') as detalle, 
        v.total FROM ventas v
        LEFT JOIN detalle_venta d ON v.id = d.venta_id
        GROUP BY v.id ORDER BY v.id DESC
    """).fetchall()
    return {"ventas": ventas}

@app.get("/ticket/{venta_id}")
def obtener_ticket(venta_id: int):
    venta = cursor.execute("SELECT id, fecha, total FROM ventas WHERE id=?", (venta_id,)).fetchone()
    detalles = cursor.execute("SELECT producto, gramos, precio FROM detalle_venta WHERE venta_id=?", (venta_id,)).fetchall()
    return {"venta": venta, "detalles": detalles}

@app.post("/agregar_producto_catalogo")
def agregar_catalogo(nombre: str = Form(...), precio_kg: float = Form(...)):
    existe = cursor.execute("SELECT id FROM productos WHERE nombre=?", (nombre,)).fetchone()
    if existe:
        cursor.execute("UPDATE productos SET precio_kg=? WHERE nombre=?", (precio_kg, nombre))
    else:
        cursor.execute("INSERT INTO productos(nombre, precio_kg) VALUES(?,?)", (nombre, precio_kg))
    conn.commit()
    return {"mensaje": "OK"}

@app.post("/eliminar_venta")
def eliminar_venta(venta_id: int = Form(...)):
    cursor.execute("DELETE FROM detalle_venta WHERE venta_id=?", (venta_id,))
    cursor.execute("DELETE FROM ventas WHERE id=?", (venta_id,))
    conn.commit()
    return {"mensaje": "Eliminado"}

@app.post("/reset_sistema")
def reset_sistema():
    cursor.execute("DELETE FROM detalle_venta")
    cursor.execute("DELETE FROM ventas")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('ventas', 'detalle_venta')")
    conn.commit()
    return {"mensaje": "Reseteado"}