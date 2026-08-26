from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROJECT_NAME_PATTERN = r"^[A-Za-z0-9._-]+$"


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


ADMIN_USERNAME_PATTERN = r"^[A-Za-z0-9._-]+$"


class AdminLogin(ApiModel):
    username: str = Field(min_length=3, max_length=64, pattern=ADMIN_USERNAME_PATTERN)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")
    recovery_code: str | None = Field(default=None, min_length=16, max_length=32, pattern=r"^[A-Za-z2-7-]+$")


class AdminPasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=14, max_length=128)


class AdminUserCreate(ApiModel):
    username: str = Field(min_length=3, max_length=64, pattern=ADMIN_USERNAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=64)
    current_password: str = Field(min_length=1, max_length=128)


class AdminSensitiveAction(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)


class AdminTotpConfirm(ApiModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminTotpRotationStart(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    current_totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminTotpRotationConfirm(ApiModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminSecurityAlertAck(ApiModel):
    alert_id: int = Field(ge=1)


class AdminDatabaseRestore(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    confirmation: str = Field(min_length=1, max_length=32)


class AdminSystemMonitorSettingsUpdate(ApiModel):
    enabled: bool
    warning_percent: float = Field(ge=1, le=99)
    critical_percent: float = Field(ge=1, le=99)
    emergency_percent: float = Field(ge=1, le=100)
    recovery_percent: float = Field(ge=0, le=98)
    current_password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "AdminSystemMonitorSettingsUpdate":
        if not (
            self.recovery_percent < self.warning_percent
            < self.critical_percent
            < self.emergency_percent
        ):
            raise ValueError("恢复、预警、严重和紧急阈值必须依次递增")
        return self


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=64, pattern=PROJECT_NAME_PATTERN)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str = Field(default="", max_length=128)

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None


class ProjectDelete(ApiModel):
    name: str = Field(min_length=1, max_length=64, pattern=PROJECT_NAME_PATTERN)


class ApiKeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    project_name: str = Field(min_length=1, max_length=64, pattern=PROJECT_NAME_PATTERN)


class ApiKeyDisable(ApiModel):
    key_id: str = Field(min_length=1)


class ApiKeyEnable(ApiModel):
    key_id: str = Field(min_length=1)


class ApiKeyDelete(ApiModel):
    key_id: str = Field(min_length=1)


class ApiKeyBindProject(ApiModel):
    key_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1, max_length=64, pattern=PROJECT_NAME_PATTERN)


class ProjectQuotaUpdate(ApiModel):
    project_name: str = Field(min_length=1, max_length=64, pattern=PROJECT_NAME_PATTERN)
    enabled: bool = False
    read_qpm: int | None = Field(default=None, ge=1)
    write_qpm: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)
    daily_asset_creates: int | None = Field(default=None, ge=1)
    daily_upload_files: int | None = Field(default=None, ge=1)
    daily_upload_bytes: int | None = Field(default=None, ge=1)
    total_assets: int | None = Field(default=None, ge=1)
    total_storage_bytes: int | None = Field(default=None, ge=1)


class ApiKeyQuotaUpdate(ApiModel):
    key_id: str = Field(min_length=1)
    read_qpm: int | None = Field(default=None, ge=1)
    write_qpm: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)
    daily_asset_creates: int | None = Field(default=None, ge=1)
    daily_upload_files: int | None = Field(default=None, ge=1)
    daily_upload_bytes: int | None = Field(default=None, ge=1)


class QuotaEventAck(ApiModel):
    event_id: int = Field(ge=1)


class AssetGroupCreate(ApiModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)


class AssetGroupUpdate(ApiModel):
    group_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_change(self) -> "AssetGroupUpdate":
        if self.name is None and self.description is None:
            raise ValueError("name 和 description 至少提供一个")
        return self


class AssetType(str, Enum):
    IMAGE = "Image"
    VIDEO = "Video"
    AUDIO = "Audio"


class AssetCreate(ApiModel):
    group_id: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2048, pattern=r"^https?://")
    asset_type: AssetType = AssetType.IMAGE
    name: str | None = Field(default=None, max_length=64)
    upload_id: str | None = Field(default=None, min_length=1, max_length=64)


class AssetUpdate(ApiModel):
    asset_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)


class VideoTaskMetadata(ApiModel):
    prompt: str = Field(default="", max_length=2000)
    prompt_document: str | None = Field(default=None, max_length=20000)
    assets: list[dict[str, Any]] = Field(default_factory=list, max_length=9)
    duration_mode: str | None = Field(default=None, pattern=r"^(seconds|smart)$")
    generation_count: int | None = Field(default=None, ge=1, le=4)


class VideoHistoryRecord(ApiModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    created_at: int = Field(default=0, ge=0)
    prompt: str = Field(default="视频生成任务", max_length=2000)
    prompt_document: str | None = Field(default=None, max_length=20000)
    asset_name: str | None = Field(default=None, max_length=128)
    asset_names: list[str] | None = Field(default=None, max_length=9)
    assets: list[dict[str, Any]] | None = Field(default=None, max_length=9)
    model: str | None = Field(default=None, max_length=128)
    ratio: str | None = Field(default=None, max_length=16)
    duration: int | None = Field(default=None, ge=1, le=60)
    duration_mode: str | None = Field(default=None, pattern=r"^(seconds|smart)$")
    resolution: str | None = Field(default=None, max_length=16)
    generation_count: int | None = Field(default=None, ge=1, le=4)
    generate_audio: bool | None = None
    status: str | None = Field(default=None, max_length=32)
    video_url: str | None = Field(default=None, max_length=4096)
    last_frame_url: str | None = Field(default=None, max_length=4096)


class VideoHistoryImport(ApiModel):
    tasks: list[VideoHistoryRecord] = Field(default_factory=list, max_length=100)


class VideoGenerate(ApiModel):
    model: str = Field(min_length=1)
    content: list[dict[str, Any]] = Field(min_length=1)
    callback_url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    return_last_frame: bool | None = None
    generate_audio: bool | None = None
    ratio: str | None = Field(default=None, min_length=1, max_length=16)
    duration: int | None = Field(default=None, ge=1, le=60)
    resolution: str | None = Field(default=None, min_length=1, max_length=16)
    seed: int | None = None
    camera_fixed: bool | None = None
    watermark: bool | None = None
    service_tier: str | None = Field(default=None, min_length=1, max_length=32)
    metadata: VideoTaskMetadata | None = None

    @model_validator(mode="after")
    def validate_content(self) -> "VideoGenerate":
        text_items = [item for item in self.content if item.get("type") == "text"]
        image_items = [item for item in self.content if item.get("type") == "image_url"]
        if not any(isinstance(item.get("text"), str) and item["text"].strip() for item in text_items):
            raise ValueError("content 至少包含一项非空文本描述")
        if len(image_items) > 9:
            raise ValueError("单个视频任务最多使用 9 张参考图片")
        for item in image_items:
            image_url = item.get("image_url")
            if not isinstance(image_url, dict) or not isinstance(image_url.get("url"), str) or not image_url["url"].strip():
                raise ValueError("参考图片缺少有效的 image_url.url")
        return self
