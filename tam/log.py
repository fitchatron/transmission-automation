import logging
import sys
from pathlib import Path

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(log_dir: Path, command: str, verbose: bool = False) -> logging.Logger:
    """
    Configure root logging for one CLI invocation.

    Logs go to <log_dir>/tam.log (tagged with the command name) and to stderr.
    If the log directory can't be created, only stderr is used.
    """
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(stderr)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "tam.log")
        file_handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(file_handler)
    except OSError as error:
        root.warning("File logging disabled (%s): %s", log_dir, error)

    return logging.getLogger(f"tam.{command}")
