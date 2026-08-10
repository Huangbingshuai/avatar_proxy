import sqlite3

from fastapi import APIRouter, Request, status

from ..database import Database
from ..errors import ApiError
from ..schemas import ApiKeyCreate, ProjectCreate
from ..security import AdminDependency, generate_api_key, generate_key_id, hash_api_key


router = APIRouter(prefix="/api/admin", tags=["管理控制台"])


def database(request: Request) -> Database:
    return request.app.state.database


@router.get("/projects")
def list_projects(request: Request, _: AdminDependency) -> dict:
    return {"projects": database(request).list_projects()}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, request: Request, _: AdminDependency) -> dict:
    display_name = (payload.displayName or payload.name).strip()
    try:
        project = database(request).create_project(payload.name, display_name, payload.description.strip())
    except sqlite3.IntegrityError as error:
        raise ApiError("项目标识已存在", 409, "project_exists") from error
    return {"project": project}


@router.get("/api-keys")
def list_api_keys(request: Request, _: AdminDependency) -> dict:
    return {"apiKeys": database(request).list_api_keys()}


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiKeyCreate, request: Request, _: AdminDependency) -> dict:
    db = database(request)
    if not db.project_exists(payload.projectName):
        raise ApiError("项目不存在", 404, "project_not_found")
    secret = generate_api_key()
    key_id = generate_key_id()
    prefix = f"{secret[:16]}…"
    db.create_api_key(key_id, payload.name.strip(), prefix, hash_api_key(secret), payload.projectName)
    return {
        "apiKey": {
            "id": key_id,
            "name": payload.name.strip(),
            "keyPrefix": prefix,
            "projectName": payload.projectName,
            "status": "active",
        },
        "secret": secret,
    }


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, request: Request, _: AdminDependency) -> dict:
    if not database(request).revoke_api_key(key_id):
        raise ApiError("API Key 不存在或已撤销", 404, "api_key_not_found")
    return {"revoked": True}


@router.get("/overview")
def overview(request: Request, _: AdminDependency) -> dict:
    return database(request).overview()
