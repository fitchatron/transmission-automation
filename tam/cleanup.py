import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from tam import repo
from tam.config import Settings
from tam.sync import SyncReport, sync
from tam.transmission import Transmission, TransmissionUnavailable


@dataclass
class CleanupReport:
    sync: SyncReport
    seed_limits_configured: bool
    removed: list[tuple[str, str | None]] = field(default_factory=list)
    still_seeding: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def cleanup(
    conn: sqlite3.Connection,
    tm: Transmission,
    settings: Settings,
    log: logging.Logger,
    dry_run: bool = False,
) -> CleanupReport:
    """
    Remove torrents (and their downloaded data) that were copied and finished seeding.

    "Finished seeding" is Transmission's own isFinished flag, set when the
    torrent hits its seed ratio or idle limit. Only rows with status copied
    are ever removed. Runs a sync first (copying anything pending, unless
    this is a dry run) so statuses are current.
    """
    sync_report = sync(conn, tm, log, settings, copy_pending=not dry_run)
    limits = tm.seed_limits_configured()
    if not limits:
        log.warning(
            "Transmission has no seed ratio or idle limit enabled; "
            "torrents only finish if a per-torrent limit is set"
        )
    report = CleanupReport(sync=sync_report, seed_limits_configured=limits)

    live = {info.hash: info for info in tm.torrents()}
    for row in repo.list_torrents(conn, ["copied"]):
        hash_, name = row["hash"], row["name"]
        info = live.get(hash_)
        if info is None:
            continue  # sync has already marked it removed
        if not info.is_finished:
            report.still_seeding += 1
            continue
        if dry_run:
            report.removed.append((hash_, name))
            continue
        try:
            tm.remove(hash_, delete_data=True)
        except TransmissionUnavailable as error:
            log.error("Failed to remove %s (%s): %s", name, hash_, error)
            report.errors.append((hash_, str(error)))
            continue
        repo.update_torrent(
            conn,
            hash_,
            status="removed",
            removed_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
        )
        log.info("Removed finished torrent %s (%s) and its data", name, hash_)
        report.removed.append((hash_, name))

    return report
