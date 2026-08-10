from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    volcengine_access_key: str = ""
    volcengine_secret_key: str = ""
    console_admin_token: str = ""
    database_path: Path = Path("./data/avatar_proxy.db")
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    upstream_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
