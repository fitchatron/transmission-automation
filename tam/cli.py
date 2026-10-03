import sqlite3
from typing import Annotated

import typer

from tam import repo
from tam.config import Settings
from tam.db import get_connection, migrate
from tam.log import setup_logging
from tam.queue import QUEUE_FILES, QueueLocked, queue_lock, read_queue, rewrite_queue
from tam.start import FAILED, StartResult, start_queue
from tam.transmission import Transmission, TransmissionUnavailable
from tam.vpn import ensure_vpn

app = typer.Typer(help="Transmission automation.", no_args_is_help=True)
db_app = typer.Typer(help="Database management.", no_args_is_help=True)
media_app = typer.Typer(help="Manage metadata used to route downloads.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(media_app, name="media")


@app.callback()
def main(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
):
    settings = Settings.from_env()
    command = ctx.invoked_subcommand or "tam"
    ctx.obj = {"settings": settings, "log": setup_logging(settings.log_dir, command, verbose)}


def _not_implemented(name: str):
    typer.echo(f"`tam {name}` is not implemented yet.", err=True)
    raise typer.Exit(1)


TYPE_ALIASES = {"tv": "tv-show", "tv-show": "tv-show", "movie": "movie"}
DEFAULT_MOVIE_DEST = "/Movies"


def media_type(value: str) -> str:
    try:
        return TYPE_ALIASES[value.lower()]
    except KeyError:
        raise typer.BadParameter("must be one of: tv, tv-show, movie") from None


def _connect(ctx: typer.Context) -> sqlite3.Connection:
    """Open the database, bringing the schema up to date first."""
    conn = get_connection(ctx.obj["settings"].db_path)
    migrate(conn)
    return conn


@db_app.command("init")
def db_init(ctx: typer.Context):
    """Create or migrate the database schema."""
    settings: Settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    try:
        before, after = migrate(conn)
    finally:
        conn.close()
    if before == after:
        typer.echo(f"{settings.db_path}: schema already at v{after}.")
    else:
        typer.echo(f"{settings.db_path}: migrated schema v{before} -> v{after}.")


@media_app.command("add")
def media_add(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Display title (also the match pattern).")],
    type_: Annotated[str, typer.Argument(metavar="TYPE", help="tv | movie", parser=media_type)],
    destination: Annotated[
        str | None,
        typer.Argument(
            help=f"Destination dir. Required for tv; movies default to {DEFAULT_MOVIE_DEST}."
        ),
    ] = None,
    pattern: Annotated[
        str | None,
        typer.Option(help="Match pattern if different from NAME ('.' matches any separator)."),
    ] = None,
):
    """Add a metadata row used to match torrents to a destination."""
    if destination is None:
        if type_ == "tv-show":
            raise typer.BadParameter("DESTINATION is required for tv", param_hint="DESTINATION")
        destination = DEFAULT_MOVIE_DEST
    pattern = pattern or name

    conn = _connect(ctx)
    try:
        existing = [
            row for row in repo.list_metadata(conn, type_) if row["match_pattern"] == pattern
        ]
        if existing:
            typer.echo(
                f"Active metadata #{existing[0]['id']} already uses pattern '{pattern}'.", err=True
            )
            raise typer.Exit(1)
        metadata_id = repo.add_metadata(conn, name, type_, pattern, destination)
    finally:
        conn.close()
    typer.echo(f"Added metadata #{metadata_id}: '{name}' ({type_}) -> {destination}")


@media_app.command("list")
def media_list(
    ctx: typer.Context,
    all_: Annotated[bool, typer.Option("--all", help="Include disabled rows.")] = False,
):
    """List metadata rows."""
    conn = _connect(ctx)
    try:
        rows = repo.list_metadata(conn, include_inactive=all_)
    finally:
        conn.close()
    if not rows:
        typer.echo("No metadata.")
        return
    typer.echo(f"{'ID':>4}  {'TYPE':<7}  {'ACTIVE':<6}  {'PATTERN':<30}  DESTINATION")
    for row in rows:
        typer.echo(
            f"{row['id']:>4}  {row['type']:<7}  {'yes' if row['active'] else 'no':<6}  "
            f"{row['match_pattern']:<30}  {row['destination_path']}"
        )


@media_app.command("disable")
def media_disable(ctx: typer.Context, metadata_id: int):
    """Deactivate a metadata row."""
    conn = _connect(ctx)
    try:
        found = repo.set_metadata_active(conn, metadata_id, False)
    finally:
        conn.close()
    if not found:
        typer.echo(f"No metadata with id {metadata_id}.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Disabled metadata #{metadata_id}.")


@app.command()
def start(ctx: typer.Context):
    """Add the magnets queued in tv.txt and movies.txt (one magnet per line)."""
    settings: Settings = ctx.obj["settings"]
    log = ctx.obj["log"]

    try:
        with queue_lock(settings.queue_dir):
            results = _run_start(ctx, settings, log)
    except QueueLocked as error:
        typer.echo(f"Skipping: {error}.")
        return

    if results is None:
        return
    for result in results:
        label = result.name or result.hash or result.entry.magnet[:60]
        detail = f"  ({result.error})" if result.error else ""
        typer.echo(f"{result.outcome:<8} {result.entry.type:<8} {label}{detail}")
    if any(r.outcome == FAILED for r in results):
        raise typer.Exit(1)


def _run_start(ctx: typer.Context, settings: Settings, log) -> list[StartResult] | None:
    paths = {settings.queue_dir / name: type_ for name, type_ in QUEUE_FILES.items()}
    entries = [entry for path, type_ in paths.items() for entry in read_queue(path, type_)]
    if not entries:
        typer.echo(f"Queue empty ({', '.join(QUEUE_FILES)} in {settings.queue_dir}).")
        return None

    if not ensure_vpn():
        log.error("VPN not connected; queue left untouched")
        typer.echo("VPN is not connected; nothing added.", err=True)
        raise typer.Exit(1)
    try:
        tm = Transmission.connect(settings)
    except TransmissionUnavailable as error:
        log.error("%s", error)
        typer.echo(f"{error}; nothing added.", err=True)
        raise typer.Exit(1) from None

    conn = _connect(ctx)
    try:
        results = start_queue(conn, tm, entries, settings.metadata_timeout, log)
    finally:
        conn.close()

    for path in paths:
        mine = [r for r in results if r.entry.path == path]
        rewrite_queue(
            path,
            processed={r.entry.magnet for r in mine},
            failures={r.entry.magnet: r.error for r in mine if r.outcome == FAILED},
        )
    return results


@app.command("on-done")
def on_done():
    """Transmission completion hook (reads TR_TORRENT_HASH)."""
    _not_implemented("on-done")


@app.command()
def copy(torrent_hash: str):
    """Copy a finished torrent's video files to their destination."""
    _not_implemented("copy")


@app.command()
def sync():
    """Bring the database up to date with Transmission."""
    _not_implemented("sync")


@app.command()
def cleanup(dry_run: Annotated[bool, typer.Option("--dry-run")] = False):
    """Remove torrents that finished seeding and were copied."""
    _not_implemented("cleanup")


@app.command()
def status():
    """Show tracked torrents and their state."""
    _not_implemented("status")
