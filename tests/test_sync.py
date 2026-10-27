import logging

import pytest

from tam import repo
from tam.config import Settings
from tam.db import get_connection, migrate
from tam.sync import sync
from tam.transmission import Transmission
from tests.fakes import HASH, FakeClient, torrent_fields

LOG = logging.getLogger("test")
OTHER = "b" * 40


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


def run(conn, client, **kwargs):
    return sync(conn, Transmission(client), LOG, **kwargs)


def status(conn, hash_=HASH):
    return repo.get_torrent(conn, hash_)["status"]


def test_progress_updates_status_and_fields(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show", name="Rick.and.Morty.S09E04")
    client.torrents[HASH] = torrent_fields(
        id=7, name="Rick.and.Morty.S09E04", metadataPercentComplete=1.0, percentDone=0.4
    )

    report = run(conn, client)

    row = repo.get_torrent(conn, HASH)
    assert (row["status"], row["percent_done"], row["transmission_id"]) == ("downloading", 0.4, 7)
    assert row["download_dir"] == "/downloads"
    assert [(c.old, c.new) for c in report.changes] == [("added", "downloading")]

    client.torrents[HASH]["percentDone"] = 1.0
    run(conn, client)
    assert status(conn) == "downloaded"


def test_fills_in_name_and_metadata_for_pending_rows(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show")  # start timed out waiting for metadata
    client.torrents[HASH] = torrent_fields(
        name="Rick.and.Morty.S09E05.1080p", metadataPercentComplete=1.0
    )

    run(conn, client)

    row = repo.get_torrent(conn, HASH)
    assert row["name"] == "Rick.and.Morty.S09E05.1080p"
    assert row["metadata_id"] == repo.list_metadata(conn)[0]["id"]


def test_placeholder_name_is_not_stored_before_metadata(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show")
    client.torrents[HASH] = torrent_fields()  # name is still the hash

    run(conn, client)

    assert repo.get_torrent(conn, HASH)["name"] is None


def test_copied_and_failed_are_not_overwritten_by_progress(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show", name="A", status="copied")
    repo.insert_torrent(conn, OTHER, "tv-show", name="B", status="failed")
    client.torrents[HASH] = torrent_fields(HASH, percentDone=1.0, metadataPercentComplete=1.0)
    client.torrents[OTHER] = torrent_fields(
        OTHER, id=2, percentDone=1.0, metadataPercentComplete=1.0
    )

    report = run(conn, client)

    assert (status(conn), status(conn, OTHER)) == ("copied", "failed")
    assert report.changes == []


def test_gone_from_transmission(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show", name="A", status="copied")
    repo.insert_torrent(conn, OTHER, "tv-show", name="B", status="downloading")

    run(conn, client)

    assert status(conn) == "removed"
    assert repo.get_torrent(conn, HASH)["removed_at"] is not None
    assert status(conn, OTHER) == "missing"


def test_missing_torrent_that_comes_back_recovers(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show", name="A", status="missing")
    client.torrents[HASH] = torrent_fields(percentDone=0.2, metadataPercentComplete=1.0)

    run(conn, client)

    assert status(conn) == "downloading"


def test_removed_rows_are_left_alone(conn, client):
    repo.insert_torrent(conn, HASH, "tv-show", name="A", status="removed")

    report = run(conn, client)

    assert report.checked == 0
    assert status(conn) == "removed"


def test_untracked_torrents_are_reported_not_inserted(conn, client):
    client.torrents[OTHER] = torrent_fields(OTHER, name="Someone.Elses.Torrent")

    report = run(conn, client)

    assert [t.hash for t in report.untracked] == [OTHER]
    assert repo.list_torrents(conn) == []


def test_copy_pending(conn, client, tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "Movie.mkv").write_bytes(b"m")
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    repo.insert_torrent(conn, HASH, "movie", name="Movie", status="downloading")
    client.torrents[HASH] = torrent_fields(
        name="Movie",
        metadataPercentComplete=1.0,
        percentDone=1.0,
        downloadDir=str(downloads),
        files=[{"name": "Movie.mkv", "length": 1, "bytesCompleted": 1}],
        priorities=[0],
        wanted=[True],
    )

    report = run(conn, client, settings=Settings(default_dest=incoming), copy_pending=True)

    assert [r.outcome for _, r in report.copies] == ["copied"]
    assert status(conn) == "copied"
    assert (incoming / "Movie.mkv").exists()
