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


class AdminProviderChannelCreate(ApiModel):
    project_name: str = Field(min_length=1, max_length=64, pattern=PROJECT_NAME_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(pattern=r"^(openai|volcengine_ark|aliyun_bailian|minimax)$")
    config: dict[str, Any] = Field(default_factory=dict)
    secret: str = Field(min_length=8, max_length=4096)
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminProviderSecretRotate(ApiModel):
    secret: str = Field(min_length=8, max_length=4096)
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminProviderStatusUpdate(ApiModel):
    enabled: bool
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AdminProviderDelete(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


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


class BillingRateUpdate(ApiModel):
    effective_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    prices: dict[str, Any]
    current_password: str = Field(min_length=1, max_length=128)


class ProjectBillingUpdate(ApiModel):
    effective_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    enabled: bool
    discount_bps: int = Field(default=10000, ge=0, le=10000)
    current_password: str = Field(min_length=1, max_length=128)


class BillingSensitiveAction(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)


class BillingAdjustmentCreate(BillingSensitiveAction):
    amount_yuan: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=500)


class BillingPaymentCreate(BillingSensitiveAction):
    paid_at: str | None = Field(default=None, max_length=40)
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


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


class ProjectModelBinding(ApiModel):
    model: str = Field(min_length=1, max_length=128)
    channel_id: str = Field(min_length=1, max_length=80)
    # Kept temporarily for backward-compatible internal clients. The service
    # deliberately ignores this value and always uses model_catalog.upstream_model.
    upstream_model: str | None = Field(default=None, max_length=256)
    enabled: bool = True


class ProjectModelsUpdate(ApiModel):
    bindings: list[ProjectModelBinding] = Field(default_factory=list, max_length=100)


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
