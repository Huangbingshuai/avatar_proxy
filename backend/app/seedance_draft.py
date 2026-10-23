"""Seedance 2.5 Draft validation; IDs exposed to clients are local task IDs."""
import json
from typing import Any

from .errors import ApiError

MODEL = "doubao-seedance-2.5"
TTL_SECONDS = 7 * 24 * 60 * 60


def supported(route: Any) -> bool:
    return route.provider == "volcengine_ark" and route.alias == MODEL and route.capabilities.get("draft") is True


def reference_id(route: Any, content: Any) -> str | None:
    if not isinstance(content, list) or not any(isinstance(item, dict) and item.get("type") == "draft_task" for item in content):
        return None
    if not supported(route):
        raise ApiError("当前渠道或模型不支持样片转成片", 422, "video_draft_unsupported")
    if len(content) != 1 or not isinstance(content[0], dict):
        raise ApiError("content只能包含一个draft_task", 422, "video_draft_reference_invalid")
    item = content[0]
    value = item.get("draft_task")
    if (set(item) != {"type", "draft_task"}
            or not isinstance(value, dict) or set(value) != {"id"}
            or not isinstance(value["id"], str) or not value["id"].startswith("vid_")
            or not 5 <= len(value["id"]) <= 128):
        raise ApiError("content只能包含一个draft_task，id必须为本站样片任务ID", 422, "video_draft_reference_invalid")
    return value["id"]


def validate(route: Any, payload: dict[str, Any]) -> str | None:
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    parent = reference_id(route, meta.get("content"))
    if not supported(route):
        return parent
    if "draft" in meta and not isinstance(meta["draft"], bool):
        raise ApiError("draft必须为布尔值", 422, "video_draft_invalid")
    if parent:
        if meta.get("draft") is True or meta.get("resolution") != "1080p":
            raise ApiError("样片转成片必须指定1080p，draft须省略或为false", 422, "video_draft_final_invalid")
        forbidden = sorted(set(meta) & {"ratio", "generate_audio", "frames", "camera_fixed", "task_type", "omni_reference_task_type"})
        forbidden += [name for name in ("duration", "seed") if name in payload]
        forbidden += [name for name in ("prompt", "image") if payload.get(name)]
        if forbidden:
            raise ApiError("成片自动继承样片参数，请勿重复传入", 422, "video_draft_parameter_conflict", details={"fields": forbidden})
    elif meta.get("draft") is True and meta.get("resolution") != "480p":
        raise ApiError("Draft样片必须明确指定resolution=480p", 422, "video_draft_resolution_invalid")
    return parent


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def source_context(source: dict[str, Any], route: Any, now: int) -> dict[str, Any]:
    billing = _object(source.get("billing_metadata_json"))
    metadata = _object(source.get("metadata_json"))
    if source["operation"] != "video" or source["model_alias"] != route.alias or billing.get("draft") is not True:
        raise ApiError("引用的任务不是当前模型的Draft样片", 422, "video_draft_source_invalid")
    if source["status"] != "succeeded" or not source.get("upstream_task_id"):
        raise ApiError("样片尚未成功，不能生成成片", 409, "video_draft_not_ready")
    if metadata.get("draft") is not True or metadata.get("resolution") != "480p":
        raise ApiError("供应商尚未确认成功的480p样片，请核对原任务", 409, "video_draft_unverified")
    created = source.get("created_at")
    if type(created) is not int or created <= 0 or created > now:
        raise ApiError("样片创建时间无效，不能生成成片", 409, "video_draft_source_invalid")
    if now >= created + TTL_SECONDS:
        raise ApiError("样片创建已满7天，请重新生成样片", 410, "video_draft_expired")
    if source["channel_id"] != route.channel_id or source["upstream_model"] != route.upstream_model:
        raise ApiError("样片与当前模型渠道不一致，请恢复原渠道绑定或重新生成样片", 409, "video_draft_route_changed")
    if type(billing.get("containsVideoInput")) is not bool:
        raise ApiError("样片缺少原始输入计费信息，不能生成成片", 409, "video_draft_usage_unknown")
    return {"draft": False, "draftTaskId": source["id"], "containsVideoInput": billing["containsVideoInput"]}


def public_metadata(task: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    billing = _object(task.get("billing_metadata_json"))
    result = dict(metadata)
    if isinstance(billing.get("draft"), bool):
        if not isinstance(result.get("draft"), bool):
            result["draft"] = billing["draft"]
        if billing["draft"]:
            result["draft_expires_at"] = int(task["created_at"]) + TTL_SECONDS
        if billing.get("draftTaskId"):
            result["draft_task_id"] = billing["draftTaskId"]
    return result
