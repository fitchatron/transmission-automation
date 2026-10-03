import fcntl
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Queue file name -> media type of every magnet in it.
QUEUE_FILES = {"tv.txt": "tv-show", "movies.txt": "movie"}
ERROR_PREFIX = "# error:"
LOCK_NAME = ".tam-start.lock"


class QueueLocked(RuntimeError):
    """Another `tam start` holds the queue lock."""


@dataclass(frozen=True)
class QueueEntry:
    path: Path
    magnet: str
    type: str


def _is_entry(line: str) -> bool:
    return bool(line) and not line.startswith("#")


def read_queue(path: Path, type_: str) -> list[QueueEntry]:
    """Magnets in a queue file, one per line. Blank and # lines are ignored."""
    if not path.exists():
        return []
    lines = (line.strip() for line in path.read_text().splitlines())
    return [QueueEntry(path, line, type_) for line in lines if _is_entry(line)]


def rewrite_queue(path: Path, processed: set[str], failures: dict[str, str]) -> None:
    """
    Remove processed magnets from a queue file, keeping failures with an error comment.

    The file is re-read here rather than rebuilt from what was processed, so
    lines added while `tam start` was running are kept. Old error comments are
    dropped and failures get a fresh one. The swap is atomic.
    """
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    out: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith(ERROR_PREFIX):
            continue
        if line in failures:
            out.append(line)
            out.append(f"{ERROR_PREFIX} {failures[line]} ({stamp})")
        elif line in processed:
            continue
        else:
            out.append(raw)

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(out) + ("\n" if out else ""))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@contextmanager
def queue_lock(queue_dir: Path) -> Iterator[None]:
    """Hold an exclusive lock so overlapping cron runs don't process the queue twice."""
    queue_dir.mkdir(parents=True, exist_ok=True)
    with open(queue_dir / LOCK_NAME, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise QueueLocked(f"another `tam start` is running ({queue_dir / LOCK_NAME})") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
