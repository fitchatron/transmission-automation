import sqlite3
from pathlib import Path

MEDIA_TYPES = ("tv-show", "movie")
TORRENT_STATUSES = (
    "added",
    "downloading",
    "downloaded",
    "copied",
    "removed",
    "failed",
    "missing",
)


def get_connection(path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory if needed."""
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _v1(conn: sqlite3.Connection) -> None:
    """The original schema from init_db.py. No-op on databases that already have it."""
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
        )
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
            status TEXT CHECK(status IN ('added','downloading','completed','moved','failed'))
                NOT NULL DEFAULT 'added',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            modified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (metadata_id) REFERENCES metadata(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metadata_pattern ON metadata(match_pattern)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_torrents_hash ON torrents(hash)")


def _v2(conn: sqlite3.Connection) -> None:
    """
    Key torrents on the info-hash.

    The old torrents table is kept as torrents_legacy for reference; its rows
    have no hash, so they can't be carried over.
    """
    conn.execute("DROP INDEX IF EXISTS idx_torrents_hash")
    conn.execute("ALTER TABLE torrents RENAME TO torrents_legacy")
    statuses = ",".join(f"'{s}'" for s in TORRENT_STATUSES)
    conn.execute(
        f"""
        CREATE TABLE torrents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT NOT NULL UNIQUE,
            transmission_id INTEGER,
            name TEXT,
            type TEXT CHECK(type IN ('tv-show','movie')) NOT NULL,
            magnet_link TEXT,
            metadata_id INTEGER REFERENCES metadata(id),
            status TEXT CHECK(status IN ({statuses})) NOT NULL DEFAULT 'added',
            percent_done REAL NOT NULL DEFAULT 0,
            download_dir TEXT,
            error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            modified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            copied_at DATETIME,
            removed_at DATETIME
        )
        """
    )
    conn.execute("CREATE INDEX idx_torrents_status ON torrents(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metadata_type ON metadata(type, active)")


MIGRATIONS = [_v1, _v2]
LATEST_VERSION = len(MIGRATIONS)


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> tuple[int, int]:
    """Apply pending migrations. Returns (version before, version after)."""
    before = schema_version(conn)
    for version in range(before + 1, LATEST_VERSION + 1):
        with conn:
            MIGRATIONS[version - 1](conn)
            conn.execute(f"PRAGMA user_version = {version}")
    return before, schema_version(conn)
