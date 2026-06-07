#!/usr/bin/env python3

import argparse
import sys

from utils.db import get_connection


def parse_args():
    parser = argparse.ArgumentParser(
        description="Insert a metadata row for a movie or tv-show."
    )
    parser.add_argument("name", help="Display title and match pattern.")
    parser.add_argument("type", choices=["tv-show", "movie"], help="Media type.")
    parser.add_argument(
        "destination",
        nargs="?",
        help="Destination directory. Optional for movie (defaults to /Movies).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.type == "movie":
        destination = args.destination or "/Movies"
    elif args.destination:
        destination = args.destination
    else:
        print("destination is required for tv-show")
        sys.exit(1)

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO metadata (title, type, match_pattern, destination_path)
            VALUES (?, ?, ?, ?)
            """,
            (args.name, args.type, args.name, destination),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Inserted metadata for '{args.name}' ({args.type}) -> {destination}")


if __name__ == "__main__":
    main()
