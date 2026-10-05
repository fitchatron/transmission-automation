# Transmission Automation

`tam` queues magnet links into Transmission and copies finished downloads to your media folders. It also removes torrents once they've finished seeding, and keeps a small SQLite database in step with Transmission.

Every torrent is tracked by its **info-hash**, which never changes, rather than its name, which does once a magnet's metadata resolves. So each torrent gets exactly one database row, and the completion hook always finds it.

## Install

Needs [uv](https://docs.astral.sh/uv/), a running `transmission-daemon` with RPC enabled, and `nordvpn` (the VPN is required before anything is added). uv fetches Python 3.12+ itself if the system doesn't have it.

```bash
cd /path/to/transmission-automation
UV_PROJECT_ENVIRONMENT=/opt/media-automation/.venv uv sync --no-dev --frozen
/opt/media-automation/.venv/bin/tam db init
```

This installs `tam` at `/opt/media-automation/.venv/bin/tam`, with the exact versions pinned in `uv.lock`. The hook script and the cron lines below use that path.

To update: `git pull`, then run the same `uv sync` command again.

If the repo itself is cloned at `/opt/media-automation`, that is already uv's default `.venv` location, so `UV_PROJECT_ENVIRONMENT` is optional. Your database, `logs/` and `queue/` then live inside the checkout; git ignores them all.

### Putting `tam` on your PATH

The venv's `bin` folder isn't on your PATH, so a bare `tam` won't be found. Link it into a folder that is:

```bash
sudo ln -s /opt/media-automation/.venv/bin/tam /usr/local/bin/tam
```

The link survives `uv sync` and works for every user. Alternatively, add `export PATH="/opt/media-automation/.venv/bin:$PATH"` to your `~/.bashrc`.

Avoid plain `uv run tam …` on the server: `uv run` syncs the dev tools (pytest, ruff) into the venv first. If you want to use it, run `uv run --no-dev tam …`.

Keep the full path in cron and in `scripts/transmission-done.sh`, because they run with a minimal PATH.

`tam db init` creates the database, or upgrades an existing one in place. If you're upgrading from the old scripts, the old `torrents` table is kept as `torrents_legacy` and your `metadata` rows are kept as they are. Every other command also brings the schema up to date before it runs.

<details>
<summary>Without uv</summary>

```bash
python3.12 -m venv /opt/media-automation/.venv
/opt/media-automation/.venv/bin/pip install -e /path/to/transmission-automation
```

This doesn't use the lockfile, so you get the newest versions allowed by `pyproject.toml`.
</details>

## Configuration

Settings are read from environment variables. `tam` also loads `/opt/media-automation/.env`, or the file named by `TAM_ENV_FILE`. Variables already set in the environment take precedence. See [`.env.example`](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `TAM_DB_PATH` | `/opt/media-automation/torrentdata.db` | SQLite database |
| `TAM_QUEUE_DIR` | `/opt/media-automation/queue` | Where `tv.txt` and `movies.txt` live |
| `TAM_LOG_DIR` | `/opt/media-automation/logs` | `tam.log` is written here |
| `TAM_DEFAULT_DEST` | `/mnt/ds223j/Incoming` | Destination when no metadata matches, or its folder is missing |
| `TAM_METADATA_TIMEOUT` | `120` | Seconds `tam start` waits for torrent names to resolve |
| `TAM_VIDEO_EXTS` | `.mp4,.mkv` | File types that get copied |
| `TRANSMISSION_HOST` / `TRANSMISSION_PORT` | `localhost` / `9091` | Transmission RPC |
| `TRANSMISSION_USER` / `TRANSMISSION_PASS` | unset | RPC credentials, if enabled |

## Day to day

### 1. Tell tam where things go

```bash
tam media add "Rick and Morty" tv /TV/Rick --pattern Rick.and.Morty
tam media add "The Matrix" movie            # movies default to /Movies
tam media list                               # --all includes disabled rows
tam media disable 3
```

A torrent is sent to the first active entry of its type whose pattern appears in the torrent's name. In a pattern, `.` matches any separator (`.`, `,`, `-` or a space), and matching ignores case. Torrents with no match go to `TAM_DEFAULT_DEST`.

### 2. Queue magnets

Add magnet links to the queue files, one per line. The file a line is in decides its type:

```
/opt/media-automation/queue/tv.txt       # tv shows
/opt/media-automation/queue/movies.txt   # movies
```

Blank lines and lines starting with `#` are ignored. Then run:

```bash
tam start
```

- The VPN is checked first. If it isn't connected, or Transmission is unreachable, nothing is added and the files are left alone.
- Magnets already tracked, or repeated in the same run, are skipped.
- `tam start` waits (up to `TAM_METADATA_TIMEOUT`) for the real torrent names, then records **one row per torrent**. If a name doesn't arrive in time, the row is recorded anyway and `tam sync` fills the name in later.
- Lines that were added are removed from the file. Lines that failed stay, with a `# error: … (timestamp)` comment under them, and are retried next run. Lines you add while it's running are kept.

### 3. Completed downloads are copied automatically

When a download finishes, Transmission runs `tam on-done` (see [Transmission setup](#transmission-setup)). It finds the torrent by hash and copies its video files (sample clips are skipped) to the matched destination. Each file is written as `<name>.part` and then renamed. The torrent keeps seeding.

To retry a failed copy by hand:

```bash
tam copy <info-hash>
```

### 4. Keep the database in sync, and clean up

```bash
tam status                  # tracked torrents, as of the last sync (--all includes removed)
tam sync                    # update progress/names; rows gone from Transmission become missing or removed
tam sync --copy-pending     # ...and copy anything that finished but was never copied
tam cleanup --dry-run       # show which finished seeds would be removed
tam cleanup                 # sync, copy pending, then remove finished seeds and their data
```

`tam cleanup` only removes torrents that were **copied** and that Transmission reports as finished, meaning they reached the seed ratio or idle limit. Torrents in Transmission that tam didn't add are listed by `sync` but never touched.

A torrent moves through these statuses: `added → downloading → downloaded → copied → removed`. There are also two side states: `failed` (the reason is shown by `tam status`) and `missing` (gone from Transmission before it was copied).

## Transmission setup

Stop the daemon before editing `settings.json`, or it will overwrite your changes:

```json
"script-torrent-done-enabled": true,
"script-torrent-done-filename": "/path/to/transmission-automation/scripts/transmission-done.sh",
"ratio-limit-enabled": true,
"ratio-limit": 2,
"idle-seeding-limit-enabled": true,
"idle-seeding-limit": 60
```

`scripts/transmission-done.sh` runs `/opt/media-automation/.venv/bin/tam on-done`. Edit it if your venv lives elsewhere. Transmission must be able to execute it.

Turn on a seed ratio and/or idle limit; without one, torrents never finish and `tam cleanup` has nothing to remove. It warns you when neither is enabled.

## Cron

```cron
*/15 * * * * /opt/media-automation/.venv/bin/tam start
0 * * * *    /opt/media-automation/.venv/bin/tam cleanup
```

Both commands exit non-zero when something fails, so cron will email you. Overlapping `tam start` runs are prevented by a lock file in the queue folder.

## Development

```bash
uv sync                      # creates ./.venv with the dev tools (pytest, ruff)
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run tam --help            # run the CLI from the checkout
```

After changing dependencies in `pyproject.toml`, run `uv lock` and commit `uv.lock`.

The tests use a fake Transmission client and temporary directories, so they need neither Transmission nor the VPN.
