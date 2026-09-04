from fastapi import APIRouter, Query, Request, status

from ..admin_auth import AdminPrincipal
from ..schemas import (
    AdminProviderChannelCreate,
    AdminProviderDelete,
    AdminProviderSecretRotate,
    AdminProviderStatusUpdate,
    ProjectModelsUpdate,
)
from ..security import AdminDependency, BusinessAdminDependency


router = APIRouter(prefix="/api/internal", tags=["多供应商模型管理"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _audit(
    request: Request,
    principal: AdminPrincipal,
    action: str,
    target_type: str,
    target_id: str,
    *,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    request.app.state.database.write_admin_audit(
        actor=principal.username,
        actor_id=principal.id,
        source_ip=_ip(request),
        user_agent=_ua(request),
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
    )


def _verify_sensitive(
    request: Request,
    principal: AdminPrincipal,
    current_password: str,
    totp_code: str,
    action: str,
) -> None:
    auth = request.app.state.admin_auth
    auth.require_super_admin(principal)
    auth.verify_reauthentication(principal, current_password, _ip(request), _ua(request), action)
    auth.verify_sensitive_totp(principal, totp_code, _ip(request), _ua(request), action)


@router.get("/provider/projects")
def provider_projects(request: Request, principal: AdminDependency) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    return {
        "projects": [
            {
                "name": item["name"],
                "displayName": item.get("displayName") or item["name"],
            }
            for item in request.app.state.database.list_projects()
        ]
    }


@router.get("/provider/channels")
def list_provider_channels(
    request: Request,
    _: AdminDependency,
    project_name: str | None = Query(default=None, alias="projectName", max_length=64),
) -> dict:
    return {"channels": request.app.state.provider_relay.list_channels(project_name)}


@router.post("/provider/channels", status_code=status.HTTP_201_CREATED)
def create_provider_channel(
    payload: AdminProviderChannelCreate,
    request: Request,
    principal: AdminDependency,
) -> dict:
    _verify_sensitive(
        request, principal, payload.current_password, payload.totp_code, "provider.channel.create"
    )
    channel = request.app.state.provider_relay.create_channel(
        project_name=payload.project_name,
        name=payload.name,
        provider=payload.provider,
        config=payload.config,
        secret=payload.secret,
        actor_id=principal.id,
    )
    _audit(
        request,
        principal,
        "provider.channel.create",
        "provider_channel",
        channel["id"],
        after={
            "projectName": channel["projectName"],
            "name": channel["name"],
            "provider": channel["provider"],
            "secretHint": channel["secretHint"],
        },
    )
    return {"channel": channel}


@router.post("/provider/channels/{channel_id}/test")
async def test_provider_channel(
    channel_id: str, request: Request, principal: AdminDependency
) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    result = await request.app.state.provider_relay.test_channel(channel_id)
    _audit(
        request,
        principal,
        "provider.channel.test",
        "provider_channel",
        channel_id,
        after={"status": result["status"], "latencyMs": result["latencyMs"]},
    )
    return {"test": result}


@router.post("/provider/channels/{channel_id}/rotate-key")
def rotate_provider_channel_key(
    channel_id: str,
    payload: AdminProviderSecretRotate,
    request: Request,
    principal: AdminDependency,
) -> dict:
    _verify_sensitive(
        request, principal, payload.current_password, payload.totp_code, "provider.channel.rotate"
    )
    before = request.app.state.provider_relay.get_channel(channel_id)
    channel = request.app.state.provider_relay.rotate_channel_secret(
        channel_id, payload.secret, principal.id
    )
    _audit(
        request,
        principal,
        "provider.channel.rotate",
        "provider_channel",
        channel_id,
        before={"secretHint": before.get("secretHint") if before else None},
        after={"secretHint": channel["secretHint"]},
    )
    return {"channel": channel}


@router.put("/provider/channels/{channel_id}/status")
def update_provider_channel_status(
    channel_id: str,
    payload: AdminProviderStatusUpdate,
    request: Request,
    principal: AdminDependency,
) -> dict:
    _verify_sensitive(
        request, principal, payload.current_password, payload.totp_code, "provider.channel.status"
    )
    before = request.app.state.provider_relay.get_channel(channel_id)
    channel = request.app.state.provider_relay.set_channel_status(channel_id, payload.enabled)
    _audit(
        request,
        principal,
        "provider.channel.status",
        "provider_channel",
        channel_id,
        before={"status": before.get("status") if before else None},
        after={"status": channel["status"]},
    )
    return {"channel": channel}


@router.delete("/provider/channels/{channel_id}")
def delete_provider_channel(
    channel_id: str,
    payload: AdminProviderDelete,
    request: Request,
    principal: AdminDependency,
) -> dict:
    _verify_sensitive(
        request, principal, payload.current_password, payload.totp_code, "provider.channel.delete"
    )
    before = request.app.state.provider_relay.get_channel(channel_id)
    request.app.state.provider_relay.delete_channel(channel_id)
    _audit(
        request,
        principal,
        "provider.channel.delete",
        "provider_channel",
        channel_id,
        before={
            "name": before.get("name") if before else None,
            "provider": before.get("provider") if before else None,
            "secretHint": before.get("secretHint") if before else None,
        },
        after={"deleted": True},
    )
    return {"deleted": True, "channelId": channel_id}


@router.get("/model/catalog")
def model_catalog(request: Request, _: AdminDependency) -> dict:
    return {"models": request.app.state.provider_relay.catalog()}


@router.get("/project/{project_name}/models")
def project_models(
    project_name: str, request: Request, _: BusinessAdminDependency
) -> dict:
    return {
        "projectName": project_name,
        "models": request.app.state.provider_relay.project_models(project_name),
    }


@router.put("/project/{project_name}/models")
def update_project_models(
    project_name: str,
    payload: ProjectModelsUpdate,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    bindings = [item.model_dump(by_alias=True) for item in payload.bindings]
    models = request.app.state.provider_relay.set_project_models(
        project_name, bindings, principal.id
    )
    _audit(
        request,
        principal,
        "project.models.update",
        "project",
        project_name,
        after={"models": [item["model"] for item in models if item["enabled"]]},
    )
    return {"projectName": project_name, "models": models}


@router.get("/inference/usage")
def inference_usage(
    request: Request,
    _: BusinessAdminDependency,
    project_name: str | None = Query(default=None, alias="projectName"),
    key_id: str | None = Query(default=None, alias="keyId"),
    model: str | None = Query(default=None),
    provider: str | None = Query(default=None, pattern="^(openai|volcengine_ark|volcengine_speech|aliyun_bailian|minimax)$"),
    start: str | None = Query(default=None, max_length=40),
    end: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return {
        "usage": request.app.state.provider_relay.usage(
            project_name=project_name,
            key_id=key_id,
            model=model,
            provider=provider,
            start=start,
            end=end,
            limit=limit,
        )
    }


@router.get("/inference/tasks")
def inference_tasks(
    request: Request,
    _: BusinessAdminDependency,
    project_name: str | None = Query(default=None, alias="projectName"),
    key_id: str | None = Query(default=None, alias="keyId"),
    model: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    return {
        "tasks": request.app.state.provider_relay.tasks(
            project_name=project_name, key_id=key_id, model=model, limit=limit
        )
    }
