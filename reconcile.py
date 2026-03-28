#!/usr/bin/env python3
import json
from utils.add_torrents_to_db import add_new_torrents_to_db


def main():

    torrents_dict = add_new_torrents_to_db()
    print(f"Torrents added {json.dumps(torrents_dict, indent=2)}")


if __name__ == "__main__":
    main()

