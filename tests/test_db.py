import sqlite3

import pytest

from tam.db import LATEST_VERSION, _v1, get_connection, migrate, schema_version


def test_fresh_database_migrates_to_latest(tmp_path):
    conn = get_connection(tmp_path / "sub" / "fresh.db")

    assert migrate(conn) == (0, LATEST_VERSION)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"metadata", "torrents", "torrents_legacy"} <= tables


def test_existing_v1_database_keeps_rows_as_legacy():
    # Simulates the production DB: created by init_db.py, user_version never set.
    conn = get_connection(":memory:")
    _v1(conn)
    conn.execute(
        "INSERT INTO metadata (title, type, match_pattern, destination_path) "
        "VALUES ('X', 'movie', 'X', '/Movies')"
    )
    conn.execute("INSERT INTO torrents (transmission_id, name, status) VALUES (7, 'old', 'moved')")
    conn.commit()
    assert schema_version(conn) == 0

    migrate(conn)

    assert tuple(conn.execute("SELECT name, status FROM torrents_legacy").fetchone()) == (
        "old",
        "moved",
    )
    assert conn.execute("SELECT count(*) FROM torrents").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM metadata").fetchone()[0] == 1


def test_migrate_is_idempotent():
    conn = get_connection(":memory:")
    migrate(conn)

    assert migrate(conn) == (LATEST_VERSION, LATEST_VERSION)


def test_hash_is_unique_and_status_checked():
    conn = get_connection(":memory:")
    migrate(conn)
    conn.execute("INSERT INTO torrents (hash, type) VALUES ('abc', 'movie')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO torrents (hash, type) VALUES ('abc', 'movie')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO torrents (hash, type, status) VALUES ('def', 'movie', 'moved')")
