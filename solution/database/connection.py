
import sqlite3

from solution.config import DATA_DIR, DATABASE_PATH
from solution.database.schema import SCHEMA_SQL


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def initialize_database():
    with get_connection() as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()
