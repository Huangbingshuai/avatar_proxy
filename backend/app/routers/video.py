import json
import re
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from ..errors import ApiError
from ..schemas import VideoGenerate, VideoHistoryImport
from ..security import PrincipalDependency


router = APIRouter(prefix="/api/video", tags=["Seedance 视频生成"])
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


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
