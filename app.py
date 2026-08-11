```python
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

# ============================================================
# CONFIGURACIÓN DE BASE DE DATOS
# ============================================================

DATABASE_URL = "TU_DATABASE_URL"

def get_db_connection():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

templates = Jinja2Templates(directory="templates")


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM productos
            ORDER BY nombre ASC
        """)

        productos = cur.fetchall()

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "productos": productos
            }
        )

    finally:
        if conn:
            conn.close()


# ============================================================
# CATÁLOGO
#
# IMPORTANTE:
# p_1000 se utiliza como PRECIO POR KG.
#
# No eliminamos p_100, p_250 ni p_500 de la base de datos.
# Simplemente dejamos de utilizarlos para calcular ventas.
# ============================================================

@app.post("/catalogo")
def guardar_catalogo(
    nombre: str = Form(...),
    p1000: float = Form(...),
    unidad: str = Form("false")
):
    nombre = nombre.strip()
    is_uni = unidad.lower() == "true"

    if not nombre:
        return JSONResponse(
            {"error": "El nombre del producto es obligatorio"},
            status_code=400
        )

    if p1000 < 0:
        return JSONResponse(
            {"error": "El precio no puede ser negativo"},
            status_code=400
        )

    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Solamente actualizamos p_1000.
        # Las demás columnas antiguas permanecen intactas.
        cur.execute("""
            INSERT INTO productos
                (nombre, p_1000, es_unitario)
            VALUES
                (%s, %s, %s)

            ON CONFLICT (nombre)
            DO UPDATE SET
                p_1000 = EXCLUDED.p_1000,
                es_unitario = EXCLUDED.es_unitario
        """, (
            nombre,
            p1000,
            is_uni
        ))

        conn.commit()

        return {
            "status": "ok"
        }

    except Exception as e:
        if conn:
            conn.rollback()

        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

    finally:
        if conn:
            conn.close()


# ============================================================
# REPONER STOCK
# ============================================================

@app.post("/reponer")
def reponer_stock(
    producto: str = Form(...),
    cantidad: int = Form(...)
):
    if cantidad <= 0:
        return JSONResponse(
            {"error": "La cantidad debe ser mayor a 0"},
            status_code=400
        )

    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE productos
            SET stock_gramos = stock_gramos + %s
            WHERE nombre = %s
        """, (
            cantidad,
            producto
        ))

        if cur.rowcount == 0:
            return JSONResponse(
                {"error": "Producto no encontrado"},
                status_code=404
            )

        conn.commit()

        return {
            "status": "ok"
        }

    except Exception as e:
        if conn:
            conn.rollback()

        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

    finally:
        if conn:
            conn.close()


# ============================================================
# PROCESAR VENTA
# ============================================================

@app.post("/venta")
def procesar_venta(carrito: str = Form(...)):
    try:
        data = json.loads(carrito)
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "Carrito inválido"},
            status_code=400
        )

    if not isinstance(data, list) or len(data) == 0:
        return JSONResponse(
            {"error": "El carrito está vacío"},
            status_code=400
        )

    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Crear venta
        cur.execute("""
            INSERT INTO ventas (total)
            VALUES (0)
            RETURNING id
        """)

        v_id = cur.fetchone()["id"]

        total_venta = 0

        for item in data:

            nombre = str(item.get("nombre", "")).strip()

            if not nombre:
                continue

            try:
                cantidad = int(item.get("cantidad", 0))
            except (ValueError, TypeError):
                continue

            if cantidad <= 0:
                continue

            # Buscar producto
            cur.execute("""
                SELECT *
                FROM productos
                WHERE nombre = %s
            """, (
                nombre,
            ))

            producto = cur.fetchone()

            if not producto:
                continue

            precio_kg = float(producto["p_1000"] or 0)
            es_unitario = bool(producto["es_unitario"])

            # ==================================================
            # PRODUCTOS POR UNIDAD
            #
            # p_1000 representa el precio de UNA unidad.
            # ==================================================

            if es_unitario:

                precio_aplicado = precio_kg * cantidad

                stock_actual = producto["stock_gramos"] or 0

                if stock_actual < cantidad:
                    raise Exception(
                        f"Stock insuficiente de {nombre}. "
                        f"Disponible: {stock_actual} unidades."
                    )

            # ==================================================
            # PRODUCTOS POR PESO
            #
            # p_1000 representa el precio por KG.
            #
            # Ejemplo:
            # $4000/kg × 250g / 1000 = $1000
            # ==================================================

            else:

                precio_aplicado = (
                    precio_kg * cantidad
                ) / 1000

                stock_actual = producto["stock_gramos"] or 0

                if stock_actual < cantidad:
                    raise Exception(
                        f"Stock insuficiente de {nombre}. "
                        f"Disponible: {stock_actual}g."
                    )

            total_venta += precio_aplicado

            # Guardamos el precio aplicado en el momento
            # de la venta. Esto hace que las ventas históricas
            # no cambien si luego modificamos el precio del catálogo.
            cur.execute("""
                INSERT INTO detalle_venta
                    (venta_id, producto, cantidad, subtotal)
                VALUES
                    (%s, %s, %s, %s)
            """, (
                v_id,
                producto["nombre"],
                cantidad,
                precio_aplicado
            ))

            # Descontar stock
            cur.execute("""
                UPDATE productos
                SET stock_gramos = stock_gramos - %s
                WHERE nombre = %s
            """, (
                cantidad,
                producto["nombre"]
            ))

        # Actualizar total de la venta
        cur.execute("""
            UPDATE ventas
            SET total = %s
            WHERE id = %s
        """, (
            total_venta,
            v_id
        ))

        conn.commit()

        return {
            "status": "ok",
            "id": v_id,
            "total": round(total_venta, 2)
        }

    except Exception as e:

        if conn:
            conn.rollback()

        return JSONResponse(
            {
                "error": str(e)
            },
            status_code=500
        )

    finally:

        if conn:
            conn.close()


# ============================================================
# HISTORIAL
# ============================================================

@app.get("/historial")
def ver_historial():
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                v.id,

                TO_CHAR(
                    v.fecha,
                    'DD/MM/YY HH24:MI'
                ) AS fecha_formateada,

                v.total,

                string_agg(
                    d.producto
                    || ' ('
                    || d.cantidad
                    || (
                        CASE
                            WHEN p.es_unitario
                            THEN 'u'
                            ELSE 'g'
                        END
                    )
                    || ')',
                    ', '
                ) AS items

            FROM ventas v

            LEFT JOIN detalle_venta d
                ON v.id = d.venta_id

            LEFT JOIN productos p
                ON d.producto = p.nombre

            GROUP BY
                v.id,
                v.fecha,
                v.total

            ORDER BY
                v.fecha DESC

            LIMIT 50
        """)

        ventas = cur.fetchall()

        return ventas

    finally:

        if conn:
            conn.close()


# ============================================================
# OBTENER DETALLE DE UNA VENTA
# ============================================================

@app.get("/venta/{venta_id}")
def obtener_venta(venta_id: int):
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                fecha,
                total
            FROM ventas
            WHERE id = %s
        """, (
            venta_id,
        ))

        venta = cur.fetchone()

        if not venta:
            return JSONResponse(
                {"error": "Venta no encontrada"},
                status_code=404
            )

        cur.execute("""
            SELECT
                d.producto,
                d.cantidad,
                d.subtotal,
                p.es_unitario
            FROM detalle_venta d
            LEFT JOIN productos p
                ON d.producto = p.nombre
            WHERE d.venta_id = %s
            ORDER BY d.id ASC
        """, (
            venta_id,
        ))

        detalles = cur.fetchall()

        return {
            "venta": venta,
            "detalles": detalles
        }

    finally:

        if conn:
            conn.close()


# ============================================================
# BORRAR VENTA
# ============================================================

@app.post("/borrar_venta")
def borrar_venta(id: int = Form(...)):
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Recuperar productos vendidos
        cur.execute("""
            SELECT
                producto,
                cantidad
            FROM detalle_venta
            WHERE venta_id = %s
        """, (
            id,
        ))

        detalles = cur.fetchall()

        # Devolver stock
        for detalle in detalles:

            cur.execute("""
                UPDATE productos
                SET stock_gramos =
                    stock_gramos + %s
                WHERE nombre = %s
            """, (
                detalle["cantidad"],
                detalle["producto"]
            ))

        # Borrar detalles explícitamente
        cur.execute("""
            DELETE FROM detalle_venta
            WHERE venta_id = %s
        """, (
            id,
        ))

        # Borrar venta
        cur.execute("""
            DELETE FROM ventas
            WHERE id = %s
        """, (
            id,
        ))

        conn.commit()

        return {
            "status": "ok"
        }

    except Exception as e:

        if conn:
            conn.rollback()

        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

    finally:

        if conn:
            conn.close()


# ============================================================
# ESTADÍSTICAS DEL DÍA
# ============================================================

@app.get("/stats_hoy")
def stats_hoy():
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                COALESCE(SUM(total), 0) AS total_dia,
                COUNT(*) AS cantidad_ventas

            FROM ventas

            WHERE DATE(fecha) = CURRENT_DATE
        """)

        return cur.fetchone()

    finally:

        if conn:
            conn.close()


# ============================================================
# BORRAR PRODUCTO
# ============================================================

@app.post("/borrar_producto")
def borrar_producto(nombre: str = Form(...)):
    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM productos
            WHERE nombre = %s
        """, (
            nombre,
        ))

        conn.commit()

        return {
            "status": "ok"
        }

    except Exception as e:

        if conn:
            conn.rollback()

        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

    finally:

        if conn:
            conn.close()
```
