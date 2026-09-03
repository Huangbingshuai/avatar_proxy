from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse, Response

from ..errors import ApiError
from ..security import PrincipalDependency


router = APIRouter(prefix="/api/v3", tags=["火山方舟兼容视频中转"])

ARK_VIDEO_FIELDS = {
    "model",
    "content",
    "duration",
    "frames",
    "resolution",
    "ratio",
    "generate_audio",
    "draft",
    "seed",
    "camera_fixed",
    "watermark",
    "return_last_frame",
    "service_tier",
    "execution_expires_after",
    "task_type",
}
FORBIDDEN_ROUTE_FIELDS = {
    "provider",
    "channel",
    "channel_id",
    "base_url",
    "api_key",
    "project",
    "project_name",
}


def _video_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError("请求体必须是JSON对象", 422, "invalid_request_body")
    forbidden = sorted(FORBIDDEN_ROUTE_FIELDS & set(value))
    if forbidden:
        raise ApiError(
            "请求不能指定供应商、渠道、项目或Base URL",
            422,
            "route_override_forbidden",
            details={"fields": forbidden},
        )
    unknown = sorted(set(value) - ARK_VIDEO_FIELDS)
    if unknown:
        raise ApiError(
            "视频请求包含火山兼容接口不支持的字段",
            422,
            "video_parameter_unsupported",
            details={"fields": unknown},
        )
    model = value.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise ApiError("model不能为空", 422, "model_required")
    return dict(value)


def _idempotency_key(value: str | None) -> str | None:
    if value is not None and not 1 <= len(value) <= 128:
        raise ApiError("Idempotency-Key长度无效", 422, "idempotency_key_invalid")
    return value


@router.post("/contents/generations/tasks")
async def create_video_task(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[Any, Body()],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    payload = _video_payload(raw)
    data = await request.app.state.provider_relay.create_ark_video(
        principal,
        str(payload["model"]).strip(),
        payload,
        _idempotency_key(idempotency_key),
    )
    return JSONResponse(content={"id": data["id"]})


@router.get("/contents/generations/tasks/{task_id}")
async def get_video_task(task_id: str, request: Request, principal: PrincipalDependency):
    return await request.app.state.provider_relay.refresh_ark_video(principal, task_id)


@router.delete("/contents/generations/tasks/{task_id}")
async def delete_video_task(task_id: str, request: Request, principal: PrincipalDependency):
    await request.app.state.provider_relay.cancel_ark_video(principal, task_id)
    return Response(status_code=204)
