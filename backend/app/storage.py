import asyncio
import logging
import re
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import tos
from anyio import to_thread
from fastapi import UploadFile

from .config import Settings
from .database import Database
from .errors import ApiError
from .quota import QuotaManager
from .security import ApiPrincipal


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
logger = logging.getLogger(__name__)


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
    def __init__(self, settings: Settings, database: Database, quota: QuotaManager) -> None:
        self.settings = settings
        self.database = database
        self.quota = quota

    def _client(self) -> tos.TosClientV2:
        settings = self.settings
        return tos.TosClientV2(
            settings.effective_tos_access_key,
            settings.effective_tos_secret_key,
            settings.tos_endpoint,
            settings.tos_region,
        )

    def _validate_configuration(self) -> None:
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
            raise ApiError("TOS_BUCKET 格式无效", 503, "tos_bucket_invalid")

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

        self._validate_configuration()
        settings = self.settings
        suffix = ALLOWED_IMAGE_TYPES[content_type]
        original_stem = Path(file.filename or "image").stem[:48]
        safe_stem = "".join(char for char in original_stem if char.isalnum() or char in "-_") or "image"
        object_key = f"avatar-assets/{principal.project_name}/{uuid.uuid4().hex}-{safe_stem}{suffix}"
        client = self._client()
        reservation_id = self.quota.reserve(principal.project_name, principal.id, {
            "daily_upload_files": 1,
            "daily_upload_bytes": len(content),
            "total_storage_bytes": len(content),
        })

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
            self.quota.finish_reservation(reservation_id, commit=False)
            message = f"TOS 拒绝上传请求：{error.code or 'unknown'}"
            if error.request_id:
                message += f"（RequestId: {error.request_id}）"
            raise ApiError(message, 502, "tos_upload_rejected") from error
        except tos.exceptions.TosClientError as error:
            self.quota.finish_reservation(reservation_id, commit=False)
            raise ApiError(f"TOS 客户端配置无效：{error.message}", 502, "tos_upload_failed") from error

        public_base = settings.tos_public_base_url.strip().rstrip("/")
        if not public_base:
            endpoint_host = settings.tos_endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
            public_base = f"https://{settings.tos_bucket}.{endpoint_host}"
        url = f"{public_base}/{quote(object_key, safe='/')}"
        upload_id = f"upload_{uuid.uuid4().hex}"
        try:
            self.database.create_asset_record(
                upload_id,
                principal.project_name,
                principal.id,
                "tos",
                url,
                bucket=settings.tos_bucket,
                object_key=object_key,
                size_bytes=len(content),
            )
            self.quota.finish_reservation(reservation_id, commit=True)
        except Exception:
            self.quota.finish_reservation(reservation_id, commit=False)
            try:
                await to_thread.run_sync(lambda: client.delete_object(settings.tos_bucket, object_key))
            except Exception:
                logger.exception("Failed to roll back TOS object after ledger write failure")
            raise

        self.database.log_request(
            principal.id,
            principal.project_name,
            "TOS:PutObject",
            200,
            round((time.monotonic() - started) * 1000),
        )
        return {
            "url": url,
            "uploadId": upload_id,
            "objectKey": object_key,
            "contentType": content_type,
            "size": len(content),
            "etag": result.etag,
            "requestId": result.request_id,
        }

    async def delete_record_object(self, record: dict, *, final_status: str = "deleted") -> bool:
        if record.get("source_type") != "tos" or not record.get("bucket") or not record.get("object_key"):
            self.database.update_asset_record(record["record_id"], final_status, deleted=final_status == "deleted")
            return True
        try:
            await to_thread.run_sync(
                lambda: self._client().delete_object(record["bucket"], record["object_key"])
            )
        except (tos.exceptions.TosServerError, tos.exceptions.TosClientError) as error:
            self.database.update_asset_record(
                record["record_id"],
                "cleanup_pending",
                last_error=str(error),
                increment_cleanup=True,
            )
            return False
        self.database.update_asset_record(record["record_id"], final_status, deleted=final_status == "deleted")
        return True

    async def cleanup_once(self) -> int:
        cleaned = 0
        for record in self.database.cleanup_candidates():
            if await self.delete_record_object(record):
                cleaned += 1
        return cleaned

    async def maintenance_loop(self) -> None:
        while True:
            try:
                await self.cleanup_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TOS cleanup maintenance failed")
            await asyncio.sleep(3600)
