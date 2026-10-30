import sqlite3
from pathlib import Path

#Declaro la ruta de la base de datos
DATABASE_PATH = Path(__file__).resolve().parent / "citas.db"

#funcion para que se conecte a la base de datos.
def get_db():
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row

    try:
        db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        db.close()


#Funcion para crear la tabla si no existe. Aqui defino las columnas que tendra mi base de datos y el tipo de datos que tendra.
def crear_tabla():
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS citas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                servicio TEXT,
                confirmado INTEGER NOT NULL DEFAULT 0,
                notas TEXT
            )
        """)

        db.commit()