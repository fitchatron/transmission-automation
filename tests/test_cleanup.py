import logging
from types import SimpleNamespace

import pytest
from transmission_rpc.error import TransmissionConnectError

from tam import repo
from tam.cleanup import cleanup
from tam.config import Settings
from tam.db import get_connection, migrate
from tam.transmission import Transmission
from tests.fakes import HASH, FakeClient, torrent_fields

LOG = logging.getLogger("test")
SEEDING = "d" * 40
DOWNLOADING = "e" * 40


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def client():
    fake = FakeClient()
    fake.session = SimpleNamespace(seed_ratio_limited=True, idle_seeding_limit_enabled=False)
    return fake


@pytest.fixture
def settings(tmp_path):
    return Settings(default_dest=tmp_path)


def add(conn, client, hash_, status, finished, percent=1.0, id_=1):
    repo.insert_torrent(conn, hash_, "tv-show", name=f"Show {hash_[:4]}", status=status)
    client.torrents[hash_] = torrent_fields(
        hash_,
        id=id_,
        name=f"Show {hash_[:4]}",
        metadataPercentComplete=1.0,
        percentDone=percent,
        isFinished=finished,
    )


def run(conn, client, settings, dry_run=False):
    return cleanup(conn, Transmission(client), settings, LOG, dry_run=dry_run)


def test_removes_finished_copied_torrents_with_data(conn, client, settings):
    add(conn, client, HASH, "copied", finished=True)
    add(conn, client, SEEDING, "copied", finished=False, id_=2)

    report = run(conn, client, settings)

    assert client.removed == [(HASH, True)]
    assert [h for h, _ in report.removed] == [HASH]
    assert report.still_seeding == 1
    row = repo.get_torrent(conn, HASH)
    assert row["status"] == "removed" and row["removed_at"]
    assert repo.get_torrent(conn, SEEDING)["status"] == "copied"


def test_never_removes_uncopied_torrents(conn, client, settings):
    # Finished seeding but the copy failed / never happened: keep the data.
    add(conn, client, HASH, "failed", finished=True)
    add(conn, client, DOWNLOADING, "downloading", finished=True, percent=0.5, id_=2)

    report = run(conn, client, settings, dry_run=True)

    assert client.removed == []
    assert report.removed == []


def test_dry_run_changes_nothing(conn, client, settings):
    add(conn, client, HASH, "copied", finished=True)

    report = run(conn, client, settings, dry_run=True)

    assert [h for h, _ in report.removed] == [HASH]
    assert client.removed == []
    assert repo.get_torrent(conn, HASH)["status"] == "copied"


def test_dry_run_does_not_copy_pending(conn, client, settings, monkeypatch):
    add(conn, client, HASH, "downloaded", finished=False)
    calls = []
    monkeypatch.setattr("tam.sync.copy_torrent", lambda *a, **k: calls.append(a))

    run(conn, client, settings, dry_run=True)

    assert calls == []


def test_warns_when_no_seed_limits(conn, client, settings):
    client.session = SimpleNamespace(seed_ratio_limited=False, idle_seeding_limit_enabled=False)

    report = run(conn, client, settings)

    assert report.seed_limits_configured is False


def test_remove_error_is_reported_and_row_kept(conn, client, settings):
    add(conn, client, HASH, "copied", finished=True)

    def failing_remove(ids, delete_data=False):
        raise TransmissionConnectError("daemon went away")

    client.remove_torrent = failing_remove

    report = run(conn, client, settings)

    assert report.errors == [(HASH, "daemon went away")]
    assert repo.get_torrent(conn, HASH)["status"] == "copied"


def test_copied_torrent_already_gone_is_marked_removed_by_sync(conn, client, settings):
    repo.insert_torrent(conn, HASH, "tv-show", name="Gone", status="copied")

    report = run(conn, client, settings)

    assert repo.get_torrent(conn, HASH)["status"] == "removed"
    assert report.removed == []  # nothing for cleanup itself to remove
