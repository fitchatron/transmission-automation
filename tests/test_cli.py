import sqlite3

import pytest
from typer.testing import CliRunner

from tam import cli
from tam.cli import app
from tam.transmission import Transmission
from tests.fakes import HASH, FakeClient, magnet

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TAM_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("TAM_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TAM_DB_PATH", str(tmp_path / "tam.db"))
    monkeypatch.setenv("TAM_QUEUE_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("TAM_METADATA_TIMEOUT", "0")


def invoke(*args):
    return runner.invoke(app, list(args))


def test_help_lists_commands():
    result = invoke("--help")

    assert result.exit_code == 0
    for command in ("db", "media", "start", "on-done", "copy", "sync", "cleanup", "status"):
        assert command in result.output


def test_stub_exits_nonzero():
    assert invoke("sync").exit_code == 1


def test_db_init_then_already_current():
    first = invoke("db", "init")
    second = invoke("db", "init")

    assert first.exit_code == 0 and "v0 -> v2" in first.output
    assert second.exit_code == 0 and "already at v2" in second.output


def test_media_add_list_disable():
    assert (
        invoke(
            "media", "add", "Rick and Morty", "tv", "/TV/Rick", "--pattern", "Rick.and.Morty"
        ).exit_code
        == 0
    )
    assert invoke("media", "add", "The Matrix", "movie").exit_code == 0

    listed = invoke("media", "list")
    assert "Rick.and.Morty" in listed.output and "tv-show" in listed.output
    assert "/Movies" in listed.output

    assert invoke("media", "disable", "1").exit_code == 0
    assert "Rick.and.Morty" not in invoke("media", "list").output
    assert "Rick.and.Morty" in invoke("media", "list", "--all").output


def test_media_add_validation():
    assert invoke("media", "add", "Show", "tv").exit_code == 2  # tv needs a destination
    assert invoke("media", "add", "Show", "cartoon", "/x").exit_code == 2

    assert invoke("media", "add", "Dup", "movie").exit_code == 0
    duplicate = invoke("media", "add", "Dup", "movie")
    assert duplicate.exit_code == 1
    assert "already uses pattern" in duplicate.output


def test_media_disable_unknown_id():
    assert invoke("media", "disable", "42").exit_code == 1


@pytest.fixture
def queue_dir(tmp_path):
    path = tmp_path / "queue"
    path.mkdir()
    return path


def test_start_empty_queue(queue_dir):
    result = invoke("start")

    assert result.exit_code == 0
    assert "Queue empty" in result.output


def test_start_vpn_down_leaves_queue_untouched(monkeypatch, queue_dir):
    (queue_dir / "tv.txt").write_text(magnet() + "\n")
    monkeypatch.setattr(cli, "ensure_vpn", lambda: False)

    result = invoke("start")

    assert result.exit_code == 1
    assert (queue_dir / "tv.txt").read_text() == magnet() + "\n"


def test_start_end_to_end(monkeypatch, tmp_path, queue_dir):
    client = FakeClient()
    other = "b" * 40
    (queue_dir / "tv.txt").write_text(f"# shows\n{magnet()}\nnot-a-magnet\n")
    (queue_dir / "movies.txt").write_text(magnet(other) + "\n")
    monkeypatch.setattr(cli, "ensure_vpn", lambda: True)
    monkeypatch.setattr(Transmission, "connect", classmethod(lambda cls, s: cls(client)))

    result = invoke("start")

    assert result.exit_code == 1  # the junk line failed
    tv = (queue_dir / "tv.txt").read_text().splitlines()
    assert tv[0] == "# shows"
    assert tv[1] == "not-a-magnet"
    assert tv[2].startswith("# error: no btih")
    assert (queue_dir / "movies.txt").read_text() == ""

    conn = sqlite3.connect(tmp_path / "tam.db")
    rows = conn.execute("SELECT hash, type FROM torrents ORDER BY hash").fetchall()
    assert rows == [(other, "movie"), (HASH, "tv-show")]
