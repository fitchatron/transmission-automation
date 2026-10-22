import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tam import repo
from tam.config import Settings
from tam.media import match_metadata
from tam.transmission import TorrentFile, Transmission, TransmissionUnavailable

COPIED = "copied"
FAILED = "failed"
UNTRACKED = "untracked"


@dataclass
class CopyResult:
    outcome: str
    destination: Path | None = None
    copied: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    error: str | None = None


class CopyError(Exception):
    pass


def video_files(files: list[TorrentFile], video_exts: frozenset[str]) -> list[TorrentFile]:
    """Video files worth keeping: right extension, and not a sample clip."""
    return [
        f
        for f in files
        if f.path.suffix.lower() in video_exts and "sample" not in f.path.stem.lower()
    ]


def _destination(conn: sqlite3.Connection, row) -> Path | None:
    """The matched metadata's destination, or None if the torrent matched nothing."""
    metadata = repo.get_metadata(conn, row["metadata_id"]) if row["metadata_id"] else None
    return Path(metadata["destination_path"]) if metadata is not None else None


def _copy_file(source: Path, dest_dir: Path) -> bool:
    """
    Copy via a .part file then rename, and confirm the result.

    Returns False if a same-size copy is already there. Raises CopyError if
    the file isn't at the destination with the source's size afterwards.
    """
    target = dest_dir / source.name
    expected = source.stat().st_size
    if target.exists() and target.stat().st_size == expected:
        return False
    partial = target.with_name(target.name + ".part")
    try:
        shutil.copy2(source, partial)
        os.replace(partial, target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    if not target.is_file() or target.stat().st_size != expected:
        raise CopyError(f"{target} missing or incomplete after copy")
    return True


def copy_torrent(
    conn: sqlite3.Connection,
    tm: Transmission,
    settings: Settings,
    hash_: str,
    log: logging.Logger,
) -> CopyResult:
    """
    Copy a finished torrent's video files to its destination, looked up by info-hash.

    The torrent stays in Transmission to keep seeding; `tam cleanup` removes it later.
    Torrents that `tam start` didn't add are ignored, never inserted.
    """
    row = repo.get_torrent(conn, hash_)
    if row is None:
        log.info("Ignoring untracked torrent %s", hash_)
        return CopyResult(UNTRACKED)

    try:
        info = tm.get(hash_)
        if info is None:
            raise CopyError("torrent is not in Transmission")

        # Fill in what `start` couldn't if metadata hadn't resolved by then.
        if row["name"] is None or row["metadata_id"] is None:
            metadata = match_metadata(conn, info.name, row["type"])
            repo.update_torrent(
                conn, hash_, name=info.name, metadata_id=metadata["id"] if metadata else None
            )
            row = repo.get_torrent(conn, hash_)

        videos = video_files(tm.files(hash_), settings.video_exts)
        if not videos:
            raise CopyError("no video files in torrent")
        incomplete = [f.path.name for f in videos if not f.complete]
        if incomplete:
            raise CopyError(f"not fully downloaded: {', '.join(incomplete)}")

        # A matched destination that's unavailable (e.g. the share isn't
        # mounted) fails the copy so it can be retried, rather than quietly
        # sending the files somewhere else.
        dest = _destination(conn, row) or settings.default_dest
        if not dest.is_dir():
            raise CopyError(f"destination {dest} is not available (missing or not mounted)")
        result = CopyResult(COPIED, destination=dest)
        for video in videos:
            if _copy_file(video.path, dest):
                result.copied.append(video.path)
                log.info("Copied %s -> %s", video.path, dest / video.path.name)
            else:
                result.skipped.append(video.path)
                log.info("Already at destination: %s", dest / video.path.name)
    except (CopyError, TransmissionUnavailable, OSError) as error:
        log.error("Copy failed for %s (%s): %s", row["name"] or hash_, hash_, error)
        repo.update_torrent(conn, hash_, status=FAILED, error=str(error))
        return CopyResult(FAILED, error=str(error))

    repo.update_torrent(
        conn,
        hash_,
        status=COPIED,
        error=None,
        percent_done=1.0,
        download_dir=str(info.download_dir) if info.download_dir else None,
        copied_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
    )
    return result
