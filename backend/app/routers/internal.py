import sqlite3

from fastapi import APIRouter, Request, status

from ..database import DEFAULT_PROJECT_NAME, Database
from ..errors import ApiError
from ..schemas import ApiKeyBindProject, ApiKeyCreate, ApiKeyDelete, ApiKeyDisable, ApiKeyEnable, ProjectCreate, ProjectDelete
from ..security import AdminDependency, generate_api_key, generate_key_id, hash_api_key


router = APIRouter(prefix="/api/internal", tags=["内部控制台"])


def database(request: Request) -> Database:
    return request.app.state.database


@router.get("/project/list")
def list_projects(request: Request, _: AdminDependency) -> dict:
    return {"projects": database(request).list_projects()}


@router.post("/project/create", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, request: Request, _: AdminDependency) -> dict:
    display_name = (payload.display_name or payload.name).strip()
    try:
        project = database(request).create_project(payload.name, display_name, payload.description.strip())
    except sqlite3.IntegrityError as error:
        raise ApiError("项目标识已存在", 409, "project_exists") from error
    return {"project": project}


@router.delete("/project/delete")
def delete_project(payload: ProjectDelete, request: Request, _: AdminDependency) -> dict:
    if payload.name == DEFAULT_PROJECT_NAME:
        raise ApiError("默认项目 avatar-proxy 不能删除", 400, "default_project_protected")
    moved_key_count = database(request).delete_project(payload.name)
    if moved_key_count is None:
        raise ApiError("项目不存在", 404, "project_not_found")
    return {
        "deleted": True,
        "projectName": payload.name,
        "movedKeyCount": moved_key_count,
        "fallbackProjectName": DEFAULT_PROJECT_NAME,
    }


@router.get("/apikey/list")
def list_api_keys(request: Request, _: AdminDependency) -> dict:
    return {"apiKeys": database(request).list_api_keys()}


@router.post("/apikey/create", status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiKeyCreate, request: Request, _: AdminDependency) -> dict:
    db = database(request)
    db.ensure_project(payload.project_name)
    secret = generate_api_key()
    key_id = generate_key_id()
    prefix = f"{secret[:16]}…"
    db.create_api_key(key_id, payload.name.strip(), prefix, hash_api_key(secret), payload.project_name)
    return {
        "apiKey": {
            "id": key_id,
            "name": payload.name.strip(),
            "keyPrefix": prefix,
            "projectName": payload.project_name,
            "status": "active",
        },
        "secret": secret,
    }


@router.put("/apikey/disable")
def disable_api_key(payload: ApiKeyDisable, request: Request, _: AdminDependency) -> dict:
    if not database(request).disable_api_key(payload.key_id):
        raise ApiError("API Key 不存在或已禁用", 404, "api_key_not_found")
    return {"disabled": True}


@router.put("/apikey/enable")
def enable_api_key(payload: ApiKeyEnable, request: Request, _: AdminDependency) -> dict:
    result = database(request).enable_api_key(payload.key_id)
    if result is None:
        raise ApiError("API Key 不存在", 404, "api_key_not_found")
    if result == "active":
        raise ApiError("API Key 已经处于启用状态", 409, "api_key_already_active")
    return {"enabled": True, "keyId": payload.key_id}


@router.delete("/apikey/delete")
def delete_api_key(payload: ApiKeyDelete, request: Request, _: AdminDependency) -> dict:
    result = database(request).delete_api_key(payload.key_id)
    if result is None:
        raise ApiError("API Key 不存在", 404, "api_key_not_found")
    if result == "active":
        raise ApiError("只有已禁用的 API Key 才能删除", 409, "api_key_must_be_disabled")
    return {"deleted": True, "keyId": payload.key_id}


@router.post("/apikey/bind-project")
def bind_api_key_project(payload: ApiKeyBindProject, request: Request, _: AdminDependency) -> dict:
    db = database(request)
    db.ensure_project(payload.project_name)
    if not db.bind_api_key_project(payload.key_id, payload.project_name):
        raise ApiError("API Key 不存在", 404, "api_key_not_found")
    return {"bound": True, "keyId": payload.key_id, "projectName": payload.project_name}


@router.get("/overview")
def overview(request: Request, _: AdminDependency) -> dict:
    return database(request).overview()
