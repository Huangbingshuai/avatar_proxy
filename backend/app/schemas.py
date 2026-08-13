from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ProjectCreate(ApiModel):
    name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_-]+$")
    display_name: str | None = Field(default=None, max_length=100)
    description: str = Field(default="", max_length=500)


class ProjectDelete(ApiModel):
    name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_-]+$")


class ApiKeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    project_name: str = Field(default="avatar-proxy", min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_-]+$")


class ApiKeyDisable(ApiModel):
    key_id: str = Field(min_length=1)


class ApiKeyEnable(ApiModel):
    key_id: str = Field(min_length=1)


class ApiKeyDelete(ApiModel):
    key_id: str = Field(min_length=1)


class ApiKeyBindProject(ApiModel):
    key_id: str = Field(min_length=1)
    project_name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_-]+$")


class ProjectQuotaUpdate(ApiModel):
    project_name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_-]+$")
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


class AssetCreate(ApiModel):
    group_id: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2048, pattern=r"^https?://")
    name: str | None = Field(default=None, max_length=128)
    upload_id: str | None = Field(default=None, min_length=1, max_length=64)


class AssetUpdate(ApiModel):
    asset_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=128)


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
