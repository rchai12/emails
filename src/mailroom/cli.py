import typer

from mailroom import __version__

app = typer.Typer()


@app.callback()
def _main() -> None:
    """Reads mail, triages it, and asks before anything becomes a task."""


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f"mailroom {__version__}")
