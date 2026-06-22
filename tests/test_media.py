import pytest
from utils.media import is_string_match

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
