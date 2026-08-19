from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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
    upload_max_bytes: int = Field(default=200 * 1024 * 1024, gt=0, le=512 * 1024 * 1024)
    ffprobe_path: str = "ffprobe"
    admin_cookie_secure: bool = True
    admin_session_idle_seconds: int = Field(default=30 * 60, ge=60, le=24 * 60 * 60)
    admin_session_absolute_seconds: int = Field(default=12 * 60 * 60, ge=300, le=7 * 24 * 60 * 60)
    admin_login_window_seconds: int = Field(default=15 * 60, ge=60, le=24 * 60 * 60)
    admin_login_lock_seconds: int = Field(default=15 * 60, ge=60, le=24 * 60 * 60)
    admin_login_max_failures: int = Field(default=5, ge=2, le=20)
    admin_argon2_time_cost: int = Field(default=3, ge=1, le=10)
    admin_argon2_memory_cost: int = Field(default=65536, ge=8192, le=262144)
    admin_argon2_parallelism: int = Field(default=4, ge=1, le=16)
    admin_totp_issuer: str = Field(default="Avatar Proxy", min_length=1, max_length=64)
    admin_totp_encryption_key: SecretStr | None = None
    admin_totp_valid_window: int = Field(default=1, ge=0, le=2)
    admin_backup_enabled: bool = True
    admin_backup_interval_seconds: int = Field(default=24 * 60 * 60, ge=60, le=7 * 24 * 60 * 60)
    admin_backup_retention: int = Field(default=30, ge=2, le=365)
    admin_backup_directory: Path | None = None
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
