import logging
from pathlib import Path

import pytest

from tam import repo
from tam.config import Settings
from tam.copy import COPIED, FAILED, UNTRACKED, copy_torrent
from tam.db import get_connection, migrate
from tam.transmission import Transmission
from tests.fakes import HASH, FakeClient, torrent_fields

LOG = logging.getLogger("test")


@pytest.fixture
def downloads(tmp_path):
    path = tmp_path / "downloads"
    path.mkdir()
    return path


@pytest.fixture
def settings(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    movies = tmp_path / "Movies"
    movies.mkdir()
    return Settings(default_dest=incoming, movie_dest=movies)


@pytest.fixture
def tv_dest(tmp_path):
    path = tmp_path / "TV" / "Rick"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def conn(tv_dest):
    connection = get_connection(":memory:")
    migrate(connection)
    repo.add_metadata(connection, "Rick and Morty", "tv-show", "Rick.and.Morty", str(tv_dest))
    yield connection
    connection.close()


@pytest.fixture
def client():
    return FakeClient()


def add_download(client, downloads, files, name="Rick.and.Morty.S09E04", complete=True):
    """Create files under downloads/ and register a finished torrent listing them."""
    for rel, content in files.items():
        path = downloads / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    client.torrents[HASH] = torrent_fields(
        name=name,
        metadataPercentComplete=1.0,
        percentDone=1.0 if complete else 0.5,
        downloadDir=str(downloads),
        files=[
            {
                "name": rel,
                "length": len(content),
                "bytesCompleted": len(content) if complete else 0,
            }
            for rel, content in files.items()
        ],
        priorities=[0] * len(files),
        wanted=[True] * len(files),
    )


def track(conn, name="Rick.and.Morty.S09E04", type_="tv-show"):
    metadata = repo.list_metadata(conn, type_)
    repo.insert_torrent(
        conn, HASH, type_, name=name, metadata_id=metadata[0]["id"] if metadata else None
    )


def run(conn, client, settings):
    return copy_torrent(conn, Transmission(client), settings, HASH, LOG)


def test_single_file_torrent(conn, client, settings, downloads, tv_dest):
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})
    track(conn)

    result = run(conn, client, settings)

    assert result.outcome == COPIED
    assert (tv_dest / "Rick.and.Morty.S09E04.mkv").read_bytes() == b"video"
    row = repo.get_torrent(conn, HASH)
    assert row["status"] == "copied" and row["copied_at"] and row["error"] is None
    assert row["download_dir"] == str(downloads)
    assert list(tv_dest.glob("*.part")) == []


def test_folder_torrent_copies_videos_only(conn, client, settings, downloads, tv_dest):
    """Regression: the old on_done.py crashed on folder torrents (undefined `file`)."""
    add_download(
        client,
        downloads,
        {
            "Rick.and.Morty.S09E04/Rick.and.Morty.S09E04.mkv": b"episode",
            "Rick.and.Morty.S09E04/Sample/rick-sample.mkv": b"s",
            "Rick.and.Morty.S09E04/info.nfo": b"nfo",
        },
    )
    track(conn)

    result = run(conn, client, settings)

    assert result.outcome == COPIED
    assert sorted(p.name for p in tv_dest.iterdir()) == ["Rick.and.Morty.S09E04.mkv"]


def test_no_video_files_fails(conn, client, settings, downloads):
    add_download(client, downloads, {"Some.Album/track.flac": b"x"})
    track(conn)

    result = run(conn, client, settings)

    assert result.outcome == FAILED
    row = repo.get_torrent(conn, HASH)
    assert row["status"] == "failed" and "no video files" in row["error"]


def test_incomplete_download_fails(conn, client, settings, downloads):
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"}, complete=False)
    track(conn)

    result = run(conn, client, settings)

    assert result.outcome == FAILED
    assert "not fully downloaded" in result.error


def test_existing_same_size_file_is_skipped(conn, client, settings, downloads, tv_dest):
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})
    (tv_dest / "Rick.and.Morty.S09E04.mkv").write_bytes(b"VIDEO")  # same size
    track(conn)

    result = run(conn, client, settings)

    assert result.outcome == COPIED
    assert result.copied == [] and len(result.skipped) == 1
    assert (tv_dest / "Rick.and.Morty.S09E04.mkv").read_bytes() == b"VIDEO"


def test_retry_after_failure_succeeds(conn, client, settings, downloads, tv_dest):
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"}, complete=False)
    track(conn)
    assert run(conn, client, settings).outcome == FAILED

    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})
    result = run(conn, client, settings)

    assert result.outcome == COPIED
    assert repo.get_torrent(conn, HASH)["error"] is None


def test_untracked_hash_is_ignored_and_not_inserted(conn, client, settings, downloads):
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})

    result = run(conn, client, settings)

    assert result.outcome == UNTRACKED
    assert repo.list_torrents(conn) == []


def test_unmatched_tv_uses_default_destination(conn, client, settings, downloads):
    add_download(client, downloads, {"Other.Show.S01E01.mkv": b"e"}, name="Other.Show.S01E01")
    repo.insert_torrent(conn, HASH, "tv-show", name="Other.Show.S01E01")

    result = run(conn, client, settings)

    assert result.destination == settings.default_dest
    assert (settings.default_dest / "Other.Show.S01E01.mkv").exists()


def test_movie_goes_to_movie_destination_without_metadata(conn, client, settings, downloads):
    add_download(client, downloads, {"Some.Movie.2024.mkv": b"m"}, name="Some.Movie.2024")
    track(conn, name="Some.Movie.2024", type_="movie")

    result = run(conn, client, settings)

    assert result.outcome == COPIED
    assert result.destination == settings.movie_dest
    assert sorted(p.name for p in settings.movie_dest.iterdir()) == ["Some.Movie.2024.mkv"]
    assert list(settings.default_dest.iterdir()) == []


def test_movie_ignores_movie_metadata(conn, client, settings, downloads, tmp_path):
    """Old movie metadata rows are no longer used for routing."""
    elsewhere = tmp_path / "Elsewhere"
    elsewhere.mkdir()
    repo.add_metadata(conn, "Some Movie", "movie", "Some.Movie", str(elsewhere))
    add_download(client, downloads, {"Some.Movie.2024.mkv": b"m"}, name="Some.Movie.2024")
    repo.insert_torrent(conn, HASH, "movie")  # name NULL, as if pending

    result = run(conn, client, settings)

    assert result.destination == settings.movie_dest
    assert repo.get_torrent(conn, HASH)["metadata_id"] is None
    assert list(elsewhere.iterdir()) == []


def test_movie_with_subtitles_gets_its_own_folder(conn, client, settings, downloads):
    add_download(
        client,
        downloads,
        {
            "Some.Movie.2024/Some.Movie.2024.mkv": b"movie",
            "Some.Movie.2024/Some.Movie.2024.en.srt": b"subs",
            "Some.Movie.2024/Subs/French.SRT": b"sous",
            "Some.Movie.2024/Sample/sample.mkv": b"s",
            "Some.Movie.2024/info.nfo": b"nfo",
        },
        name="Some.Movie.2024",
    )
    track(conn, name="Some.Movie.2024", type_="movie")

    result = run(conn, client, settings)

    folder = settings.movie_dest / "Some.Movie.2024"
    assert result.outcome == COPIED
    assert result.destination == folder
    assert [p.name for p in settings.movie_dest.iterdir()] == ["Some.Movie.2024"]
    assert sorted(p.name for p in folder.iterdir()) == [
        "French.SRT",
        "Some.Movie.2024.en.srt",
        "Some.Movie.2024.mkv",
    ]
    assert (folder / "Some.Movie.2024.en.srt").read_bytes() == b"subs"


def test_movie_with_subtitles_retry_reuses_folder(conn, client, settings, downloads):
    files = {"M/M.mkv": b"movie", "M/M.srt": b"subs"}
    add_download(client, downloads, files, name="M")
    track(conn, name="M", type_="movie")
    assert run(conn, client, settings).outcome == COPIED

    result = run(conn, client, settings)

    assert result.outcome == COPIED and result.copied == [] and len(result.skipped) == 2


def test_movie_with_incomplete_subtitle_fails(conn, client, settings, downloads):
    add_download(client, downloads, {"M/M.mkv": b"movie", "M/M.srt": b"subs"}, name="M")
    client.torrents[HASH]["files"][1]["bytesCompleted"] = 0
    track(conn, name="M", type_="movie")

    result = run(conn, client, settings)

    assert result.outcome == FAILED and "M.srt" in result.error
    assert list(settings.movie_dest.iterdir()) == []


def test_tv_subtitles_are_not_copied(conn, client, settings, downloads, tv_dest):
    add_download(
        client,
        downloads,
        {"R/Rick.and.Morty.S09E04.mkv": b"episode", "R/Rick.and.Morty.S09E04.srt": b"subs"},
    )
    track(conn)

    run(conn, client, settings)

    assert sorted(p.name for p in tv_dest.iterdir()) == ["Rick.and.Morty.S09E04.mkv"]


def test_unavailable_destination_fails_instead_of_falling_back(
    conn, client, settings, downloads, tv_dest
):
    """Regression: a missing target (e.g. share not mounted) used to copy to the default
    destination and still report `copied`."""
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})
    track(conn)
    tv_dest.rmdir()

    result = run(conn, client, settings)

    assert result.outcome == FAILED
    assert str(tv_dest) in result.error and "not available" in result.error
    row = repo.get_torrent(conn, HASH)
    assert row["status"] == "failed" and row["copied_at"] is None
    assert list(settings.default_dest.iterdir()) == []  # nothing went to the fallback


def test_unavailable_movie_destination_fails(conn, client, settings, downloads):
    add_download(client, downloads, {"M/M.mkv": b"m", "M/M.srt": b"s"}, name="M")
    track(conn, name="M", type_="movie")
    settings.movie_dest.rmdir()

    result = run(conn, client, settings)

    assert result.outcome == FAILED
    assert "not available" in result.error
    assert not settings.movie_dest.exists()  # the movie folder isn't created on its own


def test_copy_that_does_not_land_fails(conn, client, settings, downloads, tv_dest, monkeypatch):
    """The copy is checked afterwards: a truncated or vanished file is a failure, not `copied`."""
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})
    track(conn)

    def truncating_copy(src, dst):
        Path(dst).write_bytes(b"vi")

    monkeypatch.setattr("tam.copy.shutil.copy2", truncating_copy)

    result = run(conn, client, settings)

    assert result.outcome == FAILED
    assert "missing or incomplete" in result.error
    assert repo.get_torrent(conn, HASH)["status"] == "failed"


def test_pending_row_gets_name_and_metadata_filled_in(conn, client, settings, downloads, tv_dest):
    """A row inserted before metadata resolved is matched now that the name is known."""
    add_download(client, downloads, {"Rick.and.Morty.S09E04.mkv": b"video"})
    repo.insert_torrent(conn, HASH, "tv-show")  # name NULL, no metadata

    result = run(conn, client, settings)

    assert result.destination == tv_dest
    row = repo.get_torrent(conn, HASH)
    assert row["name"] == "Rick.and.Morty.S09E04"
    assert row["metadata_id"] is not None


def test_torrent_gone_from_transmission_fails(conn, client, settings):
    track(conn)

    result = run(conn, client, settings)

    assert result.outcome == FAILED
    assert "not in Transmission" in result.error
