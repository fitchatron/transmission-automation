import pytest
from typer.testing import CliRunner

from tam.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TAM_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("TAM_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TAM_DB_PATH", str(tmp_path / "tam.db"))


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
