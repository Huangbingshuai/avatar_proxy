import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi.responses import JSONResponse, Response

from .config import Settings
from .database import Database
from .errors import ApiError
from .security import ApiPrincipal


REGION = "cn-beijing"
SERVICE = "ark"
VERSION = "2024-01-01"
HOST = "ark.cn-beijing.volcengineapi.com"
logger = logging.getLogger(__name__)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


class VolcengineClient:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.upstream_timeout_seconds,
                transport=self.transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _signed_request(self, action: str, payload: dict[str, Any], project_name: str) -> tuple[str, bytes, dict[str, str]]:
        access_key = self.settings.volcengine_access_key
        secret_key = self.settings.volcengine_secret_key
        if not access_key or not secret_key:
            raise ApiError("服务端尚未配置火山引擎 AK/SK", 503, "upstream_credentials_missing")

        body = json.dumps({**payload, "ProjectName": project_name}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        payload_hash = _sha256(body)
        x_date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        short_date = x_date[:8]
        query = f"Action={quote(action, safe='')}&Version={quote(VERSION, safe='')}"
        canonical_headers = (
            f"content-type:application/json\nhost:{HOST}\n"
            f"x-content-sha256:{payload_hash}\nx-date:{x_date}\n"
        )
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_request = f"POST\n/\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        scope = f"{short_date}/{REGION}/{SERVICE}/request"
        string_to_sign = f"HMAC-SHA256\n{x_date}\n{scope}\n{_sha256(canonical_request.encode('utf-8'))}"
        k_date = _hmac(secret_key.encode("utf-8"), short_date)
        k_region = _hmac(k_date, REGION)
        k_service = _hmac(k_region, SERVICE)
        k_signing = _hmac(k_service, "request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "content-type": "application/json",
            "host": HOST,
            "x-content-sha256": payload_hash,
            "x-date": x_date,
            "authorization": authorization,
        }
        return f"https://{HOST}/?{query}", body, headers

    async def call(self, action: str, payload: dict[str, Any], principal: ApiPrincipal) -> Response:
        started = time.monotonic()
        url, body, headers = self._signed_request(action, payload, principal.project_name)
        try:
            upstream = await self._http_client().post(url, content=body, headers=headers)
        except httpx.RequestError as error:
            duration_ms = round((time.monotonic() - started) * 1000)
            self.database.log_request(
                principal.id,
                principal.project_name,
                action,
                502,
                duration_ms,
            )
            logger.warning(
                "Volcengine request failed: action=%s project=%s error=%s duration_ms=%s",
                action,
                principal.project_name,
                type(error).__name__,
                duration_ms,
            )
            raise ApiError("无法连接火山引擎服务", 502, "upstream_unreachable") from error

        self.database.log_request(
            principal.id,
            principal.project_name,
            action,
            upstream.status_code,
            round((time.monotonic() - started) * 1000),
        )
        try:
            content = upstream.json()
            return JSONResponse(
                status_code=upstream.status_code,
                content=content,
                headers={"x-upstream-service": "volcengine-ark"},
            )
        except ValueError:
            return Response(
                status_code=upstream.status_code,
                content=upstream.content,
                media_type=upstream.headers.get("content-type", "text/plain"),
                headers={"x-upstream-service": "volcengine-ark"},
            )
