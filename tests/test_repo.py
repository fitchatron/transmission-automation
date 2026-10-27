import pytest

from tam import repo
from tam.db import get_connection, migrate


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    migrate(connection)
    yield connection
    connection.close()


def test_insert_and_get_torrent_normalises_hash(conn):
    repo.insert_torrent(conn, "ABCDEF", "movie", magnet_link="magnet:?xt=urn:btih:ABCDEF")

    row = repo.get_torrent(conn, "abcdef")

    assert row["hash"] == "abcdef"
    assert row["status"] == "added"
    assert row["name"] is None


def test_update_torrent(conn):
    repo.insert_torrent(conn, "abc", "tv-show")

    assert repo.update_torrent(conn, "ABC", name="Show.S01E01", status="downloading")
    row = repo.get_torrent(conn, "abc")
    assert (row["name"], row["status"]) == ("Show.S01E01", "downloading")
    assert repo.update_torrent(conn, "missing", status="copied") is False


def test_update_torrent_rejects_bad_input(conn):
    repo.insert_torrent(conn, "abc", "tv-show")

    with pytest.raises(ValueError):
        repo.update_torrent(conn, "abc", hash="other")
    with pytest.raises(ValueError):
        repo.update_torrent(conn, "abc", status="moved")


def test_list_torrents_by_status(conn):
    repo.insert_torrent(conn, "a", "movie")
    repo.insert_torrent(conn, "b", "movie", status="copied")

    assert [r["hash"] for r in repo.list_torrents(conn)] == ["a", "b"]
    assert [r["hash"] for r in repo.list_torrents(conn, ["copied"])] == ["b"]


def test_metadata_list_and_disable(conn):
    first = repo.add_metadata(conn, "A", "movie", "A", "/Movies")
    repo.add_metadata(conn, "B", "tv-show", "B", "/TV/B")

    assert repo.set_metadata_active(conn, first, False)
    assert [r["title"] for r in repo.list_metadata(conn)] == ["B"]
    assert [r["title"] for r in repo.list_metadata(conn, include_inactive=True)] == ["A", "B"]
    assert [r["title"] for r in repo.list_metadata(conn, "movie")] == []
    assert repo.set_metadata_active(conn, 999, False) is False
