from typing import Annotated

import typer

from tam.config import Settings
from tam.log import setup_logging

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


@db_app.command("init")
def db_init():
    """Create or migrate the database schema."""
    _not_implemented("db init")


@media_app.command("add")
def media_add(name: str, media_type: str, destination: str | None = None):
    """Add a metadata row used to match torrents to a destination."""
    _not_implemented("media add")


@media_app.command("list")
def media_list():
    """List metadata rows."""
    _not_implemented("media list")


@media_app.command("disable")
def media_disable(metadata_id: int):
    """Deactivate a metadata row."""
    _not_implemented("media disable")


@app.command()
def start():
    """Add the magnets queued in tv.txt and movies.txt."""
    _not_implemented("start")


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
