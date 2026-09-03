import sqlite3

from fastapi import APIRouter, Query, Request, status

from ..admin_auth import AdminPrincipal
from ..database import Database
from ..errors import ApiError
from ..schemas import (
    ApiKeyBindProject,
    ApiKeyCreate,
    ApiKeyDelete,
    ApiKeyDisable,
    ApiKeyEnable,
    ApiKeyQuotaUpdate,
    ProjectCreate,
    ProjectDelete,
    ProjectQuotaUpdate,
    QuotaEventAck,
)
from ..security import BusinessAdminDependency as AdminDependency, generate_api_key, generate_key_id, hash_api_key


router = APIRouter(prefix="/api/internal", tags=["内部控制台"])


def database(request: Request) -> Database:
    return request.app.state.database


def audit_action(
    request: Request,
    admin: AdminPrincipal,
    action: str,
    target_type: str,
    target_id: str,
    *,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    database(request).write_admin_audit(
        actor=admin.username,
        actor_id=admin.id,
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
    )


@router.get("/project/list")
def list_projects(request: Request, _: AdminDependency) -> dict:
    return {"projects": database(request).list_projects()}


@router.post("/project/create", status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, request: Request, admin: AdminDependency) -> dict:
    db = database(request)
    if db.resolve_project_name(payload.name) is not None:
        raise ApiError("项目标识已存在", 409, "project_exists")

    volcengine_project = await request.app.state.volcengine.get_project(payload.name)
    if volcengine_project is None:
        raise ApiError(
            "火山引擎中不存在该 ProjectName，请先在火山控制台创建项目",
            422,
            "volcengine_project_not_found",
        )
    if volcengine_project["ProjectName"] != payload.name:
        raise ApiError(
            "ProjectName 必须与火山引擎中的名称完全一致（区分大小写）",
            422,
            "volcengine_project_name_mismatch",
            details={"volcengineProjectName": volcengine_project["ProjectName"]},
        )

    display_name = (payload.display_name or payload.name).strip()
    try:
        project = db.create_project(payload.name, display_name, payload.description.strip())
    except sqlite3.IntegrityError as error:
        raise ApiError("项目标识已存在", 409, "project_exists") from error
    audit_action(request, admin, "project.create", "project", payload.name, after=project)
    return {"project": project}


@router.delete("/project/delete")
def delete_project(payload: ProjectDelete, request: Request, admin: AdminDependency) -> dict:
    result = database(request).delete_project(payload.name)
    if result is None:
        raise ApiError("项目不存在", 404, "project_not_found")
    if result["keyCount"]:
        raise ApiError(
            "项目仍有关联 API Key，请先迁移或删除全部 Key",
            409,
            "project_has_api_keys",
            details={"keyCount": result["keyCount"], "assetCount": result["assetCount"]},
        )
    if result["assetCount"]:
        raise ApiError(
            "项目仍有未删除素材，请先完成素材删除和 TOS 清理",
            409,
            "project_has_assets",
            details={"keyCount": 0, "assetCount": result["assetCount"]},
        )
    if result.get("channelCount"):
        raise ApiError(
            "项目仍有供应商渠道，请先删除全部渠道",
            409,
            "project_has_provider_channels",
            details={"channelCount": result["channelCount"]},
        )
    if result.get("billingCount"):
        raise ApiError(
            "项目已有计费账单历史，为保证财务记录不能删除",
            409,
            "project_has_billing_history",
            details={"billingCount": result["billingCount"]},
        )
    audit_action(
        request, admin, "project.delete", "project", result["projectName"],
        before={"projectName": result["projectName"]}, after={"deleted": True},
    )
    return {"deleted": True, "projectName": result["projectName"]}


@router.get("/apikey/list")
def list_api_keys(request: Request, _: AdminDependency) -> dict:
    return {"apiKeys": database(request).list_api_keys()}


@router.post("/apikey/create", status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiKeyCreate, request: Request, admin: AdminDependency) -> dict:
    db = database(request)
    project_name = db.resolve_project_name(payload.project_name)
    if project_name is None:
        raise ApiError("项目不存在，请先创建并绑定真实的火山 ProjectName", 404, "project_not_found")
    secret = generate_api_key()
    key_id = generate_key_id()
    prefix = f"{secret[:16]}…"
    db.create_api_key(key_id, payload.name.strip(), prefix, hash_api_key(secret), project_name)
    result = {
        "apiKey": {
            "id": key_id,
            "name": payload.name.strip(),
            "keyPrefix": prefix,
            "projectName": project_name,
            "status": "active",
        },
        "secret": secret,
    }
    audit_action(
        request, admin, "apikey.create", "api_key", key_id,
        after={"name": payload.name.strip(), "projectName": project_name, "status": "active"},
    )
    return result


@router.put("/apikey/disable")
def disable_api_key(payload: ApiKeyDisable, request: Request, admin: AdminDependency) -> dict:
    if not database(request).disable_api_key(payload.key_id):
        raise ApiError("API Key 不存在或已禁用", 404, "api_key_not_found")
    audit_action(
        request, admin, "apikey.disable", "api_key", payload.key_id,
        before={"status": "active"}, after={"status": "disabled"},
    )
    return {"disabled": True}


@router.put("/apikey/enable")
def enable_api_key(payload: ApiKeyEnable, request: Request, admin: AdminDependency) -> dict:
    result = database(request).enable_api_key(payload.key_id)
    if result is None:
        raise ApiError("API Key 不存在", 404, "api_key_not_found")
    if result == "active":
        raise ApiError("API Key 已经处于启用状态", 409, "api_key_already_active")
    audit_action(
        request, admin, "apikey.enable", "api_key", payload.key_id,
        before={"status": "disabled"}, after={"status": "active"},
    )
    return {"enabled": True, "keyId": payload.key_id}


@router.delete("/apikey/delete")
def delete_api_key(payload: ApiKeyDelete, request: Request, admin: AdminDependency) -> dict:
    result = database(request).delete_api_key(payload.key_id)
    if result is None:
        raise ApiError("API Key 不存在", 404, "api_key_not_found")
    if result == "active":
        raise ApiError("只有已禁用的 API Key 才能删除", 409, "api_key_must_be_disabled")
    audit_action(
        request, admin, "apikey.delete", "api_key", payload.key_id,
        before={"status": "disabled"}, after={"deleted": True},
    )
    return {"deleted": True, "keyId": payload.key_id}


@router.post("/apikey/bind-project")
def bind_api_key_project(payload: ApiKeyBindProject, request: Request, admin: AdminDependency) -> dict:
    db = database(request)
    project_name = db.resolve_project_name(payload.project_name)
    if project_name is None:
        raise ApiError("项目不存在，请先创建并绑定真实的火山 ProjectName", 404, "project_not_found")
    if not db.bind_api_key_project(payload.key_id, project_name):
        raise ApiError("API Key 不存在", 404, "api_key_not_found")
    audit_action(
        request, admin, "apikey.bind_project", "api_key", payload.key_id,
        after={"projectName": project_name},
    )
    return {"bound": True, "keyId": payload.key_id, "projectName": project_name}


@router.get("/overview")
def overview(request: Request, _: AdminDependency) -> dict:
    return database(request).overview()


@router.get("/project/quota")
def get_project_quota(
    request: Request,
    _: AdminDependency,
    project_name: str = Query(alias="projectName", min_length=2),
) -> dict:
    return {"quota": request.app.state.quota.project_quota(project_name)}


@router.put("/project/quota")
def update_project_quota(payload: ProjectQuotaUpdate, request: Request, admin: AdminDependency) -> dict:
    source_ip = request.client.host if request.client else None
    return {"quota": request.app.state.quota.set_project_quota(
        payload.model_dump(), source_ip, actor_id=admin.id, actor=admin.username,
        user_agent=request.headers.get("user-agent"),
    )}


@router.get("/apikey/quota")
def get_api_key_quota(
    request: Request,
    _: AdminDependency,
    key_id: str = Query(alias="keyId", min_length=1),
) -> dict:
    return {"quota": request.app.state.quota.key_quota(key_id)}


@router.put("/apikey/quota")
def update_api_key_quota(payload: ApiKeyQuotaUpdate, request: Request, admin: AdminDependency) -> dict:
    source_ip = request.client.host if request.client else None
    return {"quota": request.app.state.quota.set_key_quota(
        payload.model_dump(), source_ip, actor_id=admin.id, actor=admin.username,
        user_agent=request.headers.get("user-agent"),
    )}


@router.get("/quota/usage")
def get_quota_usage(
    request: Request,
    _: AdminDependency,
    project_name: str = Query(alias="projectName", min_length=2),
) -> dict:
    return request.app.state.quota.usage(project_name)


@router.get("/quota/events")
def list_quota_events(
    request: Request,
    _: AdminDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"events": request.app.state.quota.events(limit)}


@router.get("/quota/audits")
def list_quota_audits(
    request: Request,
    _: AdminDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"audits": request.app.state.quota.audits(limit)}


@router.post("/quota/event/ack")
def acknowledge_quota_event(payload: QuotaEventAck, request: Request, admin: AdminDependency) -> dict:
    if not request.app.state.quota.acknowledge(payload.event_id):
        raise ApiError("额度事件不存在或已确认", 404, "quota_event_not_found")
    audit_action(
        request, admin, "quota.event.acknowledge", "quota_event", str(payload.event_id),
        after={"acknowledged": True},
    )
    return {"acknowledged": True, "eventId": payload.event_id}
