#!/usr/bin/env python3
import json
import logging
import re
import subprocess
import sys
from utils.add_torrents_to_db import add_new_torrents_to_db
from utils.transmission import add_torrent
from utils.vpn import start_vpn, is_vpn_connected

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filename="/opt/media-automation/logs/start_torrent.log",
)


def start_vpn():
    subprocess.run(["nordvpn", "connect"], check=False)


def main():
    if len(sys.argv) != 3:
        print("Usage: start_torrent.py <type> <magnet>")
        sys.exit(1)

    torrent_type = sys.argv[1]
    magnet = sys.argv[2]

    if not is_vpn_connected():
        start_vpn()

    if not is_vpn_connected():
        print("Failed to connect to VPN. Aborting.")
        sys.exit(1)

    add_torrent(logging, magnet)

    inserted_torrents = add_new_torrents_to_db(logging, magnet, torrent_type)
    logging.info(f"Torrents added {json.dumps(inserted_torrents, indent=2)}")


if __name__ == "__main__":
    main()

