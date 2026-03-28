import logging
import subprocess
import re


def list_torrents(logger: logging.Logger) -> list[dict]:
    result = subprocess.run(
        ["transmission-remote", "-l"], capture_output=True, text=True
    )

    headers = ["id", "done", "have", "eta", "up", "down", "ratio", "status", "name"]
    torrents: list[dict] = []
    lines = result.stdout.splitlines()

    for idx, line in enumerate(lines):
        if idx == 0 or idx == len(lines) - 1:
            continue

        # Split on 2+ spaces to handle columns with spaces in them
        parts = re.split(r"\s{2,}", line.strip())

        if len(parts) != len(headers):
            print(f"Unexpected line format: {line}")
            logger.error(f"Unexpected line format: {line}")
            continue
        torrent = dict(zip(headers, parts))
        torrents.append(torrent)

    return torrents


def add_torrent(logger: logging.Logger, magnet: str):
    result = subprocess.run(
        ["transmission-remote", "-a", magnet], capture_output=True, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    output = result.stdout.strip()

    match = re.search(r"responded: \"success\"", output)
    if not match:
        raise RuntimeError(f"Could not parse torrent ID from: {output}")

    logger.info(f"Torrent added successfully: {output}")


def remove_torrent(logger: logging.Logger, torrent_id: str):
    subprocess.run(["transmission-remote", "-t", torrent_id, "-r"], check=False)
    logger.info(f"Torrent removed successfully: {torrent_id}")

