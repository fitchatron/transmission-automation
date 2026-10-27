import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from tam import repo
from tam.config import Settings
from tam.copy import CopyResult, copy_torrent
from tam.db import TORRENT_STATUSES
from tam.media import match_metadata
from tam.transmission import TorrentInfo, Transmission

# Statuses whose value sync derives from Transmission's progress. copied and
# failed are set by `tam copy` and only change here if the torrent disappears.
PROGRESS_STATUSES = {"added", "downloading", "downloaded", "missing"}


@dataclass
class StatusChange:
    hash: str
    name: str | None
    old: str
    new: str


@dataclass
class SyncReport:
    changes: list[StatusChange] = field(default_factory=list)
    untracked: list[TorrentInfo] = field(default_factory=list)
    copies: list[tuple[str, CopyResult]] = field(default_factory=list)
    checked: int = 0


def _progress_status(info: TorrentInfo) -> str:
    return "downloaded" if info.percent_done >= 1.0 else "downloading"


def sync(
    conn: sqlite3.Connection,
    tm: Transmission,
    log: logging.Logger,
    settings: Settings | None = None,
    copy_pending: bool = False,
) -> SyncReport:
    """
    Bring tracked rows up to date with Transmission.

    Torrents in Transmission that tam didn't add are reported, never inserted.
    With copy_pending, rows that finished downloading but were never copied
    (the on-done hook didn't run) are copied now; that needs settings.
    """
    report = SyncReport()
    live = {info.hash: info for info in tm.torrents()}
    active = [s for s in TORRENT_STATUSES if s != "removed"]
    now = datetime.now().isoformat(sep=" ", timespec="seconds")

    for row in repo.list_torrents(conn, active):
        report.checked += 1
        hash_, old = row["hash"], row["status"]
        info = live.get(hash_)

        if info is None:
            new = "removed" if old == "copied" else "missing"
            if new != old:
                repo.update_torrent(
                    conn, hash_, status=new, removed_at=now if new == "removed" else None
                )
                report.changes.append(StatusChange(hash_, row["name"], old, new))
                log.info("%s (%s): %s -> %s", row["name"] or "?", hash_, old, new)
            continue

        fields = {
            "transmission_id": info.id,
            "percent_done": info.percent_done,
            "download_dir": str(info.download_dir) if info.download_dir else None,
        }
        if info.metadata_complete:
            if row["name"] != info.name:
                fields["name"] = info.name
            if row["metadata_id"] is None:
                metadata = match_metadata(conn, info.name, row["type"])
                if metadata is not None:
                    fields["metadata_id"] = metadata["id"]
        new = _progress_status(info) if old in PROGRESS_STATUSES else old
        if new != old:
            fields["status"] = new
            report.changes.append(StatusChange(hash_, info.name, old, new))
            log.info("%s (%s): %s -> %s", info.name, hash_, old, new)
        repo.update_torrent(conn, hash_, **fields)

    known = {row["hash"] for row in repo.list_torrents(conn)}
    report.untracked = [info for hash_, info in live.items() if hash_ not in known]

    if copy_pending:
        if settings is None:
            raise ValueError("copy_pending needs settings")
        for row in repo.list_torrents(conn, ["downloaded"]):
            result = copy_torrent(conn, tm, settings, row["hash"], log)
            report.copies.append((row["hash"], result))

    return report
