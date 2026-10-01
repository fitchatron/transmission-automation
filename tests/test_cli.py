from typer.testing import CliRunner

from tam.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("db", "media", "start", "on-done", "copy", "sync", "cleanup", "status"):
        assert command in result.output


def test_stub_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("TAM_LOG_DIR", str(tmp_path))
    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 1
