import logging
from typing import Literal
from utils.media import contains_term
from utils.transmission import list_torrents
from utils.db import get_connection


def add_new_torrents_to_db(
    logger: logging.Logger, magnet_link: str, type: Literal["tv-show", "movie"]
):
    torrents = list_torrents(logger)

    if not torrents:
        raise RuntimeError("No torrents found after adding new torrent.")

    conn = get_connection()
    inserted_ids: list[int] = []
    for torrent in torrents:
        # fmt: off
        # import pdb; pdb.set_trace()
        # fmt: on

        logger.info(
            f"Processing torrent ID {torrent['id']} with name: {torrent['name']}"
        )
        cursor = conn.execute(
            """
                SELECT id 
                FROM torrents
                WHERE transmission_id = ? and name = ?
                ORDER BY created_at DESC
            """,
            (torrent["id"], torrent["name"]),
        )
        row = cursor.fetchone()
        if row:
            logger.info(
                f"Torrent with ID {torrent['id']} and name '{torrent['name']}' already exists in the database. Skipping."
            )
        else:
            logger.info(
                f"New torrent found: ID {torrent['id']}, name '{torrent['name']}'. Adding to database."
            )
            # fmt: off
            # import pdb; pdb.set_trace()
            # fmt: on

            cursor = conn.execute(
                """
                    SELECT id, title, match_pattern
                    FROM metadata
                    WHERE type = ? and active = 1
                """,
                (type,),
            )

            active_metadata = cursor.fetchall()
            matching_metadata = next(
                (m for m in active_metadata if contains_term(m[2], torrent["name"])),
                None,
            )

            metadata_id = (
                matching_metadata[0] if matching_metadata is not None else None
            )
            logger.info(
                "Torrent for %s has been added",
                (
                    matching_metadata[1]
                    if metadata_id
                    else "Torrent with no matching metadata added"
                ),
            )

            conn.execute(
                """
                  INSERT INTO torrents (
                      transmission_id,
                      name,
                      metadata_id,
                      magnet_link,
                      status
                  )
                  VALUES (?, ?, ?, ?, ?);
                """,
                (
                    torrent["id"],
                    torrent["name"],
                    metadata_id,
                    magnet_link,
                    "added",
                ),
            )
            inserted_ids.append(torrent["id"])

    conn.commit()
    conn.close()
    return inserted_ids

