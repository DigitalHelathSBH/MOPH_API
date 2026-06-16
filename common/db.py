from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pyodbc

from common.config import DatabaseConfig, get_database_config


def build_connection_string(config: DatabaseConfig | None = None) -> str:
    config = config or get_database_config()
    return (
        f"DRIVER={{{config.driver}}};"
        f"SERVER={config.server};"
        f"DATABASE={config.database};"
        f"UID={config.username};"
        f"PWD={config.password};"
        "TrustServerCertificate=yes;"
    )


@contextmanager
def connect(config: DatabaseConfig | None = None) -> Iterator[pyodbc.Connection]:
    conn = pyodbc.connect(build_connection_string(config))
    try:
        yield conn
    finally:
        conn.close()


def fetch_dicts(cursor: pyodbc.Cursor) -> list[dict]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def insert_api_log(conn: pyodbc.Connection, apiwork: str, host: str, ip: str = "127.0.0.1") -> None:
    sql = """
    INSERT INTO Saraburi.dbo.API_log (IP, Makedate, apiwork, host)
    VALUES (?, GETDATE(), ?, ?)
    """
    conn.cursor().execute(sql, ip, apiwork, host)
    conn.commit()
