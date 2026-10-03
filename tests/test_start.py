import logging
from pathlib import Path

import pytest
from transmission_rpc.error import TransmissionConnectError

from tam import repo
from tam.db import get_connection, migrate
from tam.queue import QueueEntry
from tam.start import ADDED, FAILED, PENDING, SKIPPED, start_queue
from tam.transmission import Transmission
from tests.fakes import HASH, FakeClient, FakeClock, magnet

OTHER = "a" * 40
LOG = logging.getLogger("test")


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    migrate(connection)
    repo.add_metadata(connection, "Rick and Morty", "tv-show", "Rick.and.Morty", "/TV/Rick")
    yield connection
    connection.close()


@pytest.fixture
def client():
    return FakeClient()


def entry(magnet_link, type_="tv-show"):
    return QueueEntry(Path("tv.txt"), magnet_link, type_)


def run(conn, client, entries, resolve=None, timeout=60):
    """Run start_queue; `resolve` maps hash -> name that resolves on the first wait."""
    clock = FakeClock()

    def sleep(seconds):
        clock.sleep(seconds)
        for hash_, name in (resolve or {}).items():
            client.resolve(hash_, name)

    return start_queue(conn, Transmission(client), entries, timeout, LOG, sleep=sleep, clock=clock)


def test_one_row_with_resolved_name(conn, client):
    """Regression: the name changes from the placeholder after metadata resolves -> still one row."""
    real_name = "Rick.and.Morty.S09E04.1080p.WEB.h264-EDITH[EZTVx.to].mkv"

    [result] = run(conn, client, [entry(magnet(HASH))], resolve={HASH: real_name})

    assert (result.outcome, result.hash, result.name) == (ADDED, HASH, real_name)
    rows = repo.list_torrents(conn)
    assert len(rows) == 1
    row = rows[0]
    assert (row["hash"], row["name"], row["status"], row["type"]) == (
        HASH,
        real_name,
        "added",
        "tv-show",
    )
    assert row["metadata_id"] == repo.list_metadata(conn)[0]["id"]
    assert row["transmission_id"] == 1


def test_duplicate_line_in_same_run(conn, client):
    results = run(conn, client, [entry(magnet(HASH)), entry(magnet(HASH, "x"))], {HASH: "Show"})

    assert [r.outcome for r in results] == [ADDED, SKIPPED]
    assert len(repo.list_torrents(conn)) == 1


def test_hash_already_tracked_is_skipped_without_touching_transmission(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show", name="Show")

    [result] = run(conn, client, [entry(magnet(HASH.upper()))])

    assert result.outcome == SKIPPED
    assert client.torrents == {}


def test_metadata_timeout_inserts_pending_row(conn, client):
    [result] = run(conn, client, [entry(magnet(HASH))], resolve=None, timeout=10)

    assert result.outcome == PENDING
    row = repo.get_torrent(conn, HASH)
    assert row["name"] is None and row["metadata_id"] is None


def test_shared_deadline_across_torrents(conn, client):
    clock = FakeClock()
    entries = [entry(magnet(HASH)), entry(magnet(OTHER), "movie")]

    results = start_queue(
        conn, Transmission(client), entries, 10, LOG, sleep=clock.sleep, clock=clock
    )

    assert [r.outcome for r in results] == [PENDING, PENDING]
    assert clock.now <= 12  # not 10s per torrent


def test_junk_line_fails(conn, client):
    [result] = run(conn, client, [entry("https://example.com/not-a-magnet")])

    assert result.outcome == FAILED
    assert "btih" in result.error
    assert repo.list_torrents(conn) == []


def test_transmission_error_fails_that_entry_only(conn, client):
    client.fail_with = TransmissionConnectError("connection refused")

    [result] = run(conn, client, [entry(magnet(HASH))])

    assert result.outcome == FAILED
    assert "connection refused" in result.error
    assert repo.list_torrents(conn) == []


def test_unmatched_name_has_no_metadata(conn, client):
    [result] = run(conn, client, [entry(magnet(OTHER), "movie")], {OTHER: "Some.Movie.2024"})

    assert result.outcome == ADDED
    assert repo.get_torrent(conn, OTHER)["metadata_id"] is None
