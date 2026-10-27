import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tam import repo
from tam.cleanup import cleanup
from tam.config import Settings
from tam.db import get_connection, migrate
from tam.queue import queue_lock
from tam.transmission import Transmission
from tests.fakes import HASH, FakeClient, torrent_fields

LOG = logging.getLogger("test")
OTHER = "f" * 40
STOPPED, DOWNLOADING, SEEDING = 0, 4, 6


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
    return Settings(default_dest=tmp_path, queue_dir=tmp_path / "queue")


def finished_copied(conn, client, hash_=HASH, id_=1):
    """A copied torrent that has hit its seed limit (Transmission stops it)."""
    repo.insert_torrent(conn, hash_, "tv-show", name="Done", status="copied")
    client.torrents[hash_] = torrent_fields(
        hash_,
        id=id_,
        name="Done",
        metadataPercentComplete=1.0,
        percentDone=1.0,
        isFinished=True,
        status=STOPPED,
    )


def other_torrent(client, status):
    """A torrent tam doesn't track, e.g. one added by hand."""
    client.torrents[OTHER] = torrent_fields(OTHER, id=9, name="Other", status=status)


def run(conn, client, settings, **kwargs):
    return cleanup(conn, Transmission(client), settings, LOG, **kwargs)


def test_last_torrent_removed_disconnects_vpn_and_restarts_rpi_connect(
    conn, client, settings, system
):
    finished_copied(conn, client)

    report = run(conn, client, settings)

    assert client.removed == [(HASH, True)]
    assert system.calls == ["vpn disconnect", "rpi-connect restart"]
    assert report.idle.vpn_disconnected and report.idle.rpi_connect_restarted
    assert report.idle.error is None


@pytest.mark.parametrize("status", [DOWNLOADING, SEEDING])
def test_other_active_torrent_keeps_vpn_up(conn, client, settings, system, status):
    finished_copied(conn, client)
    other_torrent(client, status)

    report = run(conn, client, settings)

    assert client.removed == [(HASH, True)]
    assert system.calls == []
    assert report.idle is None


def test_stopped_leftover_torrent_counts_as_idle(conn, client, settings, system):
    finished_copied(conn, client)
    other_torrent(client, STOPPED)

    run(conn, client, settings)

    assert system.calls == ["vpn disconnect", "rpi-connect restart"]


def test_nothing_removed_does_nothing_even_when_idle(conn, client, settings, system):
    report = run(conn, client, settings)

    assert report.removed == []
    assert system.calls == []
    assert report.idle is None


def test_dry_run_only_reports(conn, client, settings, system):
    finished_copied(conn, client)

    report = run(conn, client, settings, dry_run=True)

    assert report.would_go_idle is True
    assert report.idle is None
    assert system.calls == []
    assert client.removed == []


def test_dry_run_with_other_active_torrent(conn, client, settings, system):
    finished_copied(conn, client)
    other_torrent(client, DOWNLOADING)

    report = run(conn, client, settings, dry_run=True)

    assert report.would_go_idle is False


def test_can_be_turned_off(conn, client, settings, system):
    finished_copied(conn, client)

    report = run(conn, client, replace(settings, idle_disconnect=False))

    assert client.removed == [(HASH, True)]
    assert system.calls == []
    assert report.idle is None


def test_removal_error_keeps_vpn_up(conn, client, settings, system):
    finished_copied(conn, client)
    finished_copied(conn, client, OTHER, id_=2)
    real_remove = client.remove_torrent

    def remove(ids, delete_data=False):
        if ids == OTHER:
            from transmission_rpc.error import TransmissionConnectError

            raise TransmissionConnectError("daemon went away")
        real_remove(ids, delete_data)

    client.remove_torrent = remove

    report = run(conn, client, settings)

    assert report.errors and report.removed
    assert system.calls == []


def test_skips_while_tam_start_is_running(conn, client, settings, system):
    finished_copied(conn, client)

    with queue_lock(settings.queue_dir):
        report = run(conn, client, settings)

    assert report.idle.skipped == "tam start is running"
    assert system.calls == []


def test_rpi_connect_failure_is_reported(conn, client, settings, system):
    finished_copied(conn, client)
    system.rpi_connect_result = (False, "rpi-connect is not installed")

    report = run(conn, client, settings)

    assert report.idle.vpn_disconnected is True
    assert report.idle.rpi_connect_restarted is False
    assert "rpi-connect is not installed" in report.idle.error
