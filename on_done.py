#!/usr/bin/env python3

import os
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime

from utils.media import find_metadata
from utils.transmission import remove_torrent
from utils.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filename="/opt/media-automation/logs/on_done.log",
)

DEFAULT_DEST = Path("/mnt/ds223j/Incoming")


def main():
    torrent_id = os.environ.get("TR_TORRENT_ID")
    torrent_name = os.environ.get("TR_TORRENT_NAME")
    torrent_dir = os.environ.get("TR_TORRENT_DIR")
    status = "moved"

    try:
        if not all([torrent_id, torrent_name, torrent_dir]):
            logging.error("Missing required Transmission environment variables.")
            return

        conn = get_connection()

        # Remove torrent from Transmission
        # remove_torrent(logging, torrent_id)

        # Fetch torrent record
        row = conn.execute(
            """
                SELECT 
                  t.id
                  , m.destination_path
                FROM torrents t
                LEFT JOIN metadata m ON t.metadata_id = m.id
                WHERE t.transmission_id = ? and t.name like ?
                LIMIT 1
            """,
            (torrent_id, f"{torrent_name[:-4]}%"),
        ).fetchone()

        if not row:
            logging.error(f"No DB entry found for torrent: {torrent_name}")
            return

        torrent_db_id, destination_path = row

        source_path = Path(torrent_dir) / torrent_name

        if not source_path.exists():
            logging.error(f"Source does not exist: {source_path}")
            status = "failed"

        destination_dir = (
            Path(destination_path) if destination_path is not None else DEFAULT_DEST
        )

        if not destination_dir.exists():
            logging.error(
                f"destination does not exist: {destination_path}. Setting to {DEFAULT_DEST}"
            )
            destination_dir = DEFAULT_DEST
        # check if torrent is file or dir
        # if file, continue,
        # else directory, go down one level and get file
        # target_path = source_path / torrent_name

        if source_path.is_dir():
            file = next(
                (
                    item
                    for item in source_path.iterdir()
                    if item.is_file()
                    and item.suffix in [".mkv", ".mp4"]
                    and item.name == torrent_name
                ),
                None,
            )

            if file is None:
                logging.error(f"Source file does not exist: {source_path}")
                status = "failed"
            # else:
            # file_name = f"{file.name}/{file.suffix}"
            # target_path = source_path / file_name

        if status == "failed":
            now = datetime.now()
            conn.execute(
                """
                    UPDATE torrents
                    SET status = ?,
                        completed_at = ?,
                        modified_at = ?,
                    WHERE id = ?
                """,
                (status, now, now, torrent_db_id),
            )
            conn.commit()
            logging.info(f"Completed processing for: {torrent_name}")
            return

        # copy file from source to destination
        shutil.copy(str(source_path), str(destination_dir))

        # delete at source
        # shutil.rmtree(str(source_path))

        # Update DB
        now = datetime.now()
        conn.execute(
            """
                UPDATE torrents
                SET status = ?,
                    completed_at = ?,
                    modified_at = ?,
                WHERE id = ?
            """,
            (status, now, now, torrent_db_id),
        )

        conn.commit()
        logging.info(f"Completed processing for: {torrent_name}")

    except Exception as e:
        logging.exception(f"Error processing torrent: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    main()

