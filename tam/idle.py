import logging
from dataclasses import dataclass

from tam import vpn
from tam.config import Settings
from tam.queue import QueueLocked, queue_lock
from tam.transmission import TorrentInfo


@dataclass
class IdleResult:
    vpn_disconnected: bool = False
    rpi_connect_restarted: bool = False
    skipped: str | None = None
    error: str | None = None


def active_torrents(torrents: list[TorrentInfo]) -> list[TorrentInfo]:
    """Torrents Transmission is still working on (downloading, seeding, checking, queued)."""
    return [t for t in torrents if t.status != "stopped"]


def go_idle(settings: Settings, log: logging.Logger) -> IdleResult:
    """
    Disconnect the VPN and restart rpi-connect once Transmission has nothing left to do.

    Holds the `tam start` queue lock while doing it, so a start that is adding
    torrents right now isn't cut off; if one is running, nothing happens.
    """
    try:
        with queue_lock(settings.queue_dir):
            disconnected = vpn.stop_vpn()
            if disconnected:
                log.info("Transmission idle: VPN disconnected")
            else:
                log.warning("Transmission idle, but `nordvpn disconnect` failed")
            ok, output = vpn.restart_rpi_connect()
    except QueueLocked:
        log.info("Transmission idle, but `tam start` is running; leaving the VPN up")
        return IdleResult(skipped="tam start is running")

    if not ok:
        log.error("rpi-connect restart failed: %s", output)
        return IdleResult(
            vpn_disconnected=disconnected, error=f"rpi-connect restart failed: {output}"
        )
    log.info("rpi-connect restarted")
    if not disconnected:
        return IdleResult(rpi_connect_restarted=True, error="nordvpn disconnect failed")
    return IdleResult(vpn_disconnected=True, rpi_connect_restarted=True)
