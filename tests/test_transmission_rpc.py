from pathlib import Path
from types import SimpleNamespace

import pytest
from transmission_rpc.error import TransmissionConnectError

from tam.transmission import Transmission, TransmissionUnavailable, magnet_hash
from tests.fakes import HASH, FakeClient, FakeClock, torrent_fields


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def tm(client):
    return Transmission(client)


@pytest.mark.parametrize(
    "magnet, expected",
    [
        (f"magnet:?xt=urn:btih:{HASH.upper()}&dn=Some.Show", HASH),
        (f"magnet:?dn=x&xt=urn:btih:{HASH}&tr=udp://tracker", HASH),
        # base32 form of the same hash
        ("magnet:?xt=urn:btih:ZHQVOY7XELZD5GFCTXWN7LRUDOMNKMCW", HASH),
        ("magnet:?xt=urn:btmh:1220abcdef", None),
        ("magnet:?xt=urn:btih:nothex", None),
        ("https://example.com/file.torrent", None),
        ("", None),
    ],
)
def test_magnet_hash(magnet, expected):
    assert magnet_hash(magnet) == expected


def test_add_returns_hash_and_duplicate_returns_existing(tm, client):
    first = tm.add(f"magnet:?xt=urn:btih:{HASH}")
    again = tm.add(f"magnet:?xt=urn:btih:{HASH.upper()}")

    assert first.hash == HASH
    assert again.id == first.id
    assert len(client.torrents) == 1


def test_get_and_missing(tm, client):
    client.torrents[HASH] = torrent_fields(
        name="Show.S01E01", percentDone=0.5, metadataPercentComplete=1.0
    )

    info = tm.get(HASH.upper())

    assert info.name == "Show.S01E01"
    assert info.percent_done == 0.5
    assert info.metadata_complete
    assert info.status == "downloading"
    assert info.download_dir == Path("/downloads")
    assert tm.get("0" * 40) is None


def test_list(tm, client):
    client.torrents[HASH] = torrent_fields()
    client.torrents["a" * 40] = torrent_fields("a" * 40, id=2, isFinished=True)

    infos = {i.hash: i for i in tm.torrents()}

    assert set(infos) == {HASH, "a" * 40}
    assert infos["a" * 40].is_finished


def test_wait_for_metadata_resolves(tm, client):
    client.torrents[HASH] = torrent_fields()
    clock = FakeClock()

    def sleep(seconds):
        clock.sleep(seconds)
        if clock.now >= 6:  # metadata arrives on the 4th poll
            client.torrents[HASH].update(metadataPercentComplete=1.0, name="Real.Name.S01E01")

    info = tm.wait_for_metadata(HASH, timeout=60, sleep=sleep, clock=clock)

    assert info.name == "Real.Name.S01E01"
    assert client.get_calls == 4


def test_wait_for_metadata_times_out(tm, client):
    client.torrents[HASH] = torrent_fields()
    clock = FakeClock()

    assert tm.wait_for_metadata(HASH, timeout=10, sleep=clock.sleep, clock=clock) is None
    assert clock.now == 10


def test_wait_for_metadata_torrent_disappears(tm):
    clock = FakeClock()

    assert tm.wait_for_metadata(HASH, timeout=10, sleep=clock.sleep, clock=clock) is None


def test_files_joins_download_dir(tm, client):
    client.torrents[HASH] = torrent_fields(
        files=[
            {"name": "Show.S01E01/Show.S01E01.mkv", "length": 100, "bytesCompleted": 100},
            {"name": "Show.S01E01/sample.mkv", "length": 10, "bytesCompleted": 5},
        ],
        priorities=[0, 0],
        wanted=[True, True],
    )

    files = tm.files(HASH)

    assert files[0].path == Path("/downloads/Show.S01E01/Show.S01E01.mkv")
    assert (files[0].size, files[0].complete) == (100, True)
    assert files[1].complete is False
    assert tm.files("0" * 40) == []


def test_remove(tm, client):
    client.torrents[HASH] = torrent_fields()

    tm.remove(HASH.upper(), delete_data=True)

    assert client.removed == [(HASH, True)]


@pytest.mark.parametrize(
    "ratio, idle, expected",
    [(False, False, False), (True, False, True), (False, True, True)],
)
def test_seed_limits_configured(tm, client, ratio, idle, expected):
    client.session = SimpleNamespace(seed_ratio_limited=ratio, idle_seeding_limit_enabled=idle)

    assert tm.seed_limits_configured() is expected


def test_rpc_errors_are_wrapped(tm, client):
    client.fail_with = TransmissionConnectError("connection refused")

    with pytest.raises(TransmissionUnavailable, match="connection refused"):
        tm.add(f"magnet:?xt=urn:btih:{HASH}")
