import sqlite3

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from datetime import date

from database import crear_tabla, get_db

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AI_API_KEY")


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tabla()
    yield


app = FastAPI(
    title="API de Citas Salon de Belleza",
    version="1.0",
    lifespan=lifespan
)


# 
class CitaEntrada(BaseModel):
    cliente: str = Field(min_length=3, max_length=100)
    fecha: date
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    servicio: str | None = Field(default=None, max_length=100)
    confirmado: bool = False
    notas: str | None = Field(default=None, max_length=500)


# Modelo de respuesta
class Cita(CitaEntrada):
    id: int
    servicio: str | None = None
    notas: str | None = None


# Convierte una fila de SQLite en un objeto Tarea
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


# Busca una tarea por su ID
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
            datos.hora,
            datos.servicio,
            int(datos.confirmado),
            datos.notas
        )
    )
    db.commit()

    fila = buscar_cita(db, cursor.lastrowid)
    return fila_a_cita(fila)


# LISTAR

@app.get("/citas", response_model=list[Cita])
def listar_cita(
    completada: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db)
):
    consulta = "SELECT * FROM citas"
    parametros = []

    if completada is not None:
        consulta += " WHERE confirmado = ?"
        parametros.append(int(completada))

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
            datos.hora,
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
@app.post("/citas/{cita_id}/recordatorio")
def generar_recordatorio(cita_id: int, db: sqlite3.Connection = Depends(get_db)):
    cita = buscar_cita(db, cita_id)

    if not API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No está configurada la clave de IA (AI_API_KEY)",
        )

    prompt = (
        f"Crea un recordatorio breve, amable y profesional en español para {cita['cliente']}. "
        f"La cita es el {cita['fecha']} a las {cita['hora']} para "
        f"{cita['servicio'] or 'un servicio de belleza'}. No uses datos reales."
    )

    try:
        respuesta = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": os.getenv("AI_MODEL", "gpt-4o-mini"),
                "input": prompt,
            },
            timeout=30.0,
        )
        respuesta.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"El proveedor de IA respondió con error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo conectar con el proveedor de IA",
        ) from exc

    datos_respuesta = respuesta.json()
    resultado = datos_respuesta.get("output_text")
    if not resultado:
        textos = []
        for parte in datos_respuesta.get("output", []):
            for contenido in parte.get("content", []):
                if contenido.get("type") == "output_text":
                    textos.append(contenido.get("text", ""))
        resultado = " ".join(textos).strip()

    if not resultado:
        raise HTTPException(status_code=502, detail="La IA no devolvió texto")

    resultado = resultado[:500]
    db.execute("UPDATE citas SET notas = ? WHERE id = ?", (resultado, cita_id))
    db.commit()
    return {"cita_id": cita_id, "recordatorio": resultado}