import asyncio
import json
import logging
import re
import subprocess
import tempfile
import time
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import quote

import tos
from anyio import to_thread
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .config import Settings
from .database import Database
from .errors import ApiError
from .maintenance import MaintenanceGate
from .quota import QuotaManager
from .security import ApiPrincipal


MEBIBYTE = 1024 * 1024
IMAGE_MAX_BYTES = 30 * MEBIBYTE
VIDEO_MAX_BYTES = 200 * MEBIBYTE
AUDIO_MAX_BYTES = 15 * MEBIBYTE
COPY_CHUNK_BYTES = MEBIBYTE
VIDEO_MIN_PIXELS = 407_696
# The CreateAsset page lists 4K as supported while one pixel-range line is
# narrower than 4K. The video-generation specification has the consistent
# upper bound below (3326 x 2494), which also admits standard 3840 x 2160.
VIDEO_MAX_PIXELS = 8_295_044

MEDIA_TYPES: dict[str, dict[str, str | int]] = {
    "image/jpeg": {"asset_type": "Image", "suffix": ".jpg", "max_bytes": IMAGE_MAX_BYTES},
    "image/png": {"asset_type": "Image", "suffix": ".png", "max_bytes": IMAGE_MAX_BYTES},
    "image/webp": {"asset_type": "Image", "suffix": ".webp", "max_bytes": IMAGE_MAX_BYTES},
    "image/bmp": {"asset_type": "Image", "suffix": ".bmp", "max_bytes": IMAGE_MAX_BYTES},
    "image/tiff": {"asset_type": "Image", "suffix": ".tiff", "max_bytes": IMAGE_MAX_BYTES},
    "image/gif": {"asset_type": "Image", "suffix": ".gif", "max_bytes": IMAGE_MAX_BYTES},
    "image/heic": {"asset_type": "Image", "suffix": ".heic", "max_bytes": IMAGE_MAX_BYTES},
    "image/heif": {"asset_type": "Image", "suffix": ".heif", "max_bytes": IMAGE_MAX_BYTES},
    "video/mp4": {"asset_type": "Video", "suffix": ".mp4", "max_bytes": VIDEO_MAX_BYTES},
    "video/quicktime": {"asset_type": "Video", "suffix": ".mov", "max_bytes": VIDEO_MAX_BYTES},
    "audio/wav": {"asset_type": "Audio", "suffix": ".wav", "max_bytes": AUDIO_MAX_BYTES},
    "audio/mpeg": {"asset_type": "Audio", "suffix": ".mp3", "max_bytes": AUDIO_MAX_BYTES},
}
CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/x-png": "image/png",
    "image/x-ms-bmp": "image/bmp",
    "image/x-bmp": "image/bmp",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/mp3": "audio/mpeg",
}
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/bmp": {".bmp"},
    "image/tiff": {".tif", ".tiff"},
    "image/gif": {".gif"},
    "image/heic": {".heic"},
    "image/heif": {".heif"},
    "video/mp4": {".mp4"},
    "video/quicktime": {".mov"},
    "audio/wav": {".wav"},
    "audio/mpeg": {".mp3"},
}
IMAGE_FORMATS = {
    "image/jpeg": {"JPEG"},
    "image/png": {"PNG"},
    "image/webp": {"WEBP"},
    "image/bmp": {"BMP"},
    "image/tiff": {"TIFF"},
    "image/gif": {"GIF"},
    "image/heic": {"HEIF"},
    "image/heif": {"HEIF"},
}
BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
logger = logging.getLogger(__name__)
register_heif_opener()


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith("your_") or normalized.startswith("replace_with")


def normalize_content_type(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    return CONTENT_TYPE_ALIASES.get(normalized, normalized)


def content_matches_type(content: bytes, content_type: str) -> bool:
    content_type = normalize_content_type(content_type)
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if content_type == "image/bmp":
        return content.startswith(b"BM")
    if content_type == "image/tiff":
        return content.startswith((b"II*\x00", b"MM\x00*"))
    if content_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if content_type in {"image/heic", "image/heif", "video/mp4", "video/quicktime"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if content_type == "audio/wav":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"
    if content_type == "audio/mpeg":
        return content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
        )
    return False


def _image_metadata(path: Path, content_type: str) -> dict[str, int]:
    try:
        with Image.open(path) as image:
            actual_format = (image.format or "").upper()
            width, height = image.size
            frames = int(getattr(image, "n_frames", 1))
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ApiError("文件不是有效或完整的受支持图片", 400, "invalid_media_content") from error
    if actual_format not in IMAGE_FORMATS[content_type]:
        raise ApiError("文件内容与声明的图片类型不匹配", 400, "media_type_mismatch")
    if not (300 < width < 6000 and 300 < height < 6000):
        raise ApiError("图片宽高必须分别大于 300px 且小于 6000px", 400, "invalid_image_dimensions")
    ratio = width / height
    if not 0.4 < ratio < 2.5:
        raise ApiError("图片宽高比必须在 0.4 到 2.5 之间", 400, "invalid_image_ratio")
    return {"width": width, "height": height, "frames": frames}


def _duration(probe: dict[str, Any], stream: dict[str, Any] | None = None) -> float:
    values = [probe.get("format", {}).get("duration")]
    if stream:
        values.append(stream.get("duration"))
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0.0


def _frame_rate(stream: dict[str, Any]) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = stream.get(key)
        if not value or value == "0/0":
            continue
        try:
            rate = float(Fraction(str(value)))
        except (ValueError, ZeroDivisionError):
            continue
        if rate > 0:
            return rate
    return 0.0


def _probe_media(path: Path, content_type: str, ffprobe_path: str) -> dict[str, int | float]:
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration",
                "-of", "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as error:
        raise ApiError("服务端未安装或未配置 ffprobe", 503, "ffprobe_not_configured") from error
    except subprocess.TimeoutExpired as error:
        raise ApiError("媒体文件探测超时", 400, "media_probe_timeout") from error
    if result.returncode != 0:
        raise ApiError("文件不是有效或完整的受支持音视频", 400, "invalid_media_content")
    try:
        probe = json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise ApiError("无法读取媒体文件信息", 400, "invalid_media_content") from error
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list):
        raise ApiError("媒体文件没有可识别的媒体流", 400, "invalid_media_content")
    format_names = {
        part.strip().lower()
        for part in str(probe.get("format", {}).get("format_name", "")).split(",")
        if part.strip()
    }

    if content_type in {"video/mp4", "video/quicktime"}:
        if not format_names.intersection({"mov", "mp4"}):
            raise ApiError("文件内容与声明的视频类型不匹配", 400, "media_type_mismatch")
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
        if not video_stream:
            raise ApiError("视频文件不包含视频流", 400, "invalid_media_content")
        try:
            width, height = int(video_stream.get("width", 0)), int(video_stream.get("height", 0))
        except (TypeError, ValueError) as error:
            raise ApiError("无法读取视频尺寸", 400, "invalid_video_dimensions") from error
        if not (300 <= width <= 6000 and 300 <= height <= 6000):
            raise ApiError("视频宽高必须在 300px 到 6000px 之间", 400, "invalid_video_dimensions")
        ratio = width / height
        pixels = width * height
        if not 0.4 <= ratio <= 2.5:
            raise ApiError("视频宽高比必须在 0.4 到 2.5 之间", 400, "invalid_video_ratio")
        if not VIDEO_MIN_PIXELS <= pixels <= VIDEO_MAX_PIXELS:
            raise ApiError("视频总像素数不符合方舟要求", 400, "invalid_video_pixels")
        duration = _duration(probe, video_stream)
        if not 2 <= duration <= 30:
            raise ApiError("视频时长必须在 2 秒到 30 秒之间", 400, "invalid_video_duration")
        fps = _frame_rate(video_stream)
        if not 24 <= fps <= 60:
            raise ApiError("视频帧率必须在 24 到 60 FPS 之间", 400, "invalid_video_fps")
        return {
            "width": width,
            "height": height,
            "duration": round(duration, 3),
            "fps": round(fps, 3),
        }

    expected_format = "wav" if content_type == "audio/wav" else "mp3"
    if expected_format not in format_names:
        raise ApiError("文件内容与声明的音频类型不匹配", 400, "media_type_mismatch")
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise ApiError("音频文件不包含音频流", 400, "invalid_media_content")
    duration = _duration(probe, audio_stream)
    if not 2 <= duration <= 30:
        raise ApiError("音频时长必须在 2 秒到 30 秒之间", 400, "invalid_audio_duration")
    return {"duration": round(duration, 3)}


def inspect_media(path: Path, content_type: str, ffprobe_path: str = "ffprobe") -> dict[str, int | float]:
    if content_type.startswith("image/"):
        return _image_metadata(path, content_type)
    return _probe_media(path, content_type, ffprobe_path)


def _copy_upload_to_path(source: Any, destination: Path, maximum: int) -> int:
    size = 0
    with destination.open("wb") as output:
        while True:
            chunk = source.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                return size
            output.write(chunk)
    return size


class TosStorage:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        quota: QuotaManager,
        maintenance_gate: MaintenanceGate | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.quota = quota
        self.maintenance_gate = maintenance_gate

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

    async def upload_media(self, file: UploadFile, principal: ApiPrincipal) -> dict[str, Any]:
        content_type = normalize_content_type(file.content_type or "")
        spec = MEDIA_TYPES.get(content_type)
        if spec is None:
            raise ApiError(
                "不支持该素材格式；请使用方舟支持的图片、MP4/MOV 视频或 WAV/MP3 音频",
                415,
                "unsupported_media_type",
            )
        filename_suffix = Path(file.filename or "").suffix.lower()
        if filename_suffix not in CONTENT_TYPE_EXTENSIONS[content_type]:
            raise ApiError(
                "文件扩展名与声明的素材格式不匹配",
                400,
                "invalid_file_extension",
            )
        settings = self.settings
        category_maximum = int(spec["max_bytes"])
        if spec["asset_type"] == "Image":
            category_maximum -= 1  # Ark requires image size to be strictly below 30 MB.
        maximum = min(settings.upload_max_bytes, category_maximum)
        suffix = str(spec["suffix"])
        temporary = tempfile.NamedTemporaryFile(prefix="ark-upload-", suffix=suffix, delete=False)
        temporary_path = Path(temporary.name)
        temporary.close()
        reservation_id: str | None = None
        object_key = ""
        client: tos.TosClientV2 | None = None
        try:
            await file.seek(0)
            size = await to_thread.run_sync(
                lambda: _copy_upload_to_path(file.file, temporary_path, maximum)
            )
            if not size:
                raise ApiError("上传文件不能为空", 400, "empty_file")
            if size > maximum:
                raise ApiError("素材文件超过允许的大小", 413, "file_too_large")
            metadata = await to_thread.run_sync(
                lambda: inspect_media(temporary_path, content_type, settings.ffprobe_path)
            )

            self._validate_configuration()
            original_stem = Path(file.filename or "asset").stem[:48]
            safe_stem = "".join(char for char in original_stem if char.isalnum() or char in "-_") or "asset"
            object_key = f"avatar-assets/{principal.project_name}/{uuid.uuid4().hex}-{safe_stem}{suffix}"
            client = self._client()
            reservation_id = self.quota.reserve(principal.project_name, principal.id, {
                "daily_upload_files": 1,
                "daily_upload_bytes": size,
                "total_storage_bytes": size,
            })

            started = time.monotonic()
            try:
                def put_object() -> Any:
                    assert client is not None
                    with temporary_path.open("rb") as content_stream:
                        return client.put_object(
                            settings.tos_bucket,
                            object_key,
                            content=content_stream,
                            content_type=content_type,
                        )

                result = await to_thread.run_sync(put_object)
            except tos.exceptions.TosServerError as error:
                self.quota.finish_reservation(reservation_id, commit=False)
                reservation_id = None
                message = f"TOS 拒绝上传请求：{error.code or 'unknown'}"
                if error.request_id:
                    message += f"（RequestId: {error.request_id}）"
                raise ApiError(message, 502, "tos_upload_rejected") from error
            except tos.exceptions.TosClientError as error:
                self.quota.finish_reservation(reservation_id, commit=False)
                reservation_id = None
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
                    size_bytes=size,
                    asset_type=str(spec["asset_type"]),
                    content_type=content_type,
                    media_metadata=metadata,
                )
                self.quota.finish_reservation(reservation_id, commit=True)
                reservation_id = None
            except Exception:
                self.quota.finish_reservation(reservation_id, commit=False)
                reservation_id = None
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
                "assetType": spec["asset_type"],
                "contentType": content_type,
                "size": size,
                "mediaMetadata": metadata,
                "etag": result.etag,
                "requestId": result.request_id,
            }
        finally:
            if reservation_id is not None:
                self.quota.finish_reservation(reservation_id, commit=False)
            temporary_path.unlink(missing_ok=True)

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
                if self.maintenance_gate:
                    async with self.maintenance_gate.background_activity():
                        await self.cleanup_once()
                else:
                    await self.cleanup_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TOS cleanup maintenance failed")
            await asyncio.sleep(3600)
