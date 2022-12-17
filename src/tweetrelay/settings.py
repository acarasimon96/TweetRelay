from functools import lru_cache

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """
    Reads application settings from a file and stores them into an encapsulated object.
    Currently, only reading from files named `.env` in the current working directory
    is supported.
    """

    bearer_token: str
    host: str = "127.0.0.1"
    port: int = 8000
    logfile_level: str = "DEBUG"
    recent_events_file: str = "recent_events.json"

    @validator("logfile_level")
    def log_level_is_valid(cls, value: str):
        value = value.strip().upper()
        if value not in ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError(
                "Value must be either one of the following: "
                "TRACE, DEBUG, INFO, WARNING, ERROR"
            )
        return value

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()  # type: ignore
