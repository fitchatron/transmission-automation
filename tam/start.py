import logging
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tam import repo
from tam.media import match_metadata
from tam.queue import QueueEntry
from tam.transmission import Transmission, TransmissionUnavailable, magnet_hash

ADDED = "added"  # in Transmission, name resolved, row inserted
PENDING = "pending"  # in Transmission, metadata not resolved in time, row inserted without name
SKIPPED = "skipped"  # already tracked (or duplicate line); nothing done
FAILED = "failed"  # not added; the queue line is kept with an error comment


@dataclass
class StartResult:
    entry: QueueEntry
    outcome: str
    hash: str | None = None
    name: str | None = None
    error: str | None = None


def start_queue(
    conn: sqlite3.Connection,
    tm: Transmission,
    entries: Iterable[QueueEntry],
    metadata_timeout: float,
    log: logging.Logger,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[StartResult]:
    """
    Add queued magnets to Transmission and record exactly one row per info-hash.

    All magnets are added first so Transmission fetches their metadata in
    parallel; then each is waited on (against one shared deadline) so the row
    is written with the torrent's resolved name rather than a placeholder.
    """
    results: list[StartResult] = []
    to_wait: list[StartResult] = []
    seen: set[str] = set()

    for entry in entries:
        hash_ = magnet_hash(entry.magnet)
        if hash_ is None:
            results.append(StartResult(entry, FAILED, error="no btih info-hash in magnet link"))
            continue
        if hash_ in seen or repo.get_torrent(conn, hash_) is not None:
            log.info("Skipping %s: already tracked", hash_)
            results.append(StartResult(entry, SKIPPED, hash=hash_))
            continue
        seen.add(hash_)

        try:
            tm.add(entry.magnet)
        except TransmissionUnavailable as error:
            log.error("Transmission rejected %s: %s", hash_, error)
            results.append(StartResult(entry, FAILED, hash=hash_, error=str(error)))
            continue
        log.info("Added %s (%s) to Transmission", hash_, entry.type)
        result = StartResult(entry, ADDED, hash=hash_)
        results.append(result)
        to_wait.append(result)

    deadline = clock() + metadata_timeout
    for result in to_wait:
        remaining = max(0.0, deadline - clock())
        info = tm.wait_for_metadata(result.hash, remaining, sleep=sleep, clock=clock)
        metadata = None
        if info is None:
            result.outcome = PENDING
            log.warning("Metadata for %s not resolved in time; name left for sync", result.hash)
        else:
            result.name = info.name
            metadata = match_metadata(conn, info.name, result.entry.type)
            log.info(
                "%s -> %s",
                info.name,
                metadata["destination_path"] if metadata else "no matching metadata",
            )

        repo.insert_torrent(
            conn,
            result.hash,
            result.entry.type,
            magnet_link=result.entry.magnet,
            name=result.name,
            metadata_id=metadata["id"] if metadata else None,
            transmission_id=info.id if info else None,
        )

    return results
