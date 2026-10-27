import base64
import binascii
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import transmission_rpc
from transmission_rpc.error import TransmissionError

from tam.config import Settings

# Only the fields we use, so polling stays cheap on a busy daemon.
TORRENT_FIELDS = [
    "id",
    "hashString",
    "name",
    "percentDone",
    "metadataPercentComplete",
    "isFinished",
    "status",
    "downloadDir",
]

_HEX_HASH = re.compile(r"^[0-9a-fA-F]{40}$")
_BASE32_HASH = re.compile(r"^[A-Za-z2-7]{32}$")


class TransmissionUnavailable(RuntimeError):
    """Transmission couldn't be reached or rejected the request."""


def magnet_hash(magnet: str) -> str | None:
    """
    Return the BitTorrent v1 info-hash of a magnet link as lowercase hex.

    Accepts the 40-char hex and 32-char base32 forms of xt=urn:btih:.
    Returns None if the link has no usable btih hash.
    """
    parsed = urlparse(magnet.strip())
    if parsed.scheme != "magnet":
        return None
    for xt in parse_qs(parsed.query).get("xt", []):
        if not xt.lower().startswith("urn:btih:"):
            continue
        value = xt[len("urn:btih:") :]
        if _HEX_HASH.match(value):
            return value.lower()
        if _BASE32_HASH.match(value):
            try:
                return base64.b32decode(value.upper()).hex()
            except binascii.Error:
                return None
    return None


@dataclass(frozen=True)
class TorrentInfo:
    hash: str
    id: int
    name: str
    percent_done: float
    metadata_complete: bool
    is_finished: bool
    status: str
    download_dir: Path | None

    @classmethod
    def from_rpc(cls, torrent: transmission_rpc.Torrent) -> "TorrentInfo":
        fields = torrent.fields
        return cls(
            hash=torrent.hash_string.lower(),
            id=torrent.id,
            name=torrent.name,
            percent_done=float(fields.get("percentDone", 0.0)),
            metadata_complete=float(fields.get("metadataPercentComplete", 0.0)) >= 1.0,
            is_finished=bool(fields.get("isFinished", False)),
            status=torrent.status.value if "status" in fields else "unknown",
            download_dir=Path(fields["downloadDir"]) if fields.get("downloadDir") else None,
        )


@dataclass(frozen=True)
class TorrentFile:
    path: Path
    size: int
    complete: bool


class Transmission:
    """Thin wrapper over transmission_rpc.Client that speaks in info-hashes."""

    def __init__(self, client):
        self._client = client

    @classmethod
    def connect(cls, settings: Settings) -> "Transmission":
        try:
            client = transmission_rpc.Client(
                host=settings.transmission_host,
                port=settings.transmission_port,
                username=settings.transmission_user,
                password=settings.transmission_pass,
            )
        except TransmissionError as error:
            raise TransmissionUnavailable(
                f"Can't connect to Transmission at "
                f"{settings.transmission_host}:{settings.transmission_port}: {error}"
            ) from error
        return cls(client)

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TransmissionError as error:
            raise TransmissionUnavailable(str(error)) from error

    def add(self, magnet: str) -> TorrentInfo:
        """
        Add a magnet. If Transmission already has it, the existing torrent is returned.

        The add response only carries id, name and hash; the rest of the
        returned info is defaults until metadata is fetched with get().
        """
        torrent = self._call(self._client.add_torrent, magnet)
        return TorrentInfo.from_rpc(torrent)

    def get(self, hash_: str) -> TorrentInfo | None:
        try:
            torrent = self._call(self._client.get_torrent, hash_.lower(), arguments=TORRENT_FIELDS)
        except KeyError:
            return None
        return TorrentInfo.from_rpc(torrent)

    def torrents(self) -> list[TorrentInfo]:
        torrents = self._call(self._client.get_torrents, arguments=TORRENT_FIELDS)
        return [TorrentInfo.from_rpc(t) for t in torrents]

    def wait_for_metadata(
        self,
        hash_: str,
        timeout: float,
        poll: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> TorrentInfo | None:
        """
        Poll until the torrent's metadata (and so its real name) has resolved.

        Returns None on timeout or if the torrent disappears.
        """
        deadline = clock() + timeout
        while True:
            info = self.get(hash_)
            if info is None:
                return None
            if info.metadata_complete:
                return info
            if clock() >= deadline:
                return None
            sleep(poll)

    def files(self, hash_: str) -> list[TorrentFile]:
        try:
            torrent = self._call(
                self._client.get_torrent,
                hash_.lower(),
                arguments=["files", "priorities", "wanted", "downloadDir"],
            )
        except KeyError:
            return []
        download_dir = Path(torrent.download_dir)
        return [
            TorrentFile(path=download_dir / f.name, size=f.size, complete=f.completed >= f.size)
            for f in torrent.get_files()
        ]

    def remove(self, hash_: str, delete_data: bool) -> None:
        self._call(self._client.remove_torrent, hash_.lower(), delete_data=delete_data)

    def seed_limits_configured(self) -> bool:
        """True if the session stops seeding on a ratio or idle limit."""
        session = self._call(self._client.get_session)
        return bool(session.seed_ratio_limited or session.idle_seeding_limit_enabled)
