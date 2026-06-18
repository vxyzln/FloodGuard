from __future__ import annotations

import getpass
import os
from contextlib import contextmanager
from typing import Any, Iterator

import mysql.connector


def db_config(include_database: bool = True, prompt_password: bool = False) -> dict[str, Any]:
    password = os.getenv("FLOODGUARD_DB_PASSWORD")
    if prompt_password and password is None:
        password = getpass.getpass("MySQL root password: ")
    config: dict[str, Any] = {
        "host": os.getenv("FLOODGUARD_DB_HOST", "localhost"),
        "port": int(os.getenv("FLOODGUARD_DB_PORT", "3306")),
        "user": os.getenv("FLOODGUARD_DB_USER", "root"),
        "password": password or "",
        "connection_timeout": 1,
    }
    if include_database:
        config["database"] = os.getenv("FLOODGUARD_DB_NAME", "floodguard")
    return config


@contextmanager
def mysql_connection(prompt_password: bool = False, include_database: bool = True) -> Iterator[Any]:
    conn = mysql.connector.connect(**db_config(include_database=include_database, prompt_password=prompt_password))
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with mysql_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows


def execute(query: str, params: tuple = ()) -> None:
    with mysql_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        cursor.close()
