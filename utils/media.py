import re
from pathlib import Path

DEFAULT_DEST = Path("/mnt/ds223j/incoming")


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


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

