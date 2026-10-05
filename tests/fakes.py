from types import SimpleNamespace

from transmission_rpc import Torrent

from tam.transmission import magnet_hash

HASH = "c9e15763f722f23e98a29decdfae341b98d53056"


def torrent_fields(hash_=HASH, **overrides):
    fields = {
        "id": 1,
        "hashString": hash_,
        "name": hash_,
        "percentDone": 0.0,
        "metadataPercentComplete": 0.0,
        "isFinished": False,
        "status": 4,  # downloading
        "downloadDir": "/downloads",
    }
    fields.update(overrides)
    return fields


class FakeClient:
    """Stands in for transmission_rpc.Client, storing real Torrent objects."""

    def __init__(self):
        self.torrents: dict[str, dict] = {}
        self.removed: list[tuple[str, bool]] = []
        self.session = SimpleNamespace(seed_ratio_limited=False, idle_seeding_limit_enabled=False)
        self.get_calls = 0
        self.fail_with: Exception | None = None

    def add_torrent(self, magnet):
        if self.fail_with:
            raise self.fail_with
        hash_ = magnet_hash(magnet)
        fields = self.torrents.setdefault(hash_, torrent_fields(hash_, id=len(self.torrents) + 1))
        # torrent-add responses only carry id, name and hashString
        return Torrent(fields={k: fields[k] for k in ("id", "name", "hashString")})

    def get_torrent(self, torrent_id, arguments=None):
        self.get_calls += 1
        if torrent_id not in self.torrents:
            raise KeyError("Torrent not found in result")
        return Torrent(fields=self.torrents[torrent_id])

    def get_torrents(self, arguments=None):
        return [Torrent(fields=f) for f in self.torrents.values()]

    def remove_torrent(self, ids, delete_data=False):
        self.removed.append((ids, delete_data))
        self.torrents.pop(ids, None)

    def get_session(self):
        return self.session

    def resolve(self, hash_, name):
        """Simulate Transmission finishing the metadata fetch for a magnet."""
        self.torrents[hash_].update(name=name, metadataPercentComplete=1.0)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def magnet(hash_=HASH, name="placeholder"):
    return f"magnet:?xt=urn:btih:{hash_}&dn={name}"
