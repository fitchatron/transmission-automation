#!/usr/bin/env -S uv run

import argparse
import sqlite3
import sys

from utils.db import get_connection


def parse_args():
    parser = argparse.ArgumentParser(
        description="Insert a metadata row for a movie or tv-show."
    )
    parser.add_argument("name", help="Display title and match pattern.")
    parser.add_argument(
        "media_type",
        choices=["tv-show", "movie"],
        help="Media type.",
    )
    parser.add_argument(
        "destination",
        nargs="?",
        help="Destination directory. Optional for movie (defaults to /Movies).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.media_type == "movie":
        destination = args.destination or "/Movies"
    elif args.destination:
        destination = args.destination
    else:
        print("destination is required for media_type 'tv-show'")
        sys.exit(1)

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO metadata (title, type, match_pattern, destination_path)
            VALUES (?, ?, ?, ?)
            """,
            (args.name, args.media_type, args.name, destination),
        )
        conn.commit()
    except sqlite3.Error as error:
        conn.rollback()
        print(f"Failed to insert metadata: {error}")
        sys.exit(1)
    finally:
        conn.close()

    print(f"Inserted metadata for '{args.name}' ({args.media_type}) -> {destination}")


if __name__ == "__main__":
    main()
