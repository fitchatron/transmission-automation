import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from tam import repo
from tam.config import Settings
from tam.idle import IdleResult, active_torrents, go_idle
from tam.sync import SyncReport, sync
from tam.transmission import Transmission, TransmissionUnavailable


@dataclass
class CleanupReport:
    sync: SyncReport
    seed_limits_configured: bool
    removed: list[tuple[str, str | None]] = field(default_factory=list)
    still_seeding: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    # Set when the last torrent was removed and Transmission is now idle.
    idle: IdleResult | None = None
    would_go_idle: bool = False


def cleanup(
    conn: sqlite3.Connection,
    tm: Transmission,
    settings: Settings,
    log: logging.Logger,
    dry_run: bool = False,
    on_idle: Callable[[Settings, logging.Logger], IdleResult] = go_idle,
) -> CleanupReport:
    """
    Remove torrents (and their downloaded data) that were copied and finished seeding.

    "Finished seeding" is Transmission's own isFinished flag, set when the
    torrent hits its seed ratio or idle limit. Only rows with status copied
    are ever removed. Runs a sync first (copying anything pending, unless
    this is a dry run) so statuses are current.

    If this run removed something without errors and Transmission then has
    nothing left running, the VPN is disconnected and rpi-connect restarted
    (see tam.idle). Turn this off with TAM_IDLE_DISCONNECT=false.
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

    if settings.idle_disconnect and report.removed and not report.errors:
        removed = {hash_ for hash_, _ in report.removed}
        remaining = [t for t in tm.torrents() if not (dry_run and t.hash in removed)]
        if not active_torrents(remaining):
            if dry_run:
                report.would_go_idle = True
            else:
                report.idle = on_idle(settings, log)

    return report
