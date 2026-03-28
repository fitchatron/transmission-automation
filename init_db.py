#!/usr/bin/env python3

import sqlite3
from pathlib import Path
from utils.db import get_connection


def main():
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT CHECK(type IN ('tv-show','movie')) NOT NULL,
            match_pattern TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            modified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            active INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    conn.execute(
        """
          CREATE TABLE IF NOT EXISTS torrents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              transmission_id INTEGER,
              name TEXT NOT NULL,
              magnet_link TEXT,
              hash TEXT,
              metadata_id INTEGER,
              status TEXT CHECK(status IN ('added','downloading','completed','moved','failed')) NOT NULL DEFAULT 'added',
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              modified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              completed_at DATETIME,
              FOREIGN KEY (metadata_id) REFERENCES metadata(id)
          );
    """
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metadata_pattern ON metadata(match_pattern);"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_torrents_hash ON torrents(hash);")

    print("Database initialised.")


if __name__ == "__main__":
    main()

