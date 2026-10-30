import sqlite3

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from datetime import date, time
from ai import crear_recordatorio, ErrorIA
from database import crear_tabla, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tabla()
    yield


app = FastAPI(
    title="API de Citas Salon de Belleza",
    version="2.0",
    lifespan=lifespan
)


# 
class CitaEntrada(BaseModel):
    cliente: str = Field(min_length=3, max_length=100)
    fecha: date
    hora: time 
    servicio: str | None = Field(default=None, max_length=100)
    confirmado: bool = False
    notas: str | None = Field(default=None, max_length=500)


# Modelo de respuesta
class Cita(CitaEntrada):
    id: int
    servicio: str | None = None
    notas: str | None = Field(default=None, max_length=500)


# Convierte 
def fila_a_cita(fila: sqlite3.Row) -> Cita:
    return Cita(
        id=fila["id"],
        cliente=fila["cliente"],
        fecha=fila["fecha"],
        hora=fila["hora"],
        confirmado=bool(fila["confirmado"]),
        servicio=fila["servicio"],
        notas=fila["notas"]
    )


# Busca 
def buscar_cita(
    db: sqlite3.Connection,
    cita_id: int
) -> sqlite3.Row:
    fila = db.execute(
        "SELECT * FROM citas WHERE id = ?",
        (cita_id,)
    ).fetchone()

    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cita no encontrada"
        )

    return fila

# CREAR 
@app.post(
    "/citas",
    response_model=Cita,
    status_code=status.HTTP_201_CREATED
)
def crear_cita(
    datos: CitaEntrada,
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.execute(
        """
        INSERT INTO citas (cliente, fecha, hora, servicio, confirmado, notas)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            datos.cliente,
            datos.fecha.isoformat(),
            datos.hora.isoformat(),
            datos.servicio,
            int(datos.confirmado),
            datos.notas,
        )
    )
    db.commit()

    fila = buscar_cita(db, cursor.lastrowid)
    return fila_a_cita(fila)


# LISTAR

@app.get("/citas", response_model=list[Cita])
def listar_cita(
    confirmado: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db)
):
    consulta = "SELECT * FROM citas"
    parametros = []

    if confirmado is not None:
        consulta += " WHERE confirmado = ?"
        parametros.append(int(confirmado))

    consulta += " ORDER BY id LIMIT ? OFFSET ?"
    parametros.extend([limit, offset])

    filas = db.execute(
        consulta, parametros
    ).fetchall()

    return [fila_a_cita(fila) for fila in filas]


# CONSULTAR
@app.get("/citas/{cita_id}", response_model=Cita)
def obtener_cita(
    cita_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    fila = buscar_cita(db, cita_id)
    return fila_a_cita(fila)


# ACTUALIZAR
@app.put("/citas/{cita_id}", response_model=Cita)
def actualizar_cita(
    cita_id: int,
    datos: CitaEntrada,
    db: sqlite3.Connection = Depends(get_db)
):
    buscar_cita(db, cita_id)

    db.execute(
        """
        UPDATE citas
        SET cliente = ?, fecha = ?, hora = ?, servicio = ?, confirmado = ?, notas = ?
        WHERE id = ?
        """,
        (
            datos.cliente,
            datos.fecha.isoformat(),
            datos.hora.isoformat(),
            datos.servicio,
            int(datos.confirmado),
            datos.notas,
            cita_id
        )
    )
    db.commit()

    return fila_a_cita(buscar_cita(db, cita_id))


# ELIMINAR 
@app.delete(
    "/citas/{cita_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_cita(
    cita_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    buscar_cita(db, cita_id)

    db.execute(
        "DELETE FROM citas WHERE id = ?",
        (cita_id,)
    )
    db.commit()

    return None

# Endpoint inteligente: genera un recordatorio con IA y lo guarda como nota

@app.post("/citas/{cita_id}/recordatorio", response_model=Cita)
def generar_recordatorio(cita_id: int, db: sqlite3.Connection = Depends(get_db)):
    cita = buscar_cita(db, cita_id)
    
    try:
        res = crear_recordatorio(cita["cliente"], cita["fecha"], cita["hora"], cita["servicio"])
    except ErrorIA as error:
        raise HTTPException(status_code=503, detail=str(error))

    resultado = f"{res.reminder} {res.sugerencia}".strip()[:500]
    db.execute(
        "UPDATE citas SET notas = ? WHERE id = ?", (resultado, cita_id))
    db.commit()
    return fila_a_cita(buscar_cita(db, cita_id))
