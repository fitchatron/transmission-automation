import re
from pathlib import Path
from rapidfuzz import fuzz

DEFAULT_DEST = Path("/mnt/ds223j/incoming")


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


def find_metadata(conn, normalized_title: str, type_: str):
    """
    Find the first metadata row matching a normalized torrent title.

    Looks up active metadata candidates by type and returns a tuple of
    (metadata_id, destination_path) when a row's match pattern is contained in
    the normalized title. If no row matches, falls back to the default
    destination and a None metadata_id.
    """
    cursor = conn.execute(
        """
        SELECT id, match_pattern, destination
        FROM metadata
        WHERE type = ?
    """,
        (type_,),
    )

    for metadata_id, pattern, dest in cursor.fetchall():
        if pattern in normalized_title:
            return metadata_id, Path(dest)

    return None, DEFAULT_DEST
