from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR_MESSAGE = "MAILROOM_DATA_DIR must be an absolute path"
EXTRACTOR_URL_MESSAGE = (
    "MAILROOM_EXTRACTOR_URL must be http:// on 127.0.0.1, localhost or [::1], with no path"
)
TIME_ZONE_MESSAGE = "MAILROOM_TIME_ZONE must be an IANA time zone name"

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_FIELD_MESSAGES = {
    "data_dir": DATA_DIR_MESSAGE,
    "extractor_url": EXTRACTOR_URL_MESSAGE,
    "time_zone": TIME_ZONE_MESSAGE,
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
