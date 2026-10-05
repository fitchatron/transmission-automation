import pytest

from tam import repo
from tam.db import get_connection, migrate
from tam.media import is_string_match, match_metadata

"""
first == torrent_name in DB
second == torrent_name when on complete is triggered by Transmission
"""


@pytest.mark.parametrize(
    "first, second, expected_match, threshold",
    [
        ("The Matrix", "the matrix", True, 90.0),
        ("The Matrix", "Interstellar", False, 90.0),
        ("The Matrix", "The Matrx", True, 80.0),
        ("The Matrix", "the.matrx", True, 90.0),
        (
            "Rick.and.Morty.S09E02.1080p.x265-ELiTE",
            "Rick and Morty S09E02 1080p x265-ELiTE EZTV",
            True,
            90.0,
        ),
        (
            "Rick.and.Morty.S09E04.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "Rick.and.Morty.S09E04.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            True,
            90.0,
        ),
        (
            "Rick and Morty S09E05 Jer Bud 1080p AMZN WEB-DL DDP5 1 H 264-FLUX",
            "www.UIndex.org    -    Rick and Morty S09E05 Jer Bud 1080p AMZN WEB-DL DDP5 1 H 264-FLUX",
            True,
            89.0,
        ),
        (
            "Rick and Morty S09E05 1080p AMZN WEB-DL DDP5 1 H 264-FLUX",
            "www.UIndex.org    -    Rick and Morty S09E04 1080p AMZN WEB-DL DDP5 1 H 264-FLUX",
            False,
            89.0,
        ),
    ],
)
def test_is_string_match(first, second, expected_match, threshold):
    assert is_string_match(first, second, threshold=threshold) == expected_match


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    migrate(connection)
    repo.add_metadata(connection, "Rick and Morty", "tv-show", "Rick.and.Morty", "/TV/Rick")
    repo.add_metadata(connection, "The Boys", "tv-show", "The.Boys", "/TV/Boys")
    repo.add_metadata(connection, "The Boys", "movie", "The.Boys", "/Movies")
    yield connection
    connection.close()


@pytest.mark.parametrize(
    "name, type_, expected_destination",
    [
        ("Rick.and.Morty.S09E04.1080p.WEB.h264-EDITH[EZTVx.to].mkv", "tv-show", "/TV/Rick"),
        ("www.UIndex.org    -    The.Boys.S05E01.1080p.WEB.h264-ETHEL", "tv-show", "/TV/Boys"),
        ("The Boys S05E06 Though the Heavens Fall 1080p", "movie", "/Movies"),
        ("Invincible.2021.S04E07.1080p.WEB.h264-ETHEL", "tv-show", None),
        ("Rick.and.Morty.S09E04.1080p", "movie", None),
    ],
)
def test_match_metadata(conn, name, type_, expected_destination):
    row = match_metadata(conn, name, type_)

    assert (row["destination_path"] if row else None) == expected_destination


def test_match_metadata_ignores_inactive(conn):
    row = match_metadata(conn, "Rick.and.Morty.S09E04", "tv-show")
    repo.set_metadata_active(conn, row["id"], False)

    assert match_metadata(conn, "Rick.and.Morty.S09E04", "tv-show") is None
