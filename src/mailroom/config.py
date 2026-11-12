from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR_MESSAGE = "MAILROOM_DATA_DIR must be an absolute path"


class ConfigError(Exception):
    pass


def _default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "mailroom"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILROOM_")

    data_dir: Path = Field(default_factory=_default_data_dir)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: object) -> Path:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            raise ValueError(DATA_DIR_MESSAGE)
        return path


def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError:
        raise ConfigError(DATA_DIR_MESSAGE) from None


def prepare_data_dir(settings: Settings) -> Path:
    folder = settings.data_dir
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)
    return folder
