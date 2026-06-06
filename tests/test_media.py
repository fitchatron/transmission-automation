from utils.media import is_string_match


def test_is_string_match_returns_true_with_default_threshold():
    assert is_string_match("The Matrix", "the matrix")


def test_is_string_match_returns_false_when_below_threshold():
    assert not is_string_match("The Matrix", "Interstellar")


def test_is_string_match_uses_custom_threshold():
    assert is_string_match("The Matrix", "The Matrx", threshold=80.0)
