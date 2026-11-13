import signal
import threading
import webbrowser

import typer

from mailroom import __version__, commands, discord_post, gmail_login, service
from mailroom import discord_layout as L
from mailroom.config import ConfigError, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.gmail import GmailError
from mailroom.keychain import KeychainError

app = typer.Typer()


@app.callback()
def _main() -> None:
    """Reads mail, triages it, and asks before anything becomes a task."""


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f"mailroom {__version__}")


@app.command("gmail-login")
def gmail_login_command(account: str, new_client: bool = False) -> None:
    """Sign in to one Gmail account and store its refresh token."""

    def open_browser(address: str) -> None:
        typer.echo("Opening Google sign-in. If no browser opens, visit:")
        typer.echo(address)
        webbrowser.open(address)

    try:
        signed_in = gmail_login.login(
            account,
            gmail_login.new_http(),
            ask=lambda label: typer.prompt(label, hide_input=True),
            open_browser=open_browser,
            new_client=new_client,
        )
    except (gmail_login.LoginError, GmailError, KeychainError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Signed in: {account} ({signed_in})")


@app.command("discord-commands")
def discord_commands() -> None:
    """Register the slash commands in your server."""
    try:
        count = _registered()
    except (DiscordUnavailable, KeychainError, ConfigError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(L.REGISTERED_TEXT.format(count=count))


def _registered() -> int:
    settings = get_settings()
    http = discord_post.open_discord_http()
    try:
        return commands.register_commands(settings, http)
    finally:
        http.close()


@app.command()
def run() -> None:
    """Run the mail service until it is stopped."""
    try:
        settings = get_settings()
    except ConfigError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    stop = threading.Event()

    def _stop(_number: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        service.run_service(settings, say=lambda line: typer.echo(line, err=True), stop=stop)
    except (service.ServiceError, ConfigError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
