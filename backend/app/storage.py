import time
import uuid
import re
from pathlib import Path
from urllib.parse import quote

import tos
from anyio import to_thread
from fastapi import UploadFile

from .config import Settings
from .database import Database
from .errors import ApiError
from .security import ApiPrincipal


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith("your_") or normalized.startswith("replace_with")


def content_matches_type(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


class TosStorage:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    async def upload_image(self, file: UploadFile, principal: ApiPrincipal) -> dict[str, str | int]:
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ApiError("仅支持 JPEG、PNG、WebP 图片", 415, "unsupported_image_type")

        content = await file.read(self.settings.upload_max_bytes + 1)
        if not content:
            raise ApiError("上传文件不能为空", 400, "empty_file")
        if len(content) > self.settings.upload_max_bytes:
            raise ApiError("图片超过允许的大小", 413, "file_too_large")
        if not content_matches_type(content, content_type):
            raise ApiError("文件内容与图片类型不匹配", 400, "invalid_image_content")

        settings = self.settings
        if any(is_placeholder(value) for value in [
            settings.effective_tos_access_key,
            settings.effective_tos_secret_key,
            settings.tos_endpoint,
            settings.tos_region,
            settings.tos_bucket,
        ]):
            raise ApiError("服务端尚未完整配置 TOS 对象存储", 503, "tos_not_configured")
        if not BUCKET_NAME_PATTERN.fullmatch(settings.tos_bucket):
            raise ApiError(
                "TOS_BUCKET 格式无效：只能使用小写字母、数字和短横线，长度 3～63 位",
                503,
                "tos_bucket_invalid",
            )

        suffix = ALLOWED_IMAGE_TYPES[content_type]
        original_stem = Path(file.filename or "image").stem[:48]
        safe_stem = "".join(char for char in original_stem if char.isalnum() or char in "-_") or "image"
        object_key = f"avatar-assets/{principal.project_name}/{uuid.uuid4().hex}-{safe_stem}{suffix}"
        client = tos.TosClientV2(
            settings.effective_tos_access_key,
            settings.effective_tos_secret_key,
            settings.tos_endpoint,
            settings.tos_region,
        )

        started = time.monotonic()
        try:
            result = await to_thread.run_sync(
                lambda: client.put_object(
                    settings.tos_bucket,
                    object_key,
                    content=content,
                    content_type=content_type,
                )
            )
        except tos.exceptions.TosServerError as error:
            message = f"TOS 拒绝上传请求：{error.code or 'unknown'}"
            if error.request_id:
                message += f"（RequestId: {error.request_id}）"
            raise ApiError(message, 502, "tos_upload_rejected") from error
        except tos.exceptions.TosClientError as error:
            raise ApiError(f"TOS 客户端配置无效：{error.message}", 502, "tos_upload_failed") from error

        self.database.log_request(
            principal.id,
            principal.project_name,
            "TOS:PutObject",
            200,
            round((time.monotonic() - started) * 1000),
        )
        public_base = settings.tos_public_base_url.strip().rstrip("/")
        if not public_base:
            endpoint_host = settings.tos_endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
            public_base = f"https://{settings.tos_bucket}.{endpoint_host}"
        return {
            "url": f"{public_base}/{quote(object_key, safe='/')}",
            "objectKey": object_key,
            "contentType": content_type,
            "size": len(content),
            "etag": result.etag,
            "requestId": result.request_id,
        }
