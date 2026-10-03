import re
import sqlite3

from rapidfuzz import fuzz


def normalize(text: str) -> str:
    """
    Normalize title text for fuzzy matching.

    Converts input to lowercase and strips all non-alphanumeric characters
    so small punctuation/spacing differences do not affect comparisons.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_string_match(first: str, second: str, threshold: float = 90.0) -> bool:
    """
    Return whether two titles are similar enough to be considered a match.

    Both values are normalized before computing a RapidFuzz ratio. A match is
    reported when the score is greater than or equal to the given threshold.
    """
    return fuzz.ratio(normalize(first), normalize(second)) >= threshold


def contains_term(term: str, text: str) -> bool:
    """
    Match a term inside text using flexible separators.

    Rules:
    - Case insensitive
    - '.' in the term represents a word separator
    - Valid separators in text: '.', ',', '-', whitespace
    - Term must appear as whole tokens
    """

    # Split the term into tokens using periods
    parts = term.lower().split(".")

    # Escape each token
    parts = [re.escape(p) for p in parts]

    # Build separator pattern
    sep = r"[.,\-\s]+"

    # Join tokens with separator
    core = sep.join(parts)

    # Require valid token boundaries
    pattern = rf"(?i)(^|[.,\-\s]){core}($|[.,\-\s])"

    return re.search(pattern, text) is not None


def match_metadata(conn: sqlite3.Connection, name: str, type_: str) -> sqlite3.Row | None:
    """
    Return the first active metadata row of this type whose match pattern
    appears in the torrent name (see contains_term), or None.
    """
    rows = conn.execute(
        "SELECT * FROM metadata WHERE type = ? AND active = 1 ORDER BY id", (type_,)
    ).fetchall()
    return next((row for row in rows if contains_term(row["match_pattern"], name)), None)
