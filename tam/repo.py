import sqlite3
from datetime import datetime

from tam.db import TORRENT_STATUSES

TORRENT_FIELDS = {
    "transmission_id",
    "name",
    "metadata_id",
    "status",
    "percent_done",
    "download_dir",
    "error",
    "copied_at",
    "removed_at",
}


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


# --- metadata ---------------------------------------------------------------


def add_metadata(
    conn: sqlite3.Connection, title: str, type_: str, match_pattern: str, destination: str
) -> int:
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO metadata (title, type, match_pattern, destination_path)
            VALUES (?, ?, ?, ?)
            """,
            (title, type_, match_pattern, destination),
        )
    return cursor.lastrowid


def list_metadata(
    conn: sqlite3.Connection, type_: str | None = None, include_inactive: bool = False
) -> list[sqlite3.Row]:
    query = "SELECT * FROM metadata WHERE 1 = 1"
    params: list = []
    if type_ is not None:
        query += " AND type = ?"
        params.append(type_)
    if not include_inactive:
        query += " AND active = 1"
    return conn.execute(query + " ORDER BY id", params).fetchall()


def set_metadata_active(conn: sqlite3.Connection, metadata_id: int, active: bool) -> bool:
    """Returns False if no row has that id."""
    with conn:
        cursor = conn.execute(
            "UPDATE metadata SET active = ?, modified_at = ? WHERE id = ?",
            (int(active), _now(), metadata_id),
        )
    return cursor.rowcount == 1


# --- torrents ---------------------------------------------------------------


def insert_torrent(
    conn: sqlite3.Connection,
    hash_: str,
    type_: str,
    magnet_link: str | None = None,
    name: str | None = None,
    metadata_id: int | None = None,
    transmission_id: int | None = None,
    status: str = "added",
) -> int:
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO torrents
                (hash, type, magnet_link, name, metadata_id, transmission_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (hash_.lower(), type_, magnet_link, name, metadata_id, transmission_id, status),
        )
    return cursor.lastrowid


def get_torrent(conn: sqlite3.Connection, hash_: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM torrents WHERE hash = ?", (hash_.lower(),)).fetchone()


def update_torrent(conn: sqlite3.Connection, hash_: str, **fields) -> bool:
    """Update the given columns (and modified_at). Returns False if the hash is unknown."""
    unknown = set(fields) - TORRENT_FIELDS
    if unknown:
        raise ValueError(f"Unknown torrent fields: {sorted(unknown)}")
    if "status" in fields and fields["status"] not in TORRENT_STATUSES:
        raise ValueError(f"Unknown status: {fields['status']}")

    fields["modified_at"] = _now()
    assignments = ", ".join(f"{column} = ?" for column in fields)
    with conn:
        cursor = conn.execute(
            f"UPDATE torrents SET {assignments} WHERE hash = ?",
            (*fields.values(), hash_.lower()),
        )
    return cursor.rowcount == 1


def list_torrents(conn: sqlite3.Connection, statuses: list[str] | None = None) -> list[sqlite3.Row]:
    if not statuses:
        return conn.execute("SELECT * FROM torrents ORDER BY id").fetchall()
    placeholders = ",".join("?" for _ in statuses)
    return conn.execute(
        f"SELECT * FROM torrents WHERE status IN ({placeholders}) ORDER BY id", statuses
    ).fetchall()
