"""Persisted Vega image tasks shared by async and OpenAI-compatible clients."""
from __future__ import annotations

import asyncio
import json
import time

from . import vega_image
from .errors import ApiError


class VegaImages:
    def __init__(self, relay):
        self.relay = relay
        self.database = relay.database

    @staticmethod
    def public(task):
        meta = json.loads(task.get("metadata_json") or "{}")
        result = {"id": task["id"], "object": "image_task", "model": task["model_alias"],
                  "status": task["status"], "progress": int(task.get("progress") or 0)}
        if task["status"] == "succeeded":
            result["result"] = meta.get("response")
        if task.get("error_code"):
            result["error"] = {"code": task["error_code"], "message": task.get("error_message")}
        return result

    def local(self, principal, task_id):
        task = self.relay.get_local_task(principal, task_id)
        if task["operation"] != "image" or task["model_alias"] not in vega_image.MODELS:
            raise ApiError("生图任务不存在", 404, "image_task_not_found")
        return task

    async def create(self, principal, alias, payload, idempotency_key):
        route = self.relay.resolve(principal, alias)
        if route.provider != "vega" or route.alias not in vega_image.MODELS:
            raise ApiError("该模型不支持Vega异步生图接口", 422, "image_provider_unsupported")
        upstream = vega_image.submit_payload(route, payload)
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise ApiError("Vega生图须提供1到128字符的Idempotency-Key", 422, "idempotency_key_required")
        task, created = self.relay._create_task(principal, route, "image", payload, idempotency_key)
        if not created:
            return self.public(self.local(principal, task["id"]))
        upstream["SessionId"] = task["id"]
        with self.database.connect() as c:
            c.execute("UPDATE inference_tasks SET metadata_json=? WHERE id=?", (json.dumps({"vegaAsync": True}), task["id"]))
        try:
            _, data = await self.relay._vega_request(route, "CreateAigcImageTask", upstream)
            upstream_id = data.get("TaskId")
            if not isinstance(upstream_id, str) or not upstream_id or len(upstream_id) > 2048:
                raise ApiError("Vega未返回生图任务ID，请联系管理员核对，勿重复生成", 502,
                               "provider_task_id_missing", details={"outcomeUnknown": True})
        except (ApiError, asyncio.CancelledError) as error:
            unknown = isinstance(error, asyncio.CancelledError) or error.code != "vega_request_failed"
            code = error.code if isinstance(error, ApiError) else "provider_outcome_unknown"
            message = error.message if isinstance(error, ApiError) else "任务提交中断，请核对供应商结果"
            with self.database.connect() as c:
                c.execute("UPDATE inference_tasks SET status='failed',error_code=?,error_message=?,metadata_json=?,"
                          "updated_at=CURRENT_TIMESTAMP,completed_at=CURRENT_TIMESTAMP WHERE id=?",
                          (code, message, json.dumps({"vegaAsync": True, "outcomeUnknown": unknown}), task["id"]))
            if unknown:
                self.relay._record_usage(request_id=task["id"], task_id=task["id"], principal=principal, route=route, status="unknown")
            raise
        with self.database.connect() as c:
            c.execute("UPDATE inference_tasks SET upstream_task_id=?,provider_request_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (upstream_id, data.get("RequestId"), task["id"]))
        return self.public(self.local(principal, task["id"]))

    def record_success(self, principal, task):
        meta = json.loads(task.get("metadata_json") or "{}")
        response = meta.get("response")
        if isinstance(response, dict) and isinstance(response.get("data"), list) and response["data"]:
            self.relay._record_usage(request_id=task["id"], task_id=task["id"], principal=principal,
                                     route=self.relay._task_route(task), status="succeeded",
                                     provider_request_id=task.get("provider_request_id"), generated_images=len(response["data"]))

    async def refresh(self, principal, task_id):
        task = self.local(principal, task_id)
        if task["status"] in ("succeeded", "failed", "canceled") or not task.get("upstream_task_id"):
            if task["status"] == "succeeded":
                self.record_success(principal, task)
            return self.public(task)
        route = self.relay._task_route(task)
        _, data = await self.relay._vega_request(route, "DescribeTaskDetail", {"TaskId": task["upstream_task_id"]})
        result = vega_image.task_result(data)
        meta = {"vegaAsync": True}
        if result["status"] == "succeeded":
            meta.update({"vegaInputImageCount": result["input_count"], "response": {
                "created": int(task["created_at"]), "model": route.alias, "task_id": task_id, "data": result["data"]}})
        progress = result.get("progress", 0)
        progress = min(100, max(0, progress)) if type(progress) is int else 0
        with self.database.connect() as c:
            c.execute("UPDATE inference_tasks SET status=?,progress=?,metadata_json=?,provider_request_id=?,error_code=?,error_message=?,"
                      "updated_at=CURRENT_TIMESTAMP,completed_at=CASE WHEN ? IN ('succeeded','failed') THEN CURRENT_TIMESTAMP ELSE completed_at END "
                      "WHERE id=? AND status IN ('queued','running')",
                      (result["status"], progress, json.dumps(meta), data.get("RequestId"), result.get("error_code"),
                       result.get("error"), result["status"], task_id))
        task = self.local(principal, task_id)
        if task["status"] == "succeeded":
            self.record_success(principal, task)
        return self.public(task)

    async def generate(self, principal, alias, payload, idempotency_key):
        created = await self.create(principal, alias, payload, idempotency_key)
        deadline = time.monotonic() + self.relay.settings.model_generation_timeout_seconds
        while True:
            result = await self.refresh(principal, created["id"])
            if result["status"] == "succeeded":
                return result["result"]
            if result["status"] in ("failed", "canceled"):
                error = result.get("error") or {}
                raise ApiError(error.get("message") or "Vega生图失败", 502,
                               error.get("code") or "provider_task_failed", details={"taskId": created["id"], "automaticRetry": False})
            if time.monotonic() >= deadline:
                raise ApiError("生图仍在处理中，请使用返回的taskId查询", 504, "image_task_pending",
                               details={"taskId": created["id"], "outcomeUnknown": False, "automaticRetry": False})
            await asyncio.sleep(2)
