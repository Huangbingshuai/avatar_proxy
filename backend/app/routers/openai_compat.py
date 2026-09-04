from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..errors import ApiError
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
EMBEDDING_FIELDS = {
    "model", "input", "encoding_format", "dimensions", "user", "instructions",
    "sparse_embedding",
}
MULTIMODAL_EMBEDDING_FIELDS = {
    "model", "input", "encoding_format", "dimensions", "instructions",
}
SPEECH_FIELDS = {"model", "input", "voice", "response_format", "speed", "sample_rate"}
TRANSCRIPTION_FIELDS = {"model", "url", "language", "enable_speaker_info"}
AUDIO_GENERATION_FIELDS = {
    "model", "prompt", "speaker", "audio_url", "audio_data", "image_url", "image_data",
    "duration", "format",
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
        request.app.state.provider_relay.validate_text_operation(
            principal, alias, operation, stream=True
        )
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
    if "n" in payload and (not isinstance(payload["n"], int) or isinstance(payload["n"], bool) or not 1 <= payload["n"] <= 15):
        raise ApiError("n必须是1到15的整数", 422, "image_count_invalid", details={"param": "n"})
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


async def _embedding(
    request: Request,
    principal: PrincipalDependency,
    raw: dict[str, Any],
    *,
    multimodal: bool,
):
    payload = _payload(raw)
    allowed = MULTIMODAL_EMBEDDING_FIELDS if multimodal else EMBEDDING_FIELDS
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ApiError(
            "向量化请求包含不支持的字段", 422, "embedding_parameter_unsupported",
            details={"fields": unknown},
        )
    value = payload.get("input")
    if value is None or value == "" or value == []:
        raise ApiError("input不能为空", 422, "embedding_input_invalid")
    dimensions = payload.get("dimensions")
    if dimensions is not None and dimensions not in {1024, 2048}:
        raise ApiError("dimensions仅支持1024或2048", 422, "embedding_dimensions_invalid")
    data, request_id = await request.app.state.provider_relay.embeddings(
        principal, str(payload["model"]).strip(), payload, multimodal=multimodal
    )
    return JSONResponse(content=data, headers={"X-Request-Id": request_id})


@router.post("/embeddings")
async def embeddings(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
):
    return await _embedding(request, principal, raw, multimodal=False)


@router.post("/embeddings/multimodal")
async def multimodal_embeddings(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
):
    return await _embedding(request, principal, raw, multimodal=True)


@router.post("/audio/speech")
async def audio_speech(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
):
    payload = _payload(raw)
    unknown = sorted(set(payload) - SPEECH_FIELDS)
    if unknown:
        raise ApiError("语音合成请求包含不支持的字段", 422, "audio_parameter_unsupported", details={"fields": unknown})
    content, media_type, request_id = await request.app.state.provider_relay.synthesize_speech(
        principal, str(payload["model"]).strip(), payload
    )
    return Response(content=content, media_type=media_type, headers={"X-Request-Id": request_id})


@router.post("/audio/transcriptions")
async def audio_transcriptions(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    payload = _payload(raw)
    unknown = sorted(set(payload) - TRANSCRIPTION_FIELDS)
    if unknown:
        raise ApiError("录音识别请求包含不支持的字段", 422, "audio_parameter_unsupported", details={"fields": unknown})
    if idempotency_key is not None and not (1 <= len(idempotency_key) <= 128):
        raise ApiError("Idempotency-Key长度无效", 422, "idempotency_key_invalid")
    data = await request.app.state.provider_relay.create_transcription(
        principal, str(payload["model"]).strip(), payload, idempotency_key
    )
    return JSONResponse(content=data, status_code=202)


@router.get("/audio/transcriptions/{task_id}")
async def audio_transcription_status(
    task_id: str,
    request: Request,
    principal: PrincipalDependency,
):
    return JSONResponse(content=await request.app.state.provider_relay.refresh_transcription(principal, task_id))


@router.post("/audio/generations")
async def audio_generations(
    request: Request,
    principal: PrincipalDependency,
    raw: Annotated[dict[str, Any], Body()],
):
    payload = _payload(raw)
    unknown = sorted(set(payload) - AUDIO_GENERATION_FIELDS)
    if unknown:
        raise ApiError("音频生成请求包含不支持的字段", 422, "audio_parameter_unsupported", details={"fields": unknown})
    data, request_id = await request.app.state.provider_relay.generate_audio(
        principal, str(payload["model"]).strip(), payload
    )
    return JSONResponse(content=data, headers={"X-Request-Id": request_id})
