import pytest
from utils.media import is_string_match


@pytest.mark.parametrize(
    "first, second, expected_match, threshold",
    [
        ("The Matrix", "the matrix", True, 90.0),
        ("The Matrix", "Interstellar", False, 90.0),
        ("The Matrix", "The Matrx", True, 80.0),
        ("The Matrix", "the.matrx", True, 90.0),
        ("Rick.and.Morty.S09E02.1080p.x265-ELiTE", "Rick and Morty S09E02 1080p x265-ELiTE EZTV", True, 90.0),
        # (
        #     "Rick and Morty S09E03 Rick Fu Hustle 1080p AMZN WEB-DL DDP5 1 H 264-playWEB[EZTVx.to].mkv",
        #     "Rick and Morty S09E03 Rick Fu Hustle 1080p AMZN WEB-DL DDP5 1 H 264-playWEB EZTV",
        #     True,
        #     None,
        # ),
        # ("www.UIndex.org    -    Euphoria US S03E07 1080p x265-ELiTE", "", True, None),
        # (
        #     "www.UIndex.org    -    Euphoria US S03E08 In God We Trust 1080p AMZN WEB-DL DDP5 1 H 264-NT",
        #     "",
        #     True,
        #     None,
        # ),
    ],
)
def test_is_string_match(first, second, expected_match, threshold):
    assert is_string_match(first, second, threshold=threshold) == expected_match
