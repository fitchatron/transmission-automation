#!/bin/sh
# Point Transmission's script-torrent-done-filename at this file.
# Transmission passes TR_TORRENT_HASH (and friends) in the environment.
exec /opt/media-automation/.venv/bin/tam on-done
