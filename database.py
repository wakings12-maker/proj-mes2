import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "citas.db"


def get_db():
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row

    try:
        db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        db.close()



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