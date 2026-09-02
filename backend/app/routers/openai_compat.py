from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from ..errors import ApiError
from ..schemas import OpenAIVideoRequest
from ..security import PrincipalDependency


router = APIRouter(prefix="/v1", tags=["OpenAI兼容模型中转"])

FORBIDDEN_ROUTE_FIELDS = {
    "provider", "channel", "channel_id", "base_url", "api_key", "project", "project_name"
}
IMAGE_FIELDS = {
    "model", "prompt", "n", "size", "quality", "style", "response_format", "user",
    "background", "moderation", "output_compression", "output_format", "image", "stream",
    "sequential_image_generation", "sequential_image_generation_options", "watermark",
    "optimize_prompt_options", "tools", "guidance_scale", "seed",
}
CHAT_FIELDS = {
    "model", "messages", "stream", "stream_options", "frequency_penalty", "function_call",
    "functions", "logit_bias", "logprobs", "top_logprobs", "max_completion_tokens",
    "max_tokens", "n", "parallel_tool_calls", "presence_penalty", "reasoning_effort",
    "response_format", "seed", "service_tier", "stop", "store", "temperature",
    "tool_choice", "tools", "top_p", "user", "metadata",
}
RESPONSE_FIELDS = {
    "model", "input", "stream", "background", "conversation", "include", "instructions",
    "max_output_tokens", "max_tool_calls", "metadata", "parallel_tool_calls",
    "previous_response_id", "prompt", "reasoning", "safety_identifier", "service_tier",
    "store", "stream_options", "temperature", "text", "tool_choice", "tools",
    "top_logprobs", "top_p", "truncation", "user",
}


def _payload(value: Any) -> dict[str, Any]:
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
    model = value.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise ApiError("model不能为空", 422, "model_required")
    return dict(value)


@router.get("/models")
def models(request: Request, principal: PrincipalDependency) -> dict:
    return {"object": "list", "data": request.app.state.provider_relay.available_models(principal)}


async def _text(
    operation: str,
    request: Request,
    principal: PrincipalDependency,
    raw: dict[str, Any],
):
    payload = _payload(raw)
    allowed = CHAT_FIELDS if operation == "chat" else RESPONSE_FIELDS
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ApiError(
            "文本请求包含不支持的字段",
            422,
            "text_parameter_unsupported",
            details={"fields": unknown},
        )
    if "stream" in payload and not isinstance(payload["stream"], bool):
        raise ApiError("stream必须是布尔值", 422, "stream_parameter_invalid", details={"param": "stream"})
    alias = str(payload["model"]).strip()
    stream = payload.get("stream") is True
    if stream:
        return StreamingResponse(
            request.app.state.provider_relay.text_stream(principal, alias, operation, payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    data, request_id = await request.app.state.provider_relay.text_json(
        principal, alias, operation, payload
    )
    headers = {"X-Request-Id": request_id} if request_id else None
    return JSONResponse(content=data, headers=headers)


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
):
    return await _text("chat", request, principal, raw)


@router.post("/responses")
async def responses(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
):
    return await _text("responses", request, principal, raw)


@router.post("/images/generations")
async def images_generations(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    payload = _payload(raw)
    unknown = sorted(set(payload) - IMAGE_FIELDS)
    if unknown:
        raise ApiError(
            "图片请求包含不支持的字段",
            422,
            "image_parameter_unsupported",
            details={"fields": unknown},
        )
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32000:
        raise ApiError("prompt不能为空或过长", 422, "image_prompt_invalid")
    if "n" in payload and (not isinstance(payload["n"], int) or isinstance(payload["n"], bool) or not 1 <= payload["n"] <= 10):
        raise ApiError("n必须是1到10的整数", 422, "image_count_invalid", details={"param": "n"})
    if payload.get("response_format", "url") not in {"url", "b64_json"}:
        raise ApiError("response_format仅支持url或b64_json", 422, "image_response_format_invalid")
    if "stream" in payload and not isinstance(payload["stream"], bool):
        raise ApiError("stream必须是布尔值", 422, "stream_parameter_invalid", details={"param": "stream"})
    if idempotency_key is not None and not (1 <= len(idempotency_key) <= 128):
        raise ApiError("Idempotency-Key长度无效", 422, "idempotency_key_invalid")
    alias = str(payload["model"]).strip()
    data = await request.app.state.provider_relay.generate_image(
        principal, alias, payload, idempotency_key
    )
    return JSONResponse(content=data)


@router.post("/videos")
async def create_video(
    payload: OpenAIVideoRequest,
    request: Request,
    principal: PrincipalDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if idempotency_key is not None and not (1 <= len(idempotency_key) <= 128):
        raise ApiError("Idempotency-Key长度无效", 422, "idempotency_key_invalid")
    body = payload.model_dump(by_alias=False, exclude_none=True)
    data = await request.app.state.provider_relay.create_video(
        principal, payload.model, body, idempotency_key
    )
    return JSONResponse(status_code=202, content=data)


@router.get("/videos/{task_id}")
async def get_video(task_id: str, request: Request, principal: PrincipalDependency):
    return await request.app.state.provider_relay.refresh_video(principal, task_id)


@router.get("/videos/{task_id}/content")
def get_video_content(task_id: str, request: Request, principal: PrincipalDependency):
    return RedirectResponse(
        request.app.state.provider_relay.content_url(principal, task_id), status_code=307
    )


@router.head("/videos/{task_id}/content")
def head_video_content(task_id: str, request: Request, principal: PrincipalDependency):
    return RedirectResponse(
        request.app.state.provider_relay.content_url(principal, task_id), status_code=307
    )
