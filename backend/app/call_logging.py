from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlsplit, urlunsplit


logger = logging.getLogger(__name__)

ASGIApp = Callable[[dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[None]]

_SENSITIVE_FIELD_FRAGMENTS = (
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "password",
    "credential",
    "signature",
    "cookie",
    "session",
    "b64_json",
    "image_data",
    "audio_data",
)
_MODEL_CREATE_PATHS = frozenset(
    {
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/images/generations",
        "/v1/embeddings",
        "/v1/embeddings/multimodal",
        "/v1/audio/speech",
        "/v1/audio/transcriptions",
        "/v1/audio/generations",
        "/api/v3/contents/generations/tasks",
    }
)
_INLINE_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}={0,2}"),
    re.compile(r"\bvap_live_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)
_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/\r\n]+={0,2}$")
_DATA_URI_PATTERN = re.compile(
    r"^data:(?:[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+)?"
    r"(?:;[A-Za-z0-9.+-]+(?:=[^;,]*)?)*,",
    re.IGNORECASE,
)


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }


def _known_key_from_authorization(database: Any, authorization: str) -> dict[str, Any] | None:
    scheme, separator, secret = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not secret.strip():
        return None
    return database.find_api_key_any_status(
        hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()
    )


def _safe_url(value: str) -> str:
    if _DATA_URI_PATTERN.match(value):
        return f"[DATA_URI:{len(value)} chars]"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[REDACTED]" if parsed.query else "", ""))


def _sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FIELD_FRAGMENTS)


def _redact_inline_secrets(value: str) -> str:
    for pattern in _INLINE_SECRET_PATTERNS:
        value = pattern.sub("[REDACTED_SECRET]", value)
    return value


def _looks_like_base64(value: str) -> bool:
    compact = value.replace("\r", "").replace("\n", "")
    return len(compact) >= 256 and len(compact) % 4 == 0 and bool(_BASE64_PATTERN.fullmatch(value))


def _is_json_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _sanitize(value: Any, *, key: str = "") -> Any:
    if _sensitive_key(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _DATA_URI_PATTERN.match(value):
            return f"[DATA_URI:{len(value)} chars]"
        if _looks_like_base64(value):
            return f"[BASE64:{len(value)} chars]"
        if value.startswith(("http://", "https://")):
            value = _safe_url(value)
        return _redact_inline_secrets(value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    return str(value)


def _serialized_json(value: Any) -> str:
    return json.dumps(_sanitize(value), ensure_ascii=False, separators=(",", ":"))


def _json_body(content_type: str, captured: bytes, total_bytes: int) -> Any:
    if not _is_json_content_type(content_type):
        return None
    if not captured:
        return None
    try:
        return json.loads(captured)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"invalidJson": True, "bodyBytes": total_bytes}


def _request_summary(
    scope: dict[str, Any],
    headers: dict[str, str],
    body: bytes,
    body_bytes: int,
) -> dict[str, Any]:
    raw_query = scope.get("query_string", b"").decode("utf-8", "replace")
    query = {key: values if len(values) > 1 else values[0] for key, values in parse_qs(raw_query, keep_blank_values=True).items()}
    summary: dict[str, Any] = {
        "path": _sanitize(scope.get("path_params") or {}),
        "query": _sanitize(query),
        "contentType": headers.get("content-type", "").split(";", 1)[0],
        "contentLength": int(headers["content-length"]) if headers.get("content-length", "").isdigit() else body_bytes,
    }
    parsed_body = _json_body(headers.get("content-type", ""), body, body_bytes)
    if parsed_body is not None:
        summary["body"] = parsed_body
    elif body_bytes:
        summary["body"] = {"captured": False, "bodyBytes": body_bytes}
    if "idempotency-key" in headers:
        summary["idempotencyKey"] = "[PRESENT]"
    return summary


def _response_summary(
    content_type: str,
    body: bytes,
    body_bytes: int,
    headers: dict[str, str],
) -> tuple[dict[str, Any], str | None, str | None]:
    base: dict[str, Any] = {
        "contentType": content_type.split(";", 1)[0],
        "bodyBytes": body_bytes,
    }
    request_id = headers.get("x-request-id")
    upstream = headers.get("x-upstream-service")
    if request_id:
        base["responseRequestId"] = request_id[:128]
    if upstream:
        base["upstreamService"] = upstream[:128]
    error_code: str | None = None
    error_message: str | None = None
    if "text/event-stream" in content_type.lower():
        base["stream"] = True
        text = body.decode("utf-8", "replace")
        events: list[dict[str, Any]] = []
        stream_completed = False
        for block in re.split(r"\r?\n\r?\n", text):
            if not block:
                continue
            event: dict[str, Any] = {}
            data_lines: list[str] = []
            comments: list[str] = []
            for line in block.splitlines():
                if line.startswith(":"):
                    comments.append(line[1:].lstrip())
                    continue
                field, separator, raw_value = line.partition(":")
                value = raw_value[1:] if separator and raw_value.startswith(" ") else raw_value
                if field == "data":
                    data_lines.append(value)
                elif field:
                    event[field] = value
            if comments:
                event["comments"] = comments
            if data_lines:
                data_text = "\n".join(data_lines)
                if data_text == "[DONE]":
                    event["data"] = "[DONE]"
                    stream_completed = True
                else:
                    try:
                        event["data"] = json.loads(data_text)
                    except json.JSONDecodeError:
                        event["data"] = data_text
            events.append(event)
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            error = data.get("error")
            if isinstance(error, dict):
                error_code = str(error.get("code") or "stream_error")[:128]
                error_message = _redact_inline_secrets(
                    str(error.get("message") or "流式响应失败")[:1024]
                )
                base["streamError"] = {"code": error_code, "message": error_message}
        base["events"] = events
        base["streamCompleted"] = stream_completed
        return base, error_code, error_message
    parsed = _json_body(content_type, body, body_bytes)
    if parsed is not None:
        base["body"] = parsed
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict):
                error_code = str(error.get("code") or "")[:128] or None
                error_message = _redact_inline_secrets(
                    str(error.get("message") or "")[:1024]
                ) or None
            elif isinstance(parsed.get("detail"), str):
                error_message = _redact_inline_secrets(str(parsed["detail"])[:1024])
    elif body_bytes:
        base["bodyCaptured"] = False
    return base, error_code, error_message


def _model_alias(request_body: Any, query_string: bytes) -> str | None:
    if isinstance(request_body, dict) and isinstance(request_body.get("model"), str):
        return request_body["model"].strip()[:128] or None
    query = parse_qs(query_string.decode("utf-8", "replace"))
    value = query.get("model", [None])[0]
    return value.strip()[:128] if isinstance(value, str) and value.strip() else None


class ApiCallLoggingMiddleware:
    """Persist one redacted record for every request tied to a known business API key."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        path = str(scope.get("path") or "")
        if scope.get("type") != "http" or path.startswith("/api/internal") or not (
            path.startswith("/api/") or path.startswith("/v1/")
        ):
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        request_headers = _headers(scope)
        request_body = bytearray()
        request_bytes = 0
        response_body = bytearray()
        response_bytes = 0
        response_headers: dict[str, str] = {}
        response_content_type = ""
        status_code = 500

        async def receive_with_capture() -> dict[str, Any]:
            nonlocal request_bytes
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                request_bytes += len(chunk)
                if _is_json_content_type(request_headers.get("content-type", "")):
                    request_body.extend(chunk)
            return message

        async def send_with_capture(message: dict[str, Any]) -> None:
            nonlocal status_code, response_headers, response_content_type, response_bytes
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                response_headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
                response_content_type = response_headers.get("content-type", "")
            elif message.get("type") == "http.response.body":
                chunk = message.get("body", b"")
                response_bytes += len(chunk)
                if (
                    _is_json_content_type(response_content_type)
                    or "text/event-stream" in response_content_type.lower()
                ):
                    response_body.extend(chunk)
            await send(message)

        failure: BaseException | None = None
        try:
            await self.app(scope, receive_with_capture, send_with_capture)
        except BaseException as error:
            failure = error
            if isinstance(error, asyncio.CancelledError):
                status_code = 499
            raise
        finally:
            state = scope.get("state") or {}
            api_key_id = state.get("api_key_id")
            project_name = state.get("api_project_name")
            database = scope["app"].state.database
            if not api_key_id or not project_name:
                known_key = _known_key_from_authorization(
                    database, request_headers.get("authorization", "")
                )
                if known_key:
                    api_key_id = known_key["id"]
                    project_name = known_key.get("projectName") or "unbound"
            if api_key_id and project_name:
                try:
                    parsed_request = _json_body(
                        request_headers.get("content-type", ""),
                        bytes(request_body),
                        request_bytes,
                    )
                    request_summary = _request_summary(
                        scope,
                        request_headers,
                        bytes(request_body),
                        request_bytes,
                    )
                    response_summary, error_code, error_message = _response_summary(
                        response_content_type,
                        bytes(response_body),
                        response_bytes,
                        response_headers,
                    )
                    if failure is not None and not error_message:
                        error_code = "client_disconnected" if status_code == 499 else "unhandled_exception"
                        error_message = type(failure).__name__
                    route = scope.get("route")
                    route_template = str(getattr(route, "path", "") or path)[:512]
                    route_name = str(getattr(route, "name", "") or "")[:128]
                    client = scope.get("client")
                    forwarded = request_headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
                    source_ip = forwarded or (str(client[0]) if client else None)
                    database.log_api_call(
                        request_id=str(state.get("request_id") or response_headers.get("x-request-id") or ""),
                        api_key_id=str(api_key_id),
                        project_name=str(project_name),
                        method=str(scope.get("method") or "GET").upper(),
                        path=path,
                        route_template=route_template,
                        action=route_name or f"{scope.get('method', 'GET')} {route_template}",
                        model_alias=(
                            _redact_inline_secrets(
                                _model_alias(parsed_request, scope.get("query_string", b"")) or ""
                            )
                            or None
                        ),
                        request_params_json=_serialized_json(request_summary),
                        status_code=status_code,
                        success=200 <= status_code < 400 and not error_code and failure is None,
                        response_summary_json=_serialized_json(response_summary),
                        error_code=_redact_inline_secrets(error_code) if error_code else None,
                        error_message=_redact_inline_secrets(error_message) if error_message else None,
                        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                        response_bytes=response_bytes,
                        source_ip=source_ip,
                        user_agent=_redact_inline_secrets(request_headers.get("user-agent", "")) or None,
                        is_model_call=str(scope.get("method") or "").upper() == "POST" and route_template in _MODEL_CREATE_PATHS,
                    )
                except Exception:
                    logger.exception("Failed to persist business API call log")
