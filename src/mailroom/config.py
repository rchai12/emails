import re
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DATA_DIR_MESSAGE = "MAILROOM_DATA_DIR must be an absolute path"
EXTRACTOR_URL_MESSAGE = (
    "MAILROOM_EXTRACTOR_URL must be http:// on 127.0.0.1, localhost or [::1], with no path"
)
TIME_ZONE_MESSAGE = "MAILROOM_TIME_ZONE must be an IANA time zone name"
DISCORD_CHANNEL_MESSAGE = (
    "MAILROOM_DISCORD_CHANNEL_ID must be a Discord channel id (17 to 20 digits)"
)
DISCORD_OWNER_MESSAGE = "MAILROOM_DISCORD_OWNER_ID must be a Discord user id (17 to 20 digits)"
DISCORD_GUILD_MESSAGE = "MAILROOM_DISCORD_GUILD_ID must be a Discord server id (17 to 20 digits)"
GMAIL_ACCOUNTS_MESSAGE = "MAILROOM_GMAIL_ACCOUNTS must be account names separated by commas"
POLL_MESSAGE = "MAILROOM_POLL_SECONDS must be a whole number from 30 to 600"

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_CHANNEL_ID = re.compile(r"[0-9]{17,20}")
_ACCOUNT = re.compile(r"[a-z][a-z0-9-]{0,31}")
_FIELD_MESSAGES = {
    "data_dir": DATA_DIR_MESSAGE,
    "extractor_url": EXTRACTOR_URL_MESSAGE,
    "time_zone": TIME_ZONE_MESSAGE,
    "discord_channel_id": DISCORD_CHANNEL_MESSAGE,
    "discord_owner_id": DISCORD_OWNER_MESSAGE,
    "discord_guild_id": DISCORD_GUILD_MESSAGE,
    "gmail_accounts": GMAIL_ACCOUNTS_MESSAGE,
    "poll_seconds": POLL_MESSAGE,
}


class ConfigError(Exception):
    pass


def _default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "mailroom"


def _loopback_http(value: str) -> bool:
    parsed = urlsplit(value)
    try:
        _port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in _LOOPBACK
        and parsed.username is None
        and not any((parsed.path, parsed.query, parsed.fragment))
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILROOM_")

    data_dir: Path = Field(default_factory=_default_data_dir)
    extractor_url: str = "http://127.0.0.1:11434"
    extractor_model: str = ""
    time_zone: str = ""
    discord_channel_id: str = ""
    discord_owner_id: str = ""
    discord_guild_id: str = ""
    gmail_accounts: Annotated[tuple[str, ...], NoDecode] = ()
    poll_seconds: int = 60

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: object) -> Path:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            raise ValueError(DATA_DIR_MESSAGE)
        return path

    @field_validator("extractor_url")
    @classmethod
    def _check_extractor_url(cls, value: str) -> str:
        if not _loopback_http(value):
            raise ValueError(EXTRACTOR_URL_MESSAGE)
        return value

    @field_validator("time_zone")
    @classmethod
    def _check_time_zone(cls, value: str) -> str:
        if value == "":
            return value
        try:
            _zone = ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(TIME_ZONE_MESSAGE) from None
        return value

    @field_validator("discord_channel_id")
    @classmethod
    def _check_discord_channel_id(cls, value: str) -> str:
        if value == "" or _CHANNEL_ID.fullmatch(value):
            return value
        raise ValueError(DISCORD_CHANNEL_MESSAGE)

    @field_validator("discord_owner_id")
    @classmethod
    def _check_discord_owner_id(cls, value: str) -> str:
        if value == "" or _CHANNEL_ID.fullmatch(value):
            return value
        raise ValueError(DISCORD_OWNER_MESSAGE)

    @field_validator("discord_guild_id")
    @classmethod
    def _check_discord_guild_id(cls, value: str) -> str:
        if value == "" or _CHANNEL_ID.fullmatch(value):
            return value
        raise ValueError(DISCORD_GUILD_MESSAGE)

    @field_validator("gmail_accounts", mode="before")
    @classmethod
    def _check_gmail_accounts(cls, value: object) -> tuple[str, ...]:
        if value == () or value == "":
            return ()
        names = tuple(part.strip() for part in cast(str, value).split(","))
        seen: set[str] = set()
        for name in names:
            if _ACCOUNT.fullmatch(name) is None or name in seen:
                raise ValueError(GMAIL_ACCOUNTS_MESSAGE)
            seen.add(name)
        return names

    @field_validator("poll_seconds")
    @classmethod
    def _check_poll_seconds(cls, value: int) -> int:
        if 30 <= value <= 600:
            return value
        raise ValueError(POLL_MESSAGE)


def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as caught:
        field = caught.errors()[0]["loc"][0]
        raise ConfigError(_FIELD_MESSAGES[str(field)]) from None


def prepare_data_dir(settings: Settings) -> Path:
    folder = settings.data_dir
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)
    return folder
