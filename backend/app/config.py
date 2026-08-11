from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    volcengine_access_key: str = ""
    volcengine_secret_key: str = ""
    seedance_ark_api_key: str = ""
    seedance_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    tos_access_key: str = ""
    tos_secret_key: str = ""
    tos_endpoint: str = "tos-cn-beijing.volces.com"
    tos_region: str = "cn-beijing"
    tos_bucket: str = ""
    tos_public_base_url: str = ""
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=50 * 1024 * 1024)
    console_admin_token: str = ""
    database_path: Path = Path("./data/avatar_proxy.db")
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:3002,http://127.0.0.1:3002"
    )
    cors_origin_regex: str = ""
    enable_api_docs: bool = False
    upstream_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_tos_access_key(self) -> str:
        return self.tos_access_key or self.volcengine_access_key

    @property
    def effective_tos_secret_key(self) -> str:
        return self.tos_secret_key or self.volcengine_secret_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
