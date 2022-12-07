from functools import lru_cache

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    bearer_token: str
    host: str = "127.0.0.1"
    port: int = 8000
    logfile_level: str = "DEBUG"

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


@lru_cache
def get_settings():
    return Settings()  # type: ignore
