import sqlite3
from pathlib import Path

DB_PATH = Path("/opt/media-automation/torrentdata.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

