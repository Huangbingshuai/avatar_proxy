"""Allowlisted Vega material/liveness API; never an arbitrary VOD proxy."""
import asyncio
import hashlib
import json
from typing import Any

from .errors import ApiError
from .vega import media_url

ACTIONS = {
    "CreateAigcMaterial": {"FileInfo", "AssetType", "GroupId", "AssetName", "IsRealPerson", "GroupName", "GroupDescription"},
    "DescribeTaskDetail": {"TaskId"},
    "CreateAigcLivenessValidate": set(),
    "DescribeAigcLivenessValidateResult": {"LivenessToken"},
    "DescribeAigcMaterial": {"AssetId"},
    "DeleteAigcMaterial": {"AssetId", "GroupId"},
    "ModifyAigcMaterial": {"AssetId", "AssetName"},
    "ModifyAigcMaterialGroup": {"GroupId", "GroupName", "GroupDescription"},
    "DescribeAigcMaterialGroup": {"GroupId"},
    "DescribeAigcMaterialList": {"GroupId", "AssetType", "Limit", "Offset"},
}
TEXT_LIMITS = {"AssetName": 1024, "GroupName": 64, "GroupDescription": 1024}


class VegaResources:
    def __init__(self, relay):
        self.relay = relay
        self.database = relay.database

    def recover_interrupted_creates(self):
        # Single-instance startup only: never resend an ambiguous material or
        # liveness POST. Accepted material tasks retain their upstream IDs.
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE inference_tasks SET status='failed',error_code='provider_outcome_unknown',"
                "error_message='服务重启前的素材或活体创建结果未确认，请联系管理员核对，勿重复提交',"
                "metadata_json=?,completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP "
                "WHERE operation IN ('vega_CreateAigcMaterial','vega_CreateAigcLivenessValidate') "
                "AND status IN ('queued','running') AND upstream_task_id IS NULL",
                (json.dumps({"outcomeUnknown": True}),),
            )

    def register(self, principal, route, kind, value, group=None, source_task=None):
        if isinstance(value, str) and value:
            with self.database.connect() as connection:
                connection.execute("INSERT OR IGNORE INTO vega_resources(api_key_id,project_name,channel_id,kind,resource_hash,group_hash,source_task_id) VALUES (?,?,?,?,?,?,?)",
                                   (principal.id, principal.project_name, route.channel_id, kind, hashlib.sha256(value.encode()).hexdigest(),
                                    hashlib.sha256(group.encode()).hexdigest() if isinstance(group, str) and group else None, source_task))

    def owns(self, principal, route, kind, value):
        if not isinstance(value, str) or not value or len(value) > 2048:
            raise ApiError("Vega素材标识无效", 422, "vega_resource_invalid")
        with self.database.connect() as connection:
            row = connection.execute("SELECT 1 FROM vega_resources WHERE api_key_id=? AND project_name=? AND channel_id=? AND kind=? AND resource_hash=?",
                                     (principal.id, principal.project_name, route.channel_id, kind, hashlib.sha256(value.encode()).hexdigest())).fetchone()
        if row is None:
            raise ApiError("Vega素材不属于当前项目、Key及渠道，或已删除", 404, "vega_resource_not_found")

    async def call(self, principal, alias: str, action: str, payload: dict[str, Any], idempotency_key: str | None):
        if action not in ACTIONS:
            raise ApiError("不支持该Vega素材操作", 404, "vega_action_not_supported")
        if set(payload) - ACTIONS[action]:
            raise ApiError("Vega素材请求包含不支持的字段", 422, "vega_parameter_invalid")
        if action == "DescribeTaskDetail":
            local = self.relay.get_local_task(principal, str(payload.get("TaskId", "")))
            if local["operation"] != "vega_CreateAigcMaterial" or local["model_alias"] != alias:
                raise ApiError("Vega素材任务不存在", 404, "vega_resource_not_found")
            route = self.relay._task_route(local)
            if not local.get("upstream_task_id"):
                meta = json.loads(local.get("metadata_json") or "{}")
                result = {"id": local["id"], "status": local["status"]}
                if local.get("error_code"):
                    result.update({"error": {"code": local["error_code"], "message": local.get("error_message")},
                                   "outcomeUnknown": bool(meta.get("outcomeUnknown")), "automaticRetry": False})
                return result
            _, data = await self.relay._vega_request(route, action, {"TaskId": local["upstream_task_id"]})
            task = data.get("CreateAigcMaterialTask")
            if not isinstance(task, dict):
                raise ApiError("Vega素材任务响应无效", 502, "provider_response_invalid")
            status = "running"
            if task.get("Status") == "FINISH" and task.get("ErrCode") == 0:
                output = task.get("Output") or {}
                if not isinstance(output, dict) or not output.get("AssetId"):
                    raise ApiError("Vega未返回素材ID", 502, "provider_response_invalid")
                # Re-reading a completed task must not resurrect a deleted asset.
                if local["status"] != "succeeded":
                    self.register(principal, route, "AssetId", output["AssetId"], output.get("GroupId"))
                    self.register(principal, route, "GroupId", output.get("GroupId"))
                status = "succeeded"
            elif task.get("Status", data.get("Status")) == "FINISH":
                status = "failed"
            with self.database.connect() as connection:
                connection.execute("UPDATE inference_tasks SET status=?,updated_at=CURRENT_TIMESTAMP,completed_at=CASE WHEN ? IN ('succeeded','failed') THEN COALESCE(completed_at,CURRENT_TIMESTAMP) ELSE completed_at END WHERE id=?",
                                   (status, status, local["id"]))
            return {"id": local["id"], "Response": data}
        source_task = None
        if action == "DescribeAigcLivenessValidateResult":
            token = payload.get("LivenessToken")
            if not isinstance(token, str) or not token or len(token) > 2048:
                raise ApiError("活体认证令牌无效", 422, "vega_resource_invalid")
            with self.database.connect() as connection:
                resource = connection.execute("SELECT source_task_id FROM vega_resources WHERE api_key_id=? AND project_name=? AND kind='LivenessToken' AND resource_hash=?",
                                              (principal.id, principal.project_name, hashlib.sha256(token.encode()).hexdigest())).fetchone()
            if resource is None or not resource["source_task_id"]:
                raise ApiError("活体认证记录不存在", 404, "vega_resource_not_found")
            source_task = resource["source_task_id"]
            task = self.relay.get_local_task(principal, source_task)
            if task["model_alias"] != alias:
                raise ApiError("活体认证记录不存在", 404, "vega_resource_not_found")
            route = self.relay._task_route(task)
        else:
            route = self.relay.resolve(principal, alias)
        if (route.provider != "vega" or route.modality != "video"
                or route.upstream_model not in {"1.0-pro", "1.0-pro-fast", "1.0-pro-mini", "1.5-pro"}):
            raise ApiError("该接口仅支持Vega Pro系列渠道", 422, "vega_resource_unsupported")
        body = dict(payload)
        if "Liveness" in action and route.channel_config["site"] != "domestic":
            raise ApiError("国际站不需要此活体认证接口", 422, "vega_liveness_unsupported")
        for field, limit in TEXT_LIMITS.items():
            if field in body and (not isinstance(body[field], str) or len(body[field]) > limit):
                raise ApiError(f"{field}须为字符串且不超过{limit}字符", 422, "vega_parameter_invalid")
        if action == "CreateAigcMaterial":
            file_info = body.get("FileInfo")
            if not isinstance(file_info, dict) or set(file_info) != {"Type", "Url"} or file_info["Type"] != "Url":
                raise ApiError("FileInfo须为Type=Url和HTTP(S) Url", 422, "vega_parameter_invalid")
            body["FileInfo"] = {"Type": "Url", "Url": media_url(file_info["Url"], assets=False)}
            if body.get("AssetType") not in ("Image", "Video", "Audio") or body.get("IsRealPerson", "False") not in ("True", "False"):
                raise ApiError("AssetType或IsRealPerson无效", 422, "vega_parameter_invalid")
            body.setdefault("IsRealPerson", "False")
            if "GroupId" not in body:
                if body["IsRealPerson"] == "True":
                    raise ApiError("真人素材须提供活体认证返回的GroupId", 422, "vega_parameter_invalid")
                body["GroupId"] = "vg_" + hashlib.sha256(f"{principal.id}:{route.channel_id}".encode()).hexdigest()[:40]
                # VOD's default name combines account and group IDs and can
                # exceed its own 64-character modification limit. Supply a
                # bounded name for a NEW isolated group, but never overwrite
                # the name of an already-registered customer group.
                with self.database.connect() as connection:
                    known_group = connection.execute(
                        "SELECT 1 FROM vega_resources WHERE api_key_id=? AND project_name=? "
                        "AND channel_id=? AND kind='GroupId' AND resource_hash=?",
                        (principal.id, principal.project_name, route.channel_id,
                         hashlib.sha256(body["GroupId"].encode()).hexdigest()),
                    ).fetchone()
                if known_group is None:
                    body.setdefault("GroupName", "vega_" + body["GroupId"][3:35])
            else:
                self.owns(principal, route, "GroupId", body["GroupId"])
        else:
            required = {"DescribeAigcLivenessValidateResult": "LivenessToken", "DescribeAigcMaterial": "AssetId",
                        "ModifyAigcMaterial": "AssetId", "ModifyAigcMaterialGroup": "GroupId",
                        "DescribeAigcMaterialGroup": "GroupId", "DescribeAigcMaterialList": "GroupId"}.get(action)
            if required:
                self.owns(principal, route, required, body.get(required))
            if action == "DeleteAigcMaterial":
                if len(set(body) & {"AssetId", "GroupId"}) != 1:
                    raise ApiError("删除须且只能提供AssetId或GroupId之一", 422, "vega_parameter_invalid")
                for field, value in body.items():
                    self.owns(principal, route, field, value)
            if action == "ModifyAigcMaterial" and not body.get("AssetName"):
                raise ApiError("AssetName不能为空", 422, "vega_parameter_invalid")
            if action == "DescribeAigcMaterialList":
                limit, offset = body.get("Limit", 10), body.get("Offset", 0)
                if (type(limit) is not int or type(offset) is not int or not 1 <= limit <= 300 or offset < 0 or offset % limit
                        or "AssetType" in body and body["AssetType"] not in ("Image", "Video", "Audio")):
                    raise ApiError("素材列表分页或类型无效", 422, "vega_parameter_invalid")
        local = None
        if action.startswith("Create"):
            if not idempotency_key:
                raise ApiError("Vega素材/活体创建必须提供Idempotency-Key", 422, "idempotency_key_required")
            local, created = self.relay._create_task(principal, route, "vega_" + action, {"model": alias, **payload}, idempotency_key)
            if not created:
                meta = json.loads(local.get("metadata_json") or "{}")
                if meta.get("encryptedResponse"):
                    return json.loads(self.relay.vault.decrypt(meta["encryptedResponse"]))
                if local.get("error_code") and not meta.get("outcomeUnknown"):
                    raise ApiError(local.get("error_message") or "供应商拒绝了创建请求", meta.get("errorStatus", 502),
                                   local["error_code"], details={**meta.get("errorDetails", {}),
                                   "taskId": local["id"], "outcomeUnknown": False, "automaticRetry": False})
                raise ApiError("该创建请求已受理或结果待核对，请勿更换幂等键重试", 409, "idempotency_request_in_progress",
                               details={"taskId": local["id"], "outcomeUnknown": True, "automaticRetry": False})
            body["SessionId"] = local["id"] if action == "CreateAigcMaterial" else None
            if body["SessionId"] is None:
                body.pop("SessionId")
        try:
            _, data = await self.relay._vega_request(route, action, body)
            if action == "CreateAigcLivenessValidate" and (
                    not isinstance(data.get("LivenessToken"), str) or not data["LivenessToken"]
                    or not isinstance(data.get("H5Link"), str) or not data["H5Link"]):
                raise ApiError("Vega未返回完整活体认证入口", 502, "provider_response_invalid")
            if action == "CreateAigcMaterial" and (
                    not isinstance(data.get("TaskId"), str) or not data["TaskId"]):
                raise ApiError("Vega未返回素材任务ID", 502, "provider_task_id_missing")
        except (ApiError, asyncio.CancelledError) as error:
            if local:
                unknown = not isinstance(error, ApiError) or error.code != "vega_request_failed"
                code = error.code if isinstance(error, ApiError) else "provider_outcome_unknown"
                message = error.message if isinstance(error, ApiError) else "创建提交中断，请核对供应商结果，勿重复提交"
                meta = {"outcomeUnknown": unknown}
                if isinstance(error, ApiError):
                    meta.update({"errorStatus": error.status_code, "errorDetails": error.details})
                    error.details = {**error.details, "taskId": local["id"], "outcomeUnknown": unknown, "automaticRetry": False}
                with self.database.connect() as connection:
                    connection.execute(
                        "UPDATE inference_tasks SET status='failed',error_code=?,error_message=?,metadata_json=?,"
                        "completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (code, message, json.dumps(meta), local["id"]),
                    )
            raise
        if action == "CreateAigcMaterial":
            self.register(principal, route, "GroupId", body["GroupId"])
        if action in {"CreateAigcLivenessValidate", "DescribeAigcLivenessValidateResult"}:
            source_task = local["id"] if local else source_task
            self.register(principal, route, "LivenessToken", data.get("LivenessToken"), source_task=source_task)
            self.register(principal, route, "GroupId", data.get("GroupId"), source_task=source_task)
        result = {"id": local["id"], "Response": data} if local else {"Response": data}
        if local:
            with self.database.connect() as connection:
                connection.execute("UPDATE inference_tasks SET upstream_task_id=?,metadata_json=?,status=?,updated_at=CURRENT_TIMESTAMP,completed_at=CASE WHEN ?='CreateAigcLivenessValidate' THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id=?",
                                   (data.get("TaskId"), json.dumps({"encryptedResponse": self.relay.vault.encrypt(json.dumps(result))}),
                                    "queued" if action == "CreateAigcMaterial" else "succeeded", action, local["id"]))
        if action == "DeleteAigcMaterial":
            # Leave a conservative tombstone: resources in a deleted group are no
            # longer accepted even if a caller retained an old asset:// URL.
            with self.database.connect() as connection:
                if "GroupId" in body:
                    connection.execute("DELETE FROM vega_resources WHERE api_key_id=? AND channel_id=? AND kind='AssetId' AND group_hash=?",
                                       (principal.id, route.channel_id, hashlib.sha256(body["GroupId"].encode()).hexdigest()))
                field, value = next(iter(body.items()))
                connection.execute("DELETE FROM vega_resources WHERE api_key_id=? AND channel_id=? AND kind=? AND resource_hash=?",
                                   (principal.id, route.channel_id, field, hashlib.sha256(value.encode()).hexdigest()))
        return result
