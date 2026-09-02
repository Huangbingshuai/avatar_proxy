from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .config import Settings
from .database import Database
from .errors import ApiError
from .security import ApiPrincipal


PROVIDERS = {"openai", "volcengine_ark", "aliyun_bailian", "minimax"}
TERMINAL_TASK_STATUSES = {"succeeded", "failed", "canceled"}
ACTIVE_TASK_STATUSES = {"queued", "running"}
ALIYUN_REGIONS = {
    "cn-beijing": "cn-beijing",
    "ap-southeast-1": "ap-southeast-1",
    "ap-northeast-1": "ap-northeast-1",
    "eu-central-1": "eu-central-1",
    "us-east-1": "us-east-1",
}


def _now_epoch() -> int:
    return int(time.time())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loaded(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _secret_hint(secret: str) -> str:
    stripped = secret.strip()
    if len(stripped) <= 8:
        return "****"
    return f"{stripped[:3]}****{stripped[-4:]}"


def _request_hash(operation: str, payload: dict[str, Any]) -> str:
    canonical = _json({"operation": operation, "payload": payload})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _provider_request_id(headers: httpx.Headers, data: dict[str, Any] | None = None) -> str | None:
    for name in ("x-request-id", "request-id", "x-tt-logid", "x-log-id"):
        value = headers.get(name)
        if value:
            return value[:256]
    if isinstance(data, dict):
        for key in ("request_id", "requestId", "RequestId", "id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value[:256]
    return None


class CredentialVault:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _fernet(self) -> Fernet:
        configured = self.settings.provider_credential_encryption_key
        if configured is None:
            raise ApiError(
                "多供应商凭证加密密钥尚未配置",
                503,
                "provider_encryption_key_missing",
            )
        try:
            return Fernet(configured.get_secret_value().encode("ascii"))
        except (ValueError, UnicodeError) as error:
            raise ApiError(
                "多供应商凭证加密密钥格式无效",
                503,
                "provider_encryption_key_invalid",
            ) from error

    def encrypt(self, secret: str) -> str:
        value = secret.strip()
        if len(value) < 8 or len(value) > 4096:
            raise ApiError("供应商凭证长度无效", 422, "provider_secret_invalid")
        return self._fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as error:
            raise ApiError(
                "供应商凭证无法解密，请检查服务器主密钥",
                503,
                "provider_secret_decrypt_failed",
            ) from error


@dataclass(frozen=True)
class ModelRoute:
    alias: str
    display_name: str
    provider: str
    modality: str
    protocol: str
    capabilities: dict[str, Any]
    upstream_model: str
    channel_id: str
    channel_name: str
    channel_config: dict[str, Any]
    credential_id: str
    secret: str


class ProviderRelay:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database
        self.vault = CredentialVault(settings)
        self.transport: httpx.AsyncBaseTransport | None = None

    def require_enabled(self) -> None:
        if not self.settings.multi_provider_enabled:
            raise ApiError("多供应商模型中转尚未启用", 503, "multi_provider_disabled")
        self.vault._fernet()

    @staticmethod
    def _validate_provider_config(provider: str, config: dict[str, Any]) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise ApiError("不支持的供应商类型", 422, "provider_not_supported")
        if not isinstance(config, dict):
            raise ApiError("渠道配置必须是对象", 422, "provider_config_invalid")
        allowed: dict[str, set[str]] = {
            "openai": {"organization", "project"},
            "volcengine_ark": {"projectName"},
            "aliyun_bailian": {"workspaceId", "region"},
            "minimax": set(),
        }
        unknown = sorted(set(config) - allowed[provider])
        if unknown:
            raise ApiError(
                "渠道配置包含不允许的字段",
                422,
                "provider_config_field_forbidden",
                details={"fields": unknown},
            )
        normalized = {key: str(value).strip() for key, value in config.items() if str(value).strip()}
        if provider == "aliyun_bailian":
            workspace = normalized.get("workspaceId", "")
            if not workspace or len(workspace) > 128 or not all(ch.isalnum() or ch in "-_" for ch in workspace):
                raise ApiError("阿里百炼渠道必须填写有效的 Workspace ID", 422, "aliyun_workspace_invalid")
            region = normalized.get("region", "cn-beijing")
            if region not in ALIYUN_REGIONS:
                raise ApiError("不支持的阿里百炼地域", 422, "aliyun_region_invalid")
            normalized["region"] = region
        for value in normalized.values():
            if len(value) > 256:
                raise ApiError("渠道配置字段过长", 422, "provider_config_invalid")
        return normalized

    def _channel_view(self, row: Any) -> dict[str, Any]:
        result = dict(row)
        return {
            "id": result["id"],
            "projectName": result["project_name"],
            "name": result["name"],
            "provider": result["provider"],
            "config": _loaded(result.get("config_json"), {}),
            "status": result["status"],
            "secretHint": result.get("secret_hint"),
            "credentialId": result.get("credential_id"),
            "lastTestStatus": result.get("last_test_status"),
            "lastTestAt": result.get("last_test_at"),
            "lastTestLatencyMs": result.get("last_test_latency_ms"),
            "lastTestError": result.get("last_test_error"),
            "createdAt": result.get("created_at"),
            "updatedAt": result.get("updated_at"),
        }

    def list_channels(self, project_name: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT c.*, pc.id AS credential_id, pc.secret_hint
            FROM provider_channels c
            LEFT JOIN provider_credentials pc ON pc.channel_id=c.id AND pc.status='active'
            WHERE c.deleted_at IS NULL
        """
        params: tuple[Any, ...] = ()
        if project_name:
            sql += " AND c.project_name=?"
            params = (project_name,)
        sql += " ORDER BY c.created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._channel_view(row) for row in rows]

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT c.*, pc.id AS credential_id, pc.secret_hint
                FROM provider_channels c
                LEFT JOIN provider_credentials pc ON pc.channel_id=c.id AND pc.status='active'
                WHERE c.id=? AND c.deleted_at IS NULL
                """,
                (channel_id,),
            ).fetchone()
        return self._channel_view(row) if row else None

    def create_channel(
        self,
        *,
        project_name: str,
        name: str,
        provider: str,
        config: dict[str, Any],
        secret: str,
        actor_id: str,
    ) -> dict[str, Any]:
        self.require_enabled()
        canonical_project = self.database.resolve_project_name(project_name)
        if canonical_project is None:
            raise ApiError("项目不存在", 404, "project_not_found")
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 100:
            raise ApiError("渠道名称长度无效", 422, "provider_channel_name_invalid")
        normalized_config = self._validate_provider_config(provider, config)
        # The customer project is already bound to the canonical Volcengine
        # ProjectName. Never trust or require a second client-supplied value.
        if provider == "volcengine_ark":
            normalized_config["projectName"] = canonical_project
        channel_id = f"pch_{uuid.uuid4().hex}"
        credential_id = f"pcr_{uuid.uuid4().hex}"
        ciphertext = self.vault.encrypt(secret)
        with self.database.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO provider_channels "
                    "(id,project_name,name,provider,config_json,created_by) VALUES (?,?,?,?,?,?)",
                    (channel_id, canonical_project, normalized_name, provider, _json(normalized_config), actor_id),
                )
                connection.execute(
                    "INSERT INTO provider_credentials "
                    "(id,channel_id,secret_ciphertext,secret_hint,created_by) VALUES (?,?,?,?,?)",
                    (credential_id, channel_id, ciphertext, _secret_hint(secret), actor_id),
                )
            except Exception as error:
                if "UNIQUE constraint" in str(error):
                    raise ApiError("项目中已存在同名渠道", 409, "provider_channel_exists") from error
                raise
        return self.get_channel(channel_id) or {}

    def rotate_channel_secret(self, channel_id: str, secret: str, actor_id: str) -> dict[str, Any]:
        self.require_enabled()
        ciphertext = self.vault.encrypt(secret)
        new_id = f"pcr_{uuid.uuid4().hex}"
        with self.database.connect() as connection:
            channel = connection.execute(
                "SELECT id FROM provider_channels WHERE id=? AND deleted_at IS NULL", (channel_id,)
            ).fetchone()
            if channel is None:
                raise ApiError("供应商渠道不存在", 404, "provider_channel_not_found")
            connection.execute(
                "UPDATE provider_credentials SET status='retired',retired_at=CURRENT_TIMESTAMP "
                "WHERE channel_id=? AND status='active'",
                (channel_id,),
            )
            connection.execute(
                "INSERT INTO provider_credentials "
                "(id,channel_id,secret_ciphertext,secret_hint,created_by) VALUES (?,?,?,?,?)",
                (new_id, channel_id, ciphertext, _secret_hint(secret), actor_id),
            )
            connection.execute(
                "UPDATE provider_channels SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (channel_id,),
            )
        return self.get_channel(channel_id) or {}

    def set_channel_status(self, channel_id: str, enabled: bool) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE provider_channels SET status=?,updated_at=CURRENT_TIMESTAMP "
                "WHERE id=? AND deleted_at IS NULL",
                ("active" if enabled else "disabled", channel_id),
            )
            if cursor.rowcount != 1:
                raise ApiError("供应商渠道不存在", 404, "provider_channel_not_found")
        return self.get_channel(channel_id) or {}

    def delete_channel(self, channel_id: str) -> None:
        with self.database.connect() as connection:
            channel = connection.execute(
                "SELECT id FROM provider_channels WHERE id=? AND deleted_at IS NULL", (channel_id,)
            ).fetchone()
            if channel is None:
                raise ApiError("供应商渠道不存在", 404, "provider_channel_not_found")
            bindings = connection.execute(
                "SELECT COUNT(*) FROM project_model_bindings WHERE channel_id=?",
                (channel_id,),
            ).fetchone()[0]
            active_tasks = connection.execute(
                "SELECT COUNT(*) FROM inference_tasks WHERE channel_id=? AND status IN ('queued','running')",
                (channel_id,),
            ).fetchone()[0]
            if bindings or active_tasks:
                raise ApiError(
                    "渠道仍有模型绑定或未完成任务，不能删除",
                    409,
                    "provider_channel_in_use",
                    details={"bindingCount": bindings, "activeTaskCount": active_tasks},
                )
            connection.execute(
                "UPDATE provider_credentials SET status='retired',retired_at=COALESCE(retired_at,CURRENT_TIMESTAMP) "
                "WHERE channel_id=? AND status='active'",
                (channel_id,),
            )
            connection.execute(
                "UPDATE provider_channels SET status='disabled',deleted_at=CURRENT_TIMESTAMP,"
                "name=name || '-deleted-' || substr(id,-8),updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (channel_id,),
            )

    def catalog(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM model_catalog WHERE enabled=1 ORDER BY modality,alias"
            ).fetchall()
        return [
            {
                "id": row["alias"],
                "displayName": row["display_name"],
                "provider": row["provider"],
                "modality": row["modality"],
                "protocol": row["protocol"],
                "upstreamModel": row["upstream_model"],
                "capabilities": _loaded(row["capabilities_json"], {}),
                "enabled": bool(row["enabled"]),
            }
            for row in rows
        ]

    def project_models(self, project_name: str) -> list[dict[str, Any]]:
        canonical = self.database.resolve_project_name(project_name)
        if canonical is None:
            raise ApiError("项目不存在", 404, "project_not_found")
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT m.*, b.channel_id, b.enabled AS binding_enabled,
                       c.name AS channel_name, c.status AS channel_status
                FROM model_catalog m
                LEFT JOIN project_model_bindings b
                  ON b.model_alias=m.alias AND b.project_name=?
                LEFT JOIN provider_channels c ON c.id=b.channel_id
                WHERE m.enabled=1
                ORDER BY m.modality,m.alias
                """,
                (canonical,),
            ).fetchall()
        return [
            {
                "model": row["alias"],
                "displayName": row["display_name"],
                "provider": row["provider"],
                "modality": row["modality"],
                "channelId": row["channel_id"],
                "channelName": row["channel_name"],
                "channelStatus": row["channel_status"],
                "upstreamModel": row["upstream_model"],
                "enabled": bool(row["binding_enabled"]) if row["binding_enabled"] is not None else False,
            }
            for row in rows
        ]

    def set_project_models(
        self, project_name: str, bindings: list[dict[str, Any]], actor_id: str
    ) -> list[dict[str, Any]]:
        canonical = self.database.resolve_project_name(project_name)
        if canonical is None:
            raise ApiError("项目不存在", 404, "project_not_found")
        seen: set[str] = set()
        with self.database.connect() as connection:
            for item in bindings:
                alias = str(item.get("model") or "").strip()
                channel_id = str(item.get("channelId") or "").strip()
                enabled = bool(item.get("enabled", True))
                if not alias or alias in seen:
                    raise ApiError("模型绑定存在空值或重复项", 422, "model_binding_invalid")
                seen.add(alias)
                model = connection.execute(
                    "SELECT provider,upstream_model FROM model_catalog WHERE alias=? AND enabled=1",
                    (alias,),
                ).fetchone()
                channel = connection.execute(
                    "SELECT project_name,provider FROM provider_channels "
                    "WHERE id=? AND deleted_at IS NULL", (channel_id,)
                ).fetchone()
                if model is None or channel is None:
                    raise ApiError("模型或渠道不存在", 404, "model_or_channel_not_found")
                if channel["project_name"] != canonical:
                    raise ApiError("不能绑定其他项目的渠道", 403, "cross_project_channel_forbidden")
                if channel["provider"] != model["provider"]:
                    raise ApiError("模型与渠道供应商不匹配", 422, "model_provider_mismatch")
                upstream_model = str(model["upstream_model"] or "").strip()
                if not upstream_model or len(upstream_model) > 256:
                    raise ApiError("模型目录中的上游模型ID无效", 500, "model_catalog_invalid")
                connection.execute(
                    "INSERT INTO project_model_bindings "
                    "(project_name,model_alias,channel_id,upstream_model,enabled,updated_by) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(project_name,model_alias) DO UPDATE SET "
                    "channel_id=excluded.channel_id,upstream_model=excluded.upstream_model,"
                    "enabled=excluded.enabled,updated_by=excluded.updated_by,updated_at=CURRENT_TIMESTAMP",
                    (canonical, alias, channel_id, upstream_model, int(enabled), actor_id),
                )
            if seen:
                placeholders = ",".join("?" for _ in seen)
                connection.execute(
                    f"DELETE FROM project_model_bindings WHERE project_name=? AND model_alias NOT IN ({placeholders})",
                    (canonical, *sorted(seen)),
                )
            else:
                connection.execute("DELETE FROM project_model_bindings WHERE project_name=?", (canonical,))
        return self.project_models(canonical)

    def resolve(self, principal: ApiPrincipal, alias: str) -> ModelRoute:
        self.require_enabled()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT m.alias,m.display_name,m.provider,m.modality,m.protocol,m.capabilities_json,
                       m.upstream_model,c.id AS channel_id,c.name AS channel_name,c.config_json,
                       pc.id AS credential_id,pc.secret_ciphertext
                FROM model_catalog m
                JOIN project_model_bindings b
                  ON b.model_alias=m.alias AND b.project_name=? AND b.enabled=1
                JOIN provider_channels c
                  ON c.id=b.channel_id AND c.project_name=? AND c.status='active'
                JOIN provider_credentials pc ON pc.channel_id=c.id AND pc.status='active'
                WHERE m.alias=? AND m.enabled=1
                """,
                (principal.project_name, principal.project_name, alias),
            ).fetchone()
        if row is None:
            raise ApiError("当前项目未启用该模型或渠道不可用", 403, "model_not_allowed")
        return ModelRoute(
            alias=row["alias"],
            display_name=row["display_name"],
            provider=row["provider"],
            modality=row["modality"],
            protocol=row["protocol"],
            capabilities=_loaded(row["capabilities_json"], {}),
            upstream_model=row["upstream_model"],
            channel_id=row["channel_id"],
            channel_name=row["channel_name"],
            channel_config=_loaded(row["config_json"], {}),
            credential_id=row["credential_id"],
            secret=self.vault.decrypt(row["secret_ciphertext"]),
        )

    def available_models(self, principal: ApiPrincipal) -> list[dict[str, Any]]:
        self.require_enabled()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT m.alias,m.display_name,m.modality,m.capabilities_json
                FROM model_catalog m
                JOIN project_model_bindings b
                  ON b.model_alias=m.alias AND b.project_name=? AND b.enabled=1
                JOIN provider_channels c
                  ON c.id=b.channel_id AND c.project_name=? AND c.status='active'
                JOIN provider_credentials pc ON pc.channel_id=c.id AND pc.status='active'
                WHERE m.enabled=1
                ORDER BY m.alias
                """,
                (principal.project_name, principal.project_name),
            ).fetchall()
        return [
            {
                "id": row["alias"],
                "object": "model",
                "created": 0,
                "owned_by": "richbest",
                "display_name": row["display_name"],
                "modality": row["modality"],
                "capabilities": _loaded(row["capabilities_json"], {}),
            }
            for row in rows
        ]

    def _base_url(self, route: ModelRoute) -> str:
        if route.provider == "openai":
            return "https://api.openai.com/v1"
        if route.provider == "volcengine_ark":
            return "https://ark.cn-beijing.volces.com/api/v3"
        if route.provider == "minimax":
            return "https://api.minimax.cn"
        if route.provider == "aliyun_bailian":
            workspace = route.channel_config.get("workspaceId", "")
            region = route.channel_config.get("region", "cn-beijing")
            if not workspace or region not in ALIYUN_REGIONS:
                raise ApiError("阿里百炼渠道配置不完整", 503, "aliyun_channel_invalid")
            return f"https://{workspace}.{region}.maas.aliyuncs.com/api/v1"
        raise ApiError("供应商适配器不存在", 503, "provider_adapter_missing")

    @staticmethod
    def _headers(route: ModelRoute) -> dict[str, str]:
        headers = {"authorization": f"Bearer {route.secret}", "content-type": "application/json"}
        if route.provider == "openai":
            organization = route.channel_config.get("organization")
            project = route.channel_config.get("project")
            if organization:
                headers["openai-organization"] = organization
            if project:
                headers["openai-project"] = project
        if route.provider == "aliyun_bailian":
            headers["x-dashscope-async"] = "enable"
        return headers

    async def _request(
        self, route: ModelRoute, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[httpx.Response, dict[str, Any]]:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.upstream_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method,
                    f"{self._base_url(route)}{path}",
                    headers=self._headers(route),
                    json=payload,
                )
        except httpx.RequestError as error:
            raise ApiError("无法连接模型供应商", 502, "provider_unreachable") from error
        try:
            data = response.json()
        except ValueError:
            data = {}
            if response.status_code < 400:
                raise ApiError("模型供应商返回了无效响应", 502, "provider_response_invalid")
        if response.status_code >= 400:
            message = "模型供应商拒绝了请求"
            if isinstance(data, dict):
                error_data = data.get("error")
                if isinstance(error_data, dict) and isinstance(error_data.get("message"), str):
                    message = error_data["message"][:500]
                elif isinstance(data.get("message"), str):
                    message = data["message"][:500]
            raise ApiError(
                message,
                response.status_code if 400 <= response.status_code < 600 else 502,
                "provider_request_failed",
                details={"upstreamRequestId": _provider_request_id(response.headers, data)},
            )
        if not isinstance(data, dict):
            raise ApiError("模型供应商返回了无效响应", 502, "provider_response_invalid")
        return response, data

    async def test_channel(self, channel_id: str) -> dict[str, Any]:
        self.require_enabled()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT c.*,pc.id AS credential_id,pc.secret_ciphertext
                FROM provider_channels c JOIN provider_credentials pc
                  ON pc.channel_id=c.id AND pc.status='active'
                WHERE c.id=? AND c.deleted_at IS NULL
                """,
                (channel_id,),
            ).fetchone()
        if row is None:
            raise ApiError("供应商渠道不存在", 404, "provider_channel_not_found")
        route = ModelRoute(
            alias="channel-test",
            display_name="channel-test",
            provider=row["provider"],
            modality="text",
            protocol="test",
            capabilities={},
            upstream_model="",
            channel_id=row["id"],
            channel_name=row["name"],
            channel_config=_loaded(row["config_json"], {}),
            credential_id=row["credential_id"],
            secret=self.vault.decrypt(row["secret_ciphertext"]),
        )
        path = "/v1/models" if route.provider == "minimax" else "/models"
        started = time.monotonic()
        status = "success"
        error_message: str | None = None
        try:
            await self._request(route, "GET", path)
        except ApiError as error:
            status = "failed"
            error_message = error.message[:500]
        latency = round((time.monotonic() - started) * 1000)
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE provider_channels SET last_test_status=?,last_test_at=CURRENT_TIMESTAMP,"
                "last_test_latency_ms=?,last_test_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, latency, error_message, channel_id),
            )
        return {"status": status, "latencyMs": latency, "message": error_message}

    def _record_usage(
        self,
        *,
        request_id: str,
        principal: ApiPrincipal,
        route: ModelRoute,
        status: str,
        task_id: str | None = None,
        provider_request_id: str | None = None,
        usage: dict[str, Any] | None = None,
        generated_images: int | None = None,
        video_seconds: float | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        usage = usage or {}
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        total_tokens = usage.get("total_tokens")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO inference_usage
                (id,request_id,task_id,api_key_id,project_name,model_alias,channel_id,
                 provider_request_id,status,input_tokens,output_tokens,total_tokens,
                 generated_images,video_seconds,video_width,video_height,settled_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                """,
                (
                    f"ius_{uuid.uuid4().hex}", request_id, task_id, principal.id,
                    principal.project_name, route.alias, route.channel_id,
                    provider_request_id, status,
                    int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
                    int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
                    int(total_tokens) if isinstance(total_tokens, (int, float)) else None,
                    generated_images, video_seconds, width, height,
                ),
            )

    async def text_json(
        self, principal: ApiPrincipal, alias: str, operation: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        route = self.resolve(principal, alias)
        if route.modality != "text":
            raise ApiError("该模型不支持文本接口", 422, "model_modality_mismatch")
        path = "/chat/completions" if operation == "chat" else "/responses"
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.upstream_model
        upstream_payload["stream"] = False
        response, data = await self._request(route, "POST", path, upstream_payload)
        data["model"] = route.alias
        request_id = _provider_request_id(response.headers, data) or f"req_{uuid.uuid4().hex}"
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        self._record_usage(
            request_id=request_id,
            principal=principal,
            route=route,
            status="succeeded",
            provider_request_id=_provider_request_id(response.headers, data),
            usage=usage,
        )
        return data, request_id

    async def text_stream(
        self, principal: ApiPrincipal, alias: str, operation: str, payload: dict[str, Any]
    ) -> AsyncIterator[bytes]:
        route = self.resolve(principal, alias)
        if route.modality != "text":
            raise ApiError("该模型不支持文本接口", 422, "model_modality_mismatch")
        path = "/chat/completions" if operation == "chat" else "/responses"
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.upstream_model
        upstream_payload["stream"] = True
        client = httpx.AsyncClient(
            timeout=self.settings.upstream_timeout_seconds,
            transport=self.transport,
        )
        provider_request_id: str | None = None
        usage: dict[str, Any] = {}
        request_id = f"req_{uuid.uuid4().hex}"
        try:
            async with client.stream(
                "POST",
                f"{self._base_url(route)}{path}",
                headers=self._headers(route),
                json=upstream_payload,
            ) as response:
                provider_request_id = _provider_request_id(response.headers)
                if response.status_code >= 400:
                    body = await response.aread()
                    try:
                        data = json.loads(body)
                    except ValueError:
                        data = {}
                    message = data.get("message") if isinstance(data, dict) else None
                    raise ApiError(
                        str(message or "模型供应商拒绝了流式请求")[:500],
                        response.status_code,
                        "provider_request_failed",
                    )
                async for line in response.aiter_lines():
                    if not line:
                        yield b"\n"
                        continue
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        try:
                            event = json.loads(line[6:])
                        except ValueError:
                            yield f"{line}\n".encode("utf-8")
                            continue
                        if isinstance(event, dict):
                            if "model" in event:
                                event["model"] = route.alias
                            if isinstance(event.get("usage"), dict):
                                usage = event["usage"]
                            request_id = str(event.get("id") or event.get("response", {}).get("id") or request_id)
                        yield f"data: {_json(event)}\n".encode("utf-8")
                    else:
                        yield f"{line}\n".encode("utf-8")
        except httpx.RequestError as error:
            raise ApiError("无法连接模型供应商", 502, "provider_unreachable") from error
        finally:
            await client.aclose()
            self._record_usage(
                request_id=request_id,
                principal=principal,
                route=route,
                status="succeeded" if usage else "unknown",
                provider_request_id=provider_request_id,
                usage=usage,
            )

    def _find_idempotent_task(
        self, principal: ApiPrincipal, operation: str, idempotency_key: str, request_hash: str
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM inference_tasks WHERE api_key_id=? AND operation=? AND idempotency_key=?",
                (principal.id, operation, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result["request_hash"] != request_hash:
            raise ApiError(
                "同一个Idempotency-Key不能用于不同请求",
                409,
                "idempotency_key_conflict",
            )
        return result

    def _create_task(
        self,
        principal: ApiPrincipal,
        route: ModelRoute,
        operation: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> tuple[dict[str, Any], bool]:
        request_hash = _request_hash(operation, payload)
        if idempotency_key:
            existing = self._find_idempotent_task(principal, operation, idempotency_key, request_hash)
            if existing:
                return existing, False
        task_id = f"vid_{uuid.uuid4().hex}" if operation == "video" else f"img_{uuid.uuid4().hex}"
        with self.database.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO inference_tasks
                    (id,api_key_id,project_name,model_alias,channel_id,credential_id,upstream_model,
                     operation,status,request_hash,idempotency_key,created_at)
                    VALUES (?,?,?,?,?,?,?,?,'queued',?,?,?)
                    """,
                    (
                        task_id, principal.id, principal.project_name, route.alias,
                        route.channel_id, route.credential_id, route.upstream_model, operation, request_hash,
                        idempotency_key, _now_epoch(),
                    ),
                )
            except Exception as error:
                if idempotency_key and "UNIQUE constraint" in str(error):
                    existing = self._find_idempotent_task(
                        principal, operation, idempotency_key, request_hash
                    )
                    if existing:
                        return existing, False
                raise
        return {
            "id": task_id,
            "status": "queued",
            "request_hash": request_hash,
            "metadata_json": "{}",
        }, True

    async def generate_image(
        self,
        principal: ApiPrincipal,
        alias: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        route = self.resolve(principal, alias)
        if route.modality != "image":
            raise ApiError("该模型不支持图片接口", 422, "model_modality_mismatch")
        task, created = self._create_task(principal, route, "image", payload, idempotency_key)
        if not created:
            metadata = _loaded(task.get("metadata_json"), {})
            if task["status"] == "succeeded" and isinstance(metadata.get("response"), dict):
                return metadata["response"]
            if task["status"] in ACTIVE_TASK_STATUSES:
                raise ApiError("相同幂等请求仍在处理中", 409, "idempotency_request_in_progress")
            raise ApiError("相同幂等请求此前执行失败", 409, "idempotency_request_failed")
        upstream = dict(payload)
        upstream["model"] = route.upstream_model
        try:
            response, data = await self._request(route, "POST", "/images/generations", upstream)
        except ApiError as error:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE inference_tasks SET status='failed',error_code=?,error_message=?,"
                    "completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (error.code, error.message, task["id"]),
                )
            raise
        data["model"] = route.alias
        provider_id = _provider_request_id(response.headers, data)
        images = data.get("data") if isinstance(data.get("data"), list) else []
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE inference_tasks SET status='succeeded',progress=100,provider_request_id=?,"
                "metadata_json=?,completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (provider_id, _json({"response": data}), task["id"]),
            )
        self._record_usage(
            request_id=task["id"],
            task_id=task["id"],
            principal=principal,
            route=route,
            status="succeeded",
            provider_request_id=provider_id,
            usage=usage,
            generated_images=len(images),
        )
        return data

    @staticmethod
    def _video_public(task: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": task["id"],
            "object": "video",
            "model": task["model_alias"],
            "status": task["status"],
            "progress": int(task.get("progress") or 0),
            "created_at": int(task["created_at"]),
        }
        if task.get("completed_at"):
            result["completed_at"] = task["completed_at"]
        if task.get("result_url"):
            result["url"] = task["result_url"]
        if task.get("result_format"):
            result["format"] = task["result_format"]
        if task.get("error_code") or task.get("error_message"):
            result["error"] = {
                "code": task.get("error_code") or "provider_error",
                "message": task.get("error_message") or "视频生成失败",
            }
        metadata = _loaded(task.get("metadata_json"), {})
        if isinstance(metadata, dict) and metadata:
            result["metadata"] = {key: value for key, value in metadata.items() if key != "response"}
        return result

    def _video_submit_payload(self, route: ModelRoute, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if route.provider == "volcengine_ark":
            allowed_metadata = {
                "resolution", "ratio", "generate_audio", "watermark", "camera_fixed",
                "return_last_frame", "service_tier", "content", "draft", "frames",
                "execution_expires_after",
            }
        elif route.provider == "aliyun_bailian":
            allowed_metadata = {"resolution", "ratio", "prompt_extend", "audio", "aigc_watermark"}
        else:
            allowed_metadata = {"resolution", "ratio", "aigc_watermark", "content"}
        forbidden = sorted(set(metadata) - allowed_metadata)
        if forbidden:
            raise ApiError(
                "metadata包含当前版本不允许的字段",
                422,
                "video_metadata_forbidden",
                details={"fields": forbidden},
            )
        prompt = str(payload.get("prompt") or "").strip()
        image = str(payload.get("image") or "").strip()
        if not prompt and not image and not metadata.get("content"):
            raise ApiError("视频请求至少需要prompt或参考素材", 422, "video_input_required")
        duration = payload.get("duration")
        unsupported = [name for name in ("width", "height", "fps") if payload.get(name) is not None]
        if route.provider == "aliyun_bailian" and payload.get("seed") is not None:
            unsupported.append("seed")
        if unsupported:
            raise ApiError(
                "当前视频模型不支持部分兼容字段",
                422,
                "video_parameter_unsupported",
                details={"fields": unsupported},
            )
        if route.provider == "volcengine_ark":
            content = metadata.get("content")
            if content is None:
                content = []
                if prompt:
                    content.append({"type": "text", "text": prompt})
                if image:
                    content.append(
                        {"type": "image_url", "image_url": {"url": image}, "role": "first_frame"}
                    )
            safe_content = self._ark_video_content(route, content)
            frames = metadata.get("frames")
            if duration is not None and frames is not None:
                raise ApiError("duration和frames不能同时设置", 422, "video_duration_conflict")
            body: dict[str, Any] = {"model": route.upstream_model, "content": safe_content}
            if duration is not None:
                if isinstance(duration, bool) or not float(duration).is_integer():
                    raise ApiError("火山视频时长必须为整数秒", 422, "video_duration_invalid")
                normalized_duration = int(duration)
                minimum = int(route.capabilities.get("durationMin", 2))
                maximum = int(route.capabilities.get("durationMax", 12))
                smart = bool(route.capabilities.get("smartDuration"))
                if normalized_duration != -1 and not minimum <= normalized_duration <= maximum:
                    raise ApiError(
                        f"当前模型视频时长范围为{minimum}到{maximum}秒",
                        422,
                        "video_duration_invalid",
                    )
                if normalized_duration == -1 and not smart:
                    raise ApiError("当前模型不支持智能时长", 422, "video_duration_invalid")
                body["duration"] = normalized_duration
            if frames is not None:
                if (
                    not route.capabilities.get("frames")
                    or isinstance(frames, bool)
                    or not isinstance(frames, int)
                    or not 29 <= frames <= 289
                    or (frames - 25) % 4 != 0
                ):
                    raise ApiError("当前模型的frames参数无效", 422, "video_frames_invalid")
                body["frames"] = frames
            resolution = metadata.get("resolution")
            if resolution is not None:
                supported = route.capabilities.get("resolutions", [])
                if resolution not in supported:
                    raise ApiError("当前模型不支持该分辨率", 422, "video_resolution_invalid")
                body["resolution"] = resolution
            ratio = metadata.get("ratio")
            if ratio is not None:
                if ratio not in {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}:
                    raise ApiError("视频比例无效", 422, "video_ratio_invalid")
                body["ratio"] = ratio
            generate_audio = metadata.get("generate_audio")
            if generate_audio is not None:
                if not isinstance(generate_audio, bool) or not route.capabilities.get("generateAudio"):
                    raise ApiError("当前模型不支持生成音频", 422, "video_audio_unsupported")
                body["generate_audio"] = generate_audio
            draft = metadata.get("draft")
            if draft is not None:
                if not isinstance(draft, bool) or not route.capabilities.get("draft"):
                    raise ApiError("当前模型不支持样片模式", 422, "video_draft_unsupported")
                body["draft"] = draft
            for name in ("watermark", "return_last_frame"):
                if name in metadata:
                    if not isinstance(metadata[name], bool):
                        raise ApiError(f"{name}必须是布尔值", 422, "video_parameter_invalid")
                    body[name] = metadata[name]
            camera_fixed = metadata.get("camera_fixed")
            if camera_fixed is not None:
                if not isinstance(camera_fixed, bool) or route.alias.startswith("seedance-2.0"):
                    raise ApiError("当前模型不支持固定摄像头", 422, "video_camera_unsupported")
                if any(item["type"] != "text" for item in safe_content):
                    raise ApiError("参考素材场景不支持固定摄像头", 422, "video_camera_unsupported")
                body["camera_fixed"] = camera_fixed
            service_tier = metadata.get("service_tier")
            if service_tier is not None:
                if service_tier not in {"default", "flex"}:
                    raise ApiError("service_tier无效", 422, "video_service_tier_invalid")
                if service_tier == "flex" and route.alias.startswith("seedance-2.0"):
                    raise ApiError("Seedance 2.0不支持离线推理", 422, "video_service_tier_invalid")
                body["service_tier"] = service_tier
            expires_after = metadata.get("execution_expires_after")
            if expires_after is not None:
                if isinstance(expires_after, bool) or not isinstance(expires_after, int) or not 3600 <= expires_after <= 259200:
                    raise ApiError("execution_expires_after无效", 422, "video_expiration_invalid")
                body["execution_expires_after"] = expires_after
            if payload.get("seed") is not None:
                body["seed"] = payload["seed"]
            return "/contents/generations/tasks", body
        if route.provider == "aliyun_bailian":
            media = []
            if image:
                media.append({"type": "first_frame", "url": image})
            input_data: dict[str, Any] = {}
            if prompt:
                input_data["prompt"] = prompt
            if media:
                input_data["media"] = media
            parameters: dict[str, Any] = {
                "resolution": metadata.get("resolution", "1080P"),
                "ratio": metadata.get("ratio", "adaptive"),
                "prompt_extend": bool(metadata.get("prompt_extend", True)),
                "audio": bool(metadata.get("audio", True)),
            }
            if "aigc_watermark" in metadata:
                parameters["aigc_watermark"] = bool(metadata["aigc_watermark"])
            if duration is not None:
                parameters["duration"] = duration
            return "/services/aigc/video-generation/video-synthesis", {
                "model": route.upstream_model,
                "input": input_data,
                "parameters": parameters,
            }
        if route.provider == "minimax":
            content = metadata.get("content")
            if content is None:
                content = []
                if prompt:
                    content.append({"type": "text", "text": prompt})
                if image:
                    content.append(
                        {"type": "image_url", "image_url": {"url": image}, "role": "first_frame"}
                    )
            if not isinstance(content, list) or not content or len(content) > 20:
                raise ApiError("MiniMax content必须是最多20项的数组", 422, "video_content_invalid")
            safe_content: list[dict[str, Any]] = []
            for item in content:
                if not isinstance(item, dict) or item.get("type") not in {"text", "image_url"}:
                    raise ApiError("MiniMax content包含不支持的条目", 422, "video_content_invalid")
                if item["type"] == "text":
                    if set(item) - {"type", "text"} or not isinstance(item.get("text"), str):
                        raise ApiError("MiniMax文本条目格式无效", 422, "video_content_invalid")
                    safe_content.append({"type": "text", "text": item["text"][:40000]})
                    continue
                image_value = item.get("image_url")
                if not isinstance(image_value, dict) or set(image_value) - {"url"}:
                    raise ApiError("MiniMax图片条目格式无效", 422, "video_content_invalid")
                url = image_value.get("url")
                role = item.get("role", "first_frame")
                if (
                    set(item) - {"type", "image_url", "role"}
                    or not isinstance(url, str)
                    or not url.startswith(("https://", "http://"))
                    or role not in {"first_frame", "last_frame", "reference_image"}
                ):
                    raise ApiError("MiniMax图片条目格式无效", 422, "video_content_invalid")
                safe_content.append({"type": "image_url", "image_url": {"url": url}, "role": role})
            body: dict[str, Any] = {
                "model": route.upstream_model,
                "content": safe_content,
                "resolution": metadata.get("resolution", "768P"),
                "ratio": metadata.get("ratio", "adaptive"),
            }
            if duration is not None:
                body["duration"] = duration
            if payload.get("seed") is not None:
                body["seed"] = payload["seed"]
            if "aigc_watermark" in metadata:
                body["aigc_watermark"] = bool(metadata["aigc_watermark"])
            return "/v2/video_generation", body
        raise ApiError("该渠道不支持异步视频", 422, "video_provider_unsupported")

    @staticmethod
    def _ark_video_content(route: ModelRoute, content: Any) -> list[dict[str, Any]]:
        maximum = int(route.capabilities.get("maxContent", 20))
        if not isinstance(content, list) or not content or len(content) > maximum:
            raise ApiError(
                f"火山content必须是1到{maximum}项的数组",
                422,
                "video_content_invalid",
            )
        media_fields = {
            "image_url": ("image_url", "image", {"first_frame", "last_frame", "reference_image"}),
            "video_url": ("video_url", "video", {"reference_video"}),
            "audio_url": ("audio_url", "audio", {"reference_audio"}),
        }
        safe_content: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                raise ApiError("火山content包含无效条目", 422, "video_content_invalid")
            content_type = item.get("type")
            if content_type == "text":
                if set(item) - {"type", "text"} or not isinstance(item.get("text"), str) or not item["text"].strip():
                    raise ApiError("火山文本条目格式无效", 422, "video_content_invalid")
                safe_content.append({"type": "text", "text": item["text"][:40000]})
                continue
            spec = media_fields.get(str(content_type))
            if spec is None:
                raise ApiError("火山content包含不支持的条目", 422, "video_content_invalid")
            value_field, capability, roles = spec
            if not route.capabilities.get(capability):
                raise ApiError("当前模型不支持该参考素材类型", 422, "video_content_unsupported")
            value = item.get(value_field)
            role = item.get("role")
            url = value.get("url") if isinstance(value, dict) else None
            if (
                set(item) - {"type", value_field, "role"}
                or not isinstance(value, dict)
                or set(value) - {"url"}
                or not isinstance(url, str)
                or not url.startswith(("https://", "http://", "asset://"))
                or role not in roles
            ):
                raise ApiError("火山参考素材条目格式无效", 422, "video_content_invalid")
            safe_content.append({"type": content_type, value_field: {"url": url}, "role": role})
        if route.capabilities.get("imageRequired") and not any(item["type"] == "image_url" for item in safe_content):
            raise ApiError("当前模型必须提供参考图片", 422, "video_image_required")
        return safe_content

    async def create_video(
        self,
        principal: ApiPrincipal,
        alias: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        route = self.resolve(principal, alias)
        if route.modality != "video":
            raise ApiError("该模型不支持视频接口", 422, "model_modality_mismatch")
        path, upstream_payload = self._video_submit_payload(route, payload)
        task, created = self._create_task(principal, route, "video", payload, idempotency_key)
        if not created:
            return self._video_public(task)
        try:
            response, data = await self._request(route, "POST", path, upstream_payload)
            if route.provider == "aliyun_bailian":
                output = data.get("output") if isinstance(data.get("output"), dict) else {}
                upstream_task_id = output.get("task_id")
            elif route.provider == "volcengine_ark":
                upstream_task_id = data.get("id")
            else:
                upstream_task_id = data.get("task_id")
                if not upstream_task_id and isinstance(data.get("task"), dict):
                    upstream_task_id = data["task"].get("id")
            if not isinstance(upstream_task_id, (str, int)) or not str(upstream_task_id):
                raise ApiError("供应商未返回任务ID", 502, "provider_task_id_missing")
            provider_id = _provider_request_id(response.headers, data)
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE inference_tasks SET upstream_task_id=?,status='queued',provider_request_id=?,"
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (str(upstream_task_id), provider_id, task["id"]),
                )
        except ApiError as error:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE inference_tasks SET status='failed',error_code=?,error_message=?,"
                    "completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (error.code, error.message, task["id"]),
                )
            raise
        return self.get_local_task(principal, task["id"])

    def get_local_task(self, principal: ApiPrincipal, task_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM inference_tasks WHERE id=? AND api_key_id=? AND project_name=?",
                (task_id, principal.id, principal.project_name),
            ).fetchone()
        if row is None:
            raise ApiError("视频任务不存在", 404, "video_task_not_found")
        return dict(row)

    def _task_route(self, task: dict[str, Any]) -> ModelRoute:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT m.display_name,m.provider,m.modality,m.protocol,m.capabilities_json,
                       c.name AS channel_name,c.config_json,pc.secret_ciphertext
                FROM model_catalog m
                JOIN provider_channels c ON c.id=?
                JOIN provider_credentials pc ON pc.id=?
                WHERE m.alias=?
                """,
                (task["channel_id"], task["credential_id"], task["model_alias"]),
            ).fetchone()
        if row is None:
            raise ApiError("任务绑定的供应商配置不存在", 503, "task_channel_missing")
        return ModelRoute(
            alias=task["model_alias"],
            display_name=row["display_name"],
            provider=row["provider"],
            modality=row["modality"],
            protocol=row["protocol"],
            capabilities=_loaded(row["capabilities_json"], {}),
            upstream_model=task["upstream_model"],
            channel_id=task["channel_id"],
            channel_name=row["channel_name"],
            channel_config=_loaded(row["config_json"], {}),
            credential_id=task["credential_id"],
            secret=self.vault.decrypt(row["secret_ciphertext"]),
        )

    async def refresh_video(self, principal: ApiPrincipal, task_id: str) -> dict[str, Any]:
        task = self.get_local_task(principal, task_id)
        if task["status"] in TERMINAL_TASK_STATUSES or not task.get("upstream_task_id"):
            return self._video_public(task)
        route = self._task_route(task)
        upstream_id = task["upstream_task_id"]
        if route.provider == "aliyun_bailian":
            response, data = await self._request(route, "GET", f"/tasks/{upstream_id}")
            output = data.get("output") if isinstance(data.get("output"), dict) else {}
            raw_status = str(output.get("task_status") or "PENDING").upper()
            status_map = {
                "PENDING": "queued", "RUNNING": "running", "SUCCEEDED": "succeeded",
                "FAILED": "failed", "CANCELED": "canceled", "CANCELLED": "canceled",
            }
            status = status_map.get(raw_status, "running")
            result_url = output.get("video_url") or output.get("url")
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            seconds = output.get("video_duration") or usage.get("video_duration")
            error = output.get("message") or data.get("message")
            metadata = {"duration": seconds} if isinstance(seconds, (int, float)) else {}
        elif route.provider == "volcengine_ark":
            response, data = await self._request(
                route, "GET", f"/contents/generations/tasks/{upstream_id}"
            )
            raw_status = str(data.get("status") or "queued").lower()
            status_map = {
                "queued": "queued", "running": "running", "succeeded": "succeeded",
                "failed": "failed", "cancelled": "canceled", "canceled": "canceled",
                "expired": "failed",
            }
            status = status_map.get(raw_status, "running")
            content = data.get("content") if isinstance(data.get("content"), dict) else {}
            result_url = content.get("video_url") or content.get("url")
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            seconds_value = data.get("duration")
            try:
                seconds = float(seconds_value) if seconds_value is not None else None
            except (TypeError, ValueError):
                seconds = None
            error_data = data.get("error") if isinstance(data.get("error"), dict) else {}
            error = error_data.get("message")
            if raw_status == "expired" and not error:
                error = "火山视频任务已过期"
            metadata = {
                key: data[key]
                for key in ("resolution", "ratio", "duration", "frames", "framespersecond", "generate_audio")
                if data.get(key) is not None
            }
        else:
            response, data = await self._request(route, "GET", f"/v2/query/video_generation/{upstream_id}")
            upstream_task = data.get("task") if isinstance(data.get("task"), dict) else {}
            raw_status = str(upstream_task.get("status") or "queued").lower()
            status = "canceled" if raw_status == "cancelled" else raw_status
            if status not in TERMINAL_TASK_STATUSES | ACTIVE_TASK_STATUSES:
                status = "running"
            content = upstream_task.get("content") if isinstance(upstream_task.get("content"), dict) else {}
            result_url = content.get("url")
            usage = upstream_task.get("usage") if isinstance(upstream_task.get("usage"), dict) else {}
            seconds = usage.get("output_seconds") or upstream_task.get("duration")
            error_data = upstream_task.get("error") if isinstance(upstream_task.get("error"), dict) else {}
            error = error_data.get("message")
            metadata = {
                key: upstream_task[key]
                for key in ("resolution", "duration", "ratio")
                if upstream_task.get(key) is not None
            }
        provider_id = _provider_request_id(response.headers, data) or task.get("provider_request_id")
        progress = 100 if status in TERMINAL_TASK_STATUSES else (50 if status == "running" else 0)
        error_code = "provider_task_failed" if status == "failed" else None
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE inference_tasks SET status=?,progress=?,result_url=?,result_format=?,
                    error_code=?,error_message=?,provider_request_id=?,metadata_json=?,
                    completed_at=CASE WHEN ? IN ('succeeded','failed','canceled')
                        THEN COALESCE(completed_at,CURRENT_TIMESTAMP) ELSE completed_at END,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    status, progress, result_url, "mp4" if result_url else None,
                    error_code, str(error)[:500] if error else None, provider_id,
                    _json(metadata), status, task_id,
                ),
            )
        if status == "succeeded":
            self._record_usage(
                request_id=task_id,
                task_id=task_id,
                principal=principal,
                route=route,
                status="succeeded",
                provider_request_id=provider_id,
                usage=usage,
                video_seconds=float(seconds) if isinstance(seconds, (int, float)) else None,
            )
        return self._video_public(self.get_local_task(principal, task_id))

    def content_url(self, principal: ApiPrincipal, task_id: str) -> str:
        task = self.get_local_task(principal, task_id)
        if task["status"] != "succeeded" or not task.get("result_url"):
            raise ApiError("视频任务尚无可下载结果", 409, "video_content_unavailable")
        return str(task["result_url"])

    def usage(
        self,
        *,
        project_name: str | None,
        key_id: str | None,
        model: str | None,
        provider: str | None,
        start: str | None,
        end: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_name:
            clauses.append("u.project_name=?")
            params.append(project_name)
        if key_id:
            clauses.append("u.api_key_id=?")
            params.append(key_id)
        if model:
            clauses.append("u.model_alias=?")
            params.append(model)
        if provider:
            clauses.append("c.provider=?")
            params.append(provider)
        if start:
            clauses.append("u.created_at>=?")
            params.append(start)
        if end:
            clauses.append("u.created_at<?")
            params.append(end)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT u.*,c.provider,c.name AS channel_name FROM inference_usage u "
                "JOIN provider_channels c ON c.id=u.channel_id" + where +
                " ORDER BY u.created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [
            {
                "id": row["id"], "requestId": row["request_id"], "taskId": row["task_id"],
                "projectName": row["project_name"], "apiKeyId": row["api_key_id"],
                "model": row["model_alias"], "provider": row["provider"],
                "channelName": row["channel_name"], "status": row["status"],
                "inputTokens": row["input_tokens"], "outputTokens": row["output_tokens"],
                "totalTokens": row["total_tokens"], "generatedImages": row["generated_images"],
                "videoSeconds": row["video_seconds"], "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def tasks(self, *, project_name: str | None, key_id: str | None, model: str | None, limit: int) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_name:
            clauses.append("project_name=?")
            params.append(project_name)
        if key_id:
            clauses.append("api_key_id=?")
            params.append(key_id)
        if model:
            clauses.append("model_alias=?")
            params.append(model)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM inference_tasks" + where + " ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        return [self._video_public(dict(row)) if row["operation"] == "video" else {
            "id": row["id"], "object": "image", "model": row["model_alias"],
            "status": row["status"], "created_at": row["created_at"],
        } for row in rows]
