import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file="config.env",
                                      env_file_encoding="utf-8", 
                                      populate_by_name=True,   # lets you pass app_name as well as APP_NAME
                                      extra="ignore")

    env: str = Field(..., alias="ENV", description="Runtime environment name (dev/prod/stage)")
    app_name: str = Field(..., alias="APP_NAME", description="Human-friendly service name")
    log_level: str = Field("INFO", alias="LOG_LEVEL", description="Logging level, e.g. INFO, DEBUG")
    Driver: str = Field(..., alias="DRIVER_NAME", description="database driver")
    Server: str = Field(..., alias="SERVER_NAME", description="Server IP or name and Port")
    Database: str = Field(..., alias="DATABASE_NAME", description="database Name")
    Trusted_Connection: str = Field(..., alias="TRUSTED_CONNECTION", description="database Trusted_Connection")
    Encrypt: str = Field(..., alias="ENCRYPT", description="is transport Encrypt")
    TrustServerCertificate: str = Field(..., alias="TRUSTED_SERVER_CERTIFICATE", description="Flag to use TrustServerCertificate")
    username: str = Field(..., alias="USER_NAME", description="database user name")
    password: str = Field(..., alias="PASSWORD", description="database passsword")

    @property
    def cors_origins(self) -> List[str]:
        # Default to localhost for dev if explicit origins are not provided
        if self.allowed_origins_raw:
            return [origin.strip() for origin in self.allowed_origins_raw.split(",") if origin.strip()]
        if self.env.lower() == "dev":
            return ["http://localhost:3000"]
        return []


@lru_cache
def _cached_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    """Return settings, disabling cache in dev for hot reload, caching otherwise."""
    env = os.getenv("ENV", "").lower()
    if env == "dev":
        return Settings()
    return _cached_settings()