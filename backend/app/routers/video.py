import json
import re
import time
from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from ..errors import ApiError
from ..schemas import VideoGenerate, VideoHistoryImport
from ..security import PrincipalDependency
from ..volcengine import ark_usage_token_mask


router = APIRouter(prefix="/api/video", tags=["Seedance 视频生成"])
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
VIDEO_MODEL_PATTERN = re.compile(r"seedance", re.IGNORECASE)
USAGE_DIMENSIONS = {
    "AccountID", "Day", "Hour", "ModelEndpoint", "ModelName", "ModelUnitID",
    "AuthToken", "ProjectName", "BillingStatus",
}
USAGE_ALIASES = {
    "InputTokens": "inputTokens",
    "OutputTokens": "outputTokens",
    "TotalTokens": "totalTokens",
    "ReqCnt": "requestCount",
}


def validate_task_id(task_id: str) -> str:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ApiError("视频任务 ID 格式无效", 400, "invalid_task_id")
    return task_id


def response_data(response: Response) -> dict[str, Any]:
    body = getattr(response, "body", b"")
    if not body:
        return {}
    try:
        value = json.loads(body)
    except (TypeError, ValueError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def first_url(data: dict[str, Any], key: str) -> str | None:
    for source in (data.get("content"), data.get("output"), data):
        if isinstance(source, dict) and isinstance(source.get(key), str) and source[key]:
            return source[key]
    return None


def ark_key_from_request(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, value = authorization.partition(" ")
    key = value.strip()
    if separator != " " or scheme.lower() != "bearer" or not key:
        raise ApiError("请使用 Authorization: Bearer <ARK_API_KEY>", 401, "missing_ark_api_key")
    if not 16 <= len(key) <= 512 or any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise ApiError("方舟 API Key 格式无效", 401, "invalid_ark_api_key")
    if len(re.sub(r"[^A-Za-z0-9]", "", key)) < 12:
        raise ApiError("方舟 API Key 格式无效", 401, "invalid_ark_api_key")
    return key


def _usage_number(value: Any) -> int | float:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return 0
    return int(number) if number.is_integer() else number


def _usage_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_fields = result.get("Fields") or result.get("fields") or []
    field_names = [
        str(field.get("Name") or field.get("name") or field.get("Metric") or "")
        for field in raw_fields
        if isinstance(field, dict)
    ]
    raw_records = (
        result.get("Data")
        or result.get("data")
        or result.get("Records")
        or result.get("records")
        or result.get("Values")
        or []
    )
    if not raw_records and raw_fields:
        column_count = max(
            (len(field.get("Values", [])) for field in raw_fields if isinstance(field, dict)),
            default=0,
        )
        return [
            {
                str(field.get("Name") or field.get("name") or field.get("Metric") or ""): field.get("Values", [])[index]
                for field in raw_fields
                if isinstance(field, dict)
                and str(field.get("Name") or field.get("name") or field.get("Metric") or "")
                and isinstance(field.get("Values"), list)
                and index < len(field["Values"])
            }
            for index in range(column_count)
        ]
    records: list[dict[str, Any]] = []
    for raw_record in raw_records if isinstance(raw_records, list) else []:
        if isinstance(raw_record, str):
            try:
                raw_record = json.loads(raw_record)
            except ValueError:
                continue
        if isinstance(raw_record, dict):
            values = raw_record.get("Values")
            if isinstance(values, list) and field_names:
                record = dict(zip(field_names, values, strict=False))
            else:
                record = dict(raw_record)
        elif isinstance(raw_record, list) and field_names:
            record = dict(zip(field_names, raw_record, strict=False))
        else:
            continue
        records.append(record)
    return records


def normalize_ark_video_usage(content: dict[str, Any], ark_api_key: str, start: date, end: date, interval: str) -> dict[str, Any]:
    result = content["Result"]
    records = _usage_records(result)
    video_records = []
    key_suffix = ark_api_key[-12:]
    masked_token = ark_usage_token_mask(ark_api_key)
    totals: dict[str, int | float] = {value: 0 for value in USAGE_ALIASES.values()}
    extra_totals: dict[str, int | float] = {}
    for record in records:
        returned_token = str(record.get("AuthToken") or "")
        if returned_token and returned_token != masked_token:
            continue
        model_name = str(record.get("ModelName") or record.get("FoundationModelName") or "")
        if not VIDEO_MODEL_PATTERN.search(model_name):
            continue
        normalized = {
            "date": record.get("Day") or record.get("Hour"),
            "modelName": model_name,
            "modelUnitId": record.get("ModelUnitID"),
            "endpointId": record.get("ModelEndpoint"),
        }
        metrics: dict[str, int | float] = {}
        for name, value in record.items():
            if name in USAGE_DIMENSIONS or name == "FoundationModelName":
                continue
            metric_value = _usage_number(value)
            alias = USAGE_ALIASES.get(name)
            if alias:
                normalized[alias] = metric_value
                totals[alias] += metric_value
            else:
                metrics[name] = metric_value
                extra_totals[name] = extra_totals.get(name, 0) + metric_value
        for alias in USAGE_ALIASES.values():
            normalized.setdefault(alias, 0)
        if metrics:
            normalized["metrics"] = metrics
        video_records.append({key: value for key, value in normalized.items() if value is not None})

    metadata = content.get("ResponseMetadata")
    request_id = metadata.get("RequestId") if isinstance(metadata, dict) else None
    return {
        "source": "volcengine_ark",
        "scope": "ark_api_key",
        "keySuffix": key_suffix,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "interval": interval,
        "dataDelayMinutes": {"min": 5, "max": 30},
        "billingAmountIncluded": False,
        "summary": {**totals, "metrics": extra_totals},
        "records": video_records,
        "upstreamRequestId": request_id,
    }


def task_record(payload: VideoGenerate, data: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.metadata
    prompt = metadata.prompt.strip() if metadata else ""
    if not prompt:
        prompt = next(
            (
                str(item.get("text") or "").strip()
                for item in payload.content
                if item.get("type") == "text" and str(item.get("text") or "").strip()
            ),
            "视频生成任务",
        )
    assets = metadata.assets if metadata else []
    raw_created_at = data.get("created_at")
    try:
        created_at = round(float(raw_created_at) * 1000) if raw_created_at is not None else round(time.time() * 1000)
    except (TypeError, ValueError):
        created_at = round(time.time() * 1000)
    return {
        "id": str(data.get("id") or ""),
        "createdAt": created_at,
        "prompt": prompt,
        "promptDocument": metadata.prompt_document if metadata else None,
        "assetName": next((str(asset.get("name")) for asset in assets if asset.get("name")), None),
        "assetNames": [str(asset["name"]) for asset in assets if asset.get("name")],
        "assets": assets,
        "model": str(data.get("model") or payload.model),
        "ratio": payload.ratio,
        "duration": payload.duration,
        "durationMode": metadata.duration_mode if metadata else None,
        "resolution": payload.resolution,
        "generationCount": metadata.generation_count if metadata else 1,
        "generateAudio": payload.generate_audio,
        "status": str(data.get("status") or "queued"),
        "videoUrl": first_url(data, "video_url"),
        "lastFrameUrl": first_url(data, "last_frame_url"),
    }


def sync_task_response(request: Request, principal: PrincipalDependency, data: dict[str, Any]) -> None:
    task_id = str(data.get("id") or "")
    if not task_id:
        return
    request.app.state.database.save_video_task(
        principal.id,
        principal.project_name,
        task_id,
        {
            "id": task_id,
            "status": str(data.get("status") or "") or None,
            "model": str(data.get("model") or "") or None,
            "videoUrl": first_url(data, "video_url"),
            "lastFrameUrl": first_url(data, "last_frame_url"),
        },
    )


@router.post("/generate")
async def generate_video(payload: VideoGenerate, request: Request, principal: PrincipalDependency) -> Response:
    body = payload.model_dump(by_alias=False, exclude_none=True, exclude={"metadata"})
    response = await request.app.state.seedance.request(
        "POST", "contents/generations/tasks", principal, body
    )
    data = response_data(response)
    if response.status_code < 400 and data.get("id"):
        record = task_record(payload, data)
        request.app.state.database.save_video_task(
            principal.id, principal.project_name, str(data["id"]), record
        )
    return response


@router.get("/history")
def list_video_history(
    request: Request,
    principal: PrincipalDependency,
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, list[dict[str, Any]]]:
    return {"tasks": request.app.state.database.list_video_tasks(principal.id, limit)}


@router.post("/history/import")
def import_video_history(
    payload: VideoHistoryImport,
    request: Request,
    principal: PrincipalDependency,
) -> dict[str, int]:
    imported = 0
    for task in payload.tasks:
        record = task.model_dump(by_alias=True, exclude_none=True)
        request.app.state.database.save_video_task(
            principal.id, principal.project_name, task.id, record
        )
        imported += 1
    return {"imported": imported}


@router.delete("/history")
def clear_video_history(request: Request, principal: PrincipalDependency) -> dict[str, int]:
    return {"removed": request.app.state.database.hide_all_video_tasks(principal.id)}


@router.delete("/history/{taskId}")
def remove_video_history_task(
    taskId: str,
    request: Request,
    principal: PrincipalDependency,
) -> dict[str, bool]:
    task_id = validate_task_id(taskId)
    return {"removed": request.app.state.database.hide_video_task(principal.id, task_id)}


@router.get("/usage")
def get_video_usage(
    request: Request,
    principal: PrincipalDependency,
    days: int = Query(default=14, ge=7, le=30),
) -> dict:
    return request.app.state.database.video_usage(principal.id, days)


@router.get("/ark-usage")
async def get_ark_video_usage(
    request: Request,
    start: date = Query(description="开始日期，格式 YYYY-MM-DD"),
    end: date = Query(description="结束日期，格式 YYYY-MM-DD"),
    interval: str = Query(default="Day", pattern="^(Day|Hour)$"),
) -> dict[str, Any]:
    ark_api_key = ark_key_from_request(request)
    if end < start:
        raise ApiError("结束日期不能早于开始日期", 400, "invalid_usage_date_range")
    if (end - start).days > 31:
        raise ApiError("单次最多查询 31 天", 400, "usage_date_range_too_large")
    content = await request.app.state.volcengine.query_inference_usage(
        ark_api_key,
        start.isoformat(),
        end.isoformat(),
        interval,
    )
    return normalize_ark_video_usage(content, ark_api_key, start, end, interval)


@router.get("/task/{taskId}")
async def get_video_task(taskId: str, request: Request, principal: PrincipalDependency) -> Response:
    task_id = validate_task_id(taskId)
    response = await request.app.state.seedance.request(
        "GET", f"contents/generations/tasks/{task_id}", principal
    )
    if response.status_code < 400:
        sync_task_response(request, principal, response_data(response))
    return response


@router.post("/task/{taskId}/cancel")
async def cancel_video_task(taskId: str, request: Request, principal: PrincipalDependency) -> Response:
    task_id = validate_task_id(taskId)
    response = await request.app.state.seedance.request(
        "DELETE", f"contents/generations/tasks/{task_id}", principal
    )
    if response.status_code < 400:
        request.app.state.database.save_video_task(
            principal.id,
            principal.project_name,
            task_id,
            {"id": task_id, "status": "cancelled"},
        )
    return response
