import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi.responses import JSONResponse, Response

from .config import Settings
from .database import Database
from .errors import ApiError
from .security import ApiPrincipal


class SeedanceClient:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.transport = transport

    async def request(
        self,
        method: str,
        path: str,
        principal: ApiPrincipal,
        payload: dict[str, Any] | None = None,
    ) -> Response:
        if not self.settings.seedance_ark_api_key:
            raise ApiError("API 服务器尚未配置 SEEDANCE_ARK_API_KEY", 503, "seedance_api_key_missing")

        started = time.monotonic()
        url = f"{self.settings.seedance_base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "authorization": f"Bearer {self.settings.seedance_ark_api_key}",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.upstream_timeout_seconds,
                transport=self.transport,
            ) as client:
                upstream = await client.request(method, url, headers=headers, json=payload)
        except httpx.RequestError as error:
            raise ApiError("无法连接 Seedance 视频生成服务", 502, "seedance_unreachable") from error

        self.database.log_request(
            principal.id,
            principal.project_name,
            f"Seedance:{method.upper()}:{path}",
            upstream.status_code,
            round((time.monotonic() - started) * 1000),
        )
        try:
            data = upstream.json()
        except ValueError:
            return Response(
                status_code=upstream.status_code,
                content=upstream.content,
                media_type=upstream.headers.get("content-type", "text/plain"),
                headers={"x-upstream-service": "volcengine-seedance"},
            )
        self._record_usage(data, principal)
        return JSONResponse(
            status_code=upstream.status_code,
            content=data,
            headers={"x-upstream-service": "volcengine-seedance"},
        )

    @staticmethod
    def _token(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _record_usage(self, data: Any, principal: ApiPrincipal) -> None:
        if not isinstance(data, dict) or not data.get("id"):
            return
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        input_tokens = self._token(usage.get("input_tokens"))
        output_tokens = self._token(usage.get("output_tokens") or usage.get("completion_tokens"))
        total_tokens = self._token(usage.get("total_tokens")) or input_tokens + output_tokens
        if not output_tokens and total_tokens and not input_tokens:
            output_tokens = total_tokens
        raw_created_at = data.get("created_at")
        created_at = None
        try:
            if raw_created_at is not None:
                created_at = datetime.fromtimestamp(float(raw_created_at), timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            created_at = None
        self.database.upsert_video_usage(
            principal.id,
            principal.project_name,
            str(data["id"]),
            str(data.get("model") or ""),
            input_tokens,
            output_tokens,
            total_tokens,
            created_at,
        )
