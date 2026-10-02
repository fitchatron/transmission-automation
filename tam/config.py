import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path("/opt/media-automation")
DEFAULT_ENV_FILE = BASE_DIR / ".env"


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    db_path: Path = BASE_DIR / "torrentdata.db"
    queue_dir: Path = BASE_DIR / "queue"
    log_dir: Path = BASE_DIR / "logs"
    default_dest: Path = Path("/mnt/ds223j/Incoming")
    transmission_host: str = "localhost"
    transmission_port: int = 9091
    transmission_user: str | None = None
    transmission_pass: str | None = None
    metadata_timeout: int = 120
    video_exts: frozenset[str] = field(default_factory=lambda: frozenset({".mp4", ".mkv"}))

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Build settings from environment variables.

        Variables are read after loading a .env file: TAM_ENV_FILE if set,
        otherwise /opt/media-automation/.env, otherwise ./.env. Variables
        already set in the environment win over the file.
        """
        env_file = _env_path("TAM_ENV_FILE", DEFAULT_ENV_FILE)
        load_dotenv(env_file if env_file.exists() else None)

        defaults = cls()
        exts = os.environ.get("TAM_VIDEO_EXTS")
        return cls(
            db_path=_env_path("TAM_DB_PATH", defaults.db_path),
            queue_dir=_env_path("TAM_QUEUE_DIR", defaults.queue_dir),
            log_dir=_env_path("TAM_LOG_DIR", defaults.log_dir),
            default_dest=_env_path("TAM_DEFAULT_DEST", defaults.default_dest),
            transmission_host=os.environ.get("TRANSMISSION_HOST", defaults.transmission_host),
            transmission_port=_env_int("TRANSMISSION_PORT", defaults.transmission_port),
            transmission_user=os.environ.get("TRANSMISSION_USER") or None,
            transmission_pass=os.environ.get("TRANSMISSION_PASS") or None,
            metadata_timeout=_env_int("TAM_METADATA_TIMEOUT", defaults.metadata_timeout),
            video_exts=(
                frozenset(
                    e if e.startswith(".") else f".{e}"
                    for e in (x.strip().lower() for x in exts.split(","))
                    if e
                )
                if exts
                else defaults.video_exts
            ),
        )
