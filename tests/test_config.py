from pathlib import Path

from tam.config import Settings


def test_defaults_without_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TAM_ENV_FILE", str(tmp_path / "missing.env"))
    for var in ("TAM_DB_PATH", "TAM_VIDEO_EXTS", "TRANSMISSION_PORT"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings.from_env()

    assert settings.db_path == Path("/opt/media-automation/torrentdata.db")
    assert settings.transmission_port == 9091
    assert settings.video_exts == {".mp4", ".mkv"}


def test_env_file_and_overrides(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"TAM_DB_PATH={tmp_path / 'x.db'}\nTRANSMISSION_PORT=1234\n")
    monkeypatch.setenv("TAM_ENV_FILE", str(env_file))
    monkeypatch.delenv("TAM_DB_PATH", raising=False)
    monkeypatch.delenv("TRANSMISSION_PORT", raising=False)
    monkeypatch.setenv("TAM_VIDEO_EXTS", "MKV, .avi")

    settings = Settings.from_env()

    assert settings.db_path == tmp_path / "x.db"
    assert settings.transmission_port == 1234
    assert settings.video_exts == {".mkv", ".avi"}
