import os
import sqlite3
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from tam import repo
from tam.cleanup import cleanup as run_cleanup
from tam.config import Settings
from tam.copy import COPIED, UNTRACKED, CopyResult, copy_torrent
from tam.copy import FAILED as COPY_FAILED
from tam.db import TORRENT_STATUSES, get_connection, migrate
from tam.log import setup_logging
from tam.queue import QUEUE_FILES, QueueLocked, queue_lock, read_queue, rewrite_queue
from tam.start import FAILED, StartResult, start_queue
from tam.sync import SyncReport
from tam.sync import sync as run_sync
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


def _transmission(ctx: typer.Context, note: str = "") -> Transmission:
    """Connect to Transmission or exit 1 with a one-line error."""
    try:
        return Transmission.connect(ctx.obj["settings"])
    except TransmissionUnavailable as error:
        ctx.obj["log"].error("%s", error)
        typer.echo(f"{error}{note}", err=True)
        raise typer.Exit(1) from None


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
    tm = _transmission(ctx, "; nothing added.")

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


def _copy(ctx: typer.Context, torrent_hash: str) -> CopyResult:
    settings: Settings = ctx.obj["settings"]
    log = ctx.obj["log"]
    tm = _transmission(ctx)

    conn = _connect(ctx)
    try:
        result = copy_torrent(conn, tm, settings, torrent_hash.strip().lower(), log)
    finally:
        conn.close()

    if result.outcome == UNTRACKED:
        typer.echo(f"{torrent_hash} is not tracked by tam; nothing to do.")
    elif result.outcome == COPIED:
        typer.echo(
            f"Copied {len(result.copied)} file(s) to {result.destination}"
            + (f" ({len(result.skipped)} already there)" if result.skipped else "")
        )
    else:
        typer.echo(f"Copy failed: {result.error}", err=True)
    return result


@app.command("on-done")
def on_done(ctx: typer.Context):
    """Transmission completion hook: copies the torrent named by TR_TORRENT_HASH."""
    torrent_hash = os.environ.get("TR_TORRENT_HASH", "").strip()
    if not torrent_hash:
        ctx.obj["log"].error("on-done called without TR_TORRENT_HASH")
        typer.echo("TR_TORRENT_HASH is not set; is this running from Transmission?", err=True)
        raise typer.Exit(1)
    ctx.obj["log"].info(
        "Torrent done: %s (%s)", os.environ.get("TR_TORRENT_NAME", "?"), torrent_hash
    )
    if _copy(ctx, torrent_hash).outcome == COPY_FAILED:
        raise typer.Exit(1)


@app.command()
def copy(
    ctx: typer.Context,
    torrent_hash: Annotated[str, typer.Argument(help="Info-hash of the torrent.")],
):
    """Copy a finished torrent's video files to their destination (retry a failed copy)."""
    if _copy(ctx, torrent_hash).outcome == COPY_FAILED:
        raise typer.Exit(1)


@app.command()
def sync(
    ctx: typer.Context,
    copy_pending: Annotated[
        bool,
        typer.Option(
            "--copy-pending", help="Also copy torrents that finished but were never copied."
        ),
    ] = False,
):
    """Bring the database up to date with Transmission."""
    settings: Settings = ctx.obj["settings"]
    tm = _transmission(ctx)
    conn = _connect(ctx)
    try:
        report = run_sync(conn, tm, ctx.obj["log"], settings, copy_pending=copy_pending)
    finally:
        conn.close()

    _print_sync(report)
    if any(result.outcome == COPY_FAILED for _, result in report.copies):
        raise typer.Exit(1)


def _print_sync(report: SyncReport) -> None:
    typer.echo(f"Checked {report.checked} tracked torrent(s).")
    for change in report.changes:
        typer.echo(f"  {change.old:>11} -> {change.new:<11} {change.name or change.hash}")
    for hash_, result in report.copies:
        detail = result.destination if result.outcome == COPIED else result.error
        typer.echo(f"  copy {result.outcome:<9} {hash_}  {detail}")
    if report.untracked:
        typer.echo(f"{len(report.untracked)} torrent(s) in Transmission not tracked by tam:")
        for info in report.untracked:
            typer.echo(f"  {info.hash}  {info.name}")


@app.command()
def cleanup(
    ctx: typer.Context,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be removed; change nothing.")
    ] = False,
):
    """Sync, then remove copied torrents (and their data) that finished seeding."""
    settings: Settings = ctx.obj["settings"]
    tm = _transmission(ctx)
    conn = _connect(ctx)
    try:
        report = run_cleanup(conn, tm, settings, ctx.obj["log"], dry_run=dry_run)
    finally:
        conn.close()

    _print_sync(report.sync)
    if not report.seed_limits_configured:
        typer.echo(
            "Warning: Transmission has no seed ratio or idle limit enabled, so torrents "
            "may never finish seeding. Set them in Transmission's preferences.",
            err=True,
        )
    verb = "Would remove" if dry_run else "Removed"
    typer.echo(f"{verb} {len(report.removed)} finished torrent(s) and their data:")
    for hash_, name in report.removed:
        typer.echo(f"  {name or hash_}")
    if report.still_seeding:
        typer.echo(f"{report.still_seeding} copied torrent(s) still seeding.")
    for hash_, error in report.errors:
        typer.echo(f"Failed to remove {hash_}: {error}", err=True)
    copy_failed = any(r.outcome == COPY_FAILED for _, r in report.sync.copies)
    if report.errors or copy_failed:
        raise typer.Exit(1)


STATUS_STYLES = {
    "copied": "green",
    "removed": "dim",
    "failed": "red",
    "missing": "yellow",
    "downloaded": "cyan",
}


@app.command()
def status(
    ctx: typer.Context,
    all_: Annotated[bool, typer.Option("--all", help="Include removed torrents.")] = False,
):
    """Show tracked torrents and their state (as of the last sync)."""
    conn = _connect(ctx)
    try:
        statuses = None if all_ else [s for s in TORRENT_STATUSES if s != "removed"]
        rows = repo.list_torrents(conn, statuses)
        destinations = {
            m["id"]: m["destination_path"] for m in repo.list_metadata(conn, include_inactive=True)
        }
    finally:
        conn.close()

    if not rows:
        typer.echo("No tracked torrents.")
        return
    table = Table(box=None, header_style="bold")
    for column in ("Status", "Type", "Done", "Name", "Destination", "Hash"):
        table.add_column(column, no_wrap=column in ("Status", "Hash"))
    for row in rows:
        style = STATUS_STYLES.get(row["status"], "")
        table.add_row(
            f"[{style}]{row['status']}[/]" if style else row["status"],
            row["type"],
            f"{row['percent_done'] * 100:.0f}%",
            escape(row["name"] or "(resolving)"),
            escape(destinations.get(row["metadata_id"], "(default)")),
            row["hash"][:8],
        )
        if row["status"] == "failed" and row["error"]:
            table.add_row("", "", "", f"[red]{escape(row['error'])}[/]", "", "")
    Console().print(table)
