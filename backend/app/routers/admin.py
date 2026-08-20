from fastapi import APIRouter, Query, Request, Response, status

from ..admin_auth import AdminPrincipal
from ..backup import RESTORE_CONFIRMATION
from ..errors import ApiError
from ..schemas import (
    AdminLogin,
    AdminDatabaseRestore,
    AdminPasswordChange,
    AdminSecurityAlertAck,
    AdminSensitiveAction,
    AdminTotpConfirm,
    AdminTotpRotationConfirm,
    AdminTotpRotationStart,
    AdminUserCreate,
)
from ..security import AdminDependency, AdminSessionDependency


router = APIRouter(prefix="/api/internal", tags=["控制台管理员"])


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _validate_login_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    normalized = origin.rstrip("/")
    request_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    allowed = set(request.app.state.settings.allowed_origins)
    if normalized != request_origin and normalized not in allowed:
        raise ApiError("控制台登录来源无效", 403, "admin_origin_forbidden")


def _set_auth_cookies(response: Response, request: Request, session_token: str, csrf_token: str) -> None:
    settings = request.app.state.settings
    common = {
        "secure": settings.admin_cookie_secure,
        "samesite": "strict",
        "max_age": settings.admin_session_absolute_seconds,
    }
    response.set_cookie(
        "avatar_admin_session",
        session_token,
        httponly=True,
        path="/api/internal",
        **common,
    )
    response.set_cookie(
        "avatar_admin_csrf",
        csrf_token,
        httponly=False,
        path="/",
        **common,
    )


def _clear_auth_cookies(response: Response, request: Request) -> None:
    secure = request.app.state.settings.admin_cookie_secure
    response.delete_cookie(
        "avatar_admin_session", path="/api/internal", secure=secure, httponly=True, samesite="strict"
    )
    response.delete_cookie(
        "avatar_admin_csrf", path="/", secure=secure, httponly=False, samesite="strict"
    )


@router.post("/auth/login")
def login(payload: AdminLogin, request: Request, response: Response) -> dict:
    _validate_login_origin(request)
    user, session, session_token, csrf_token = request.app.state.admin_auth.login(
        payload.username,
        payload.password,
        _request_ip(request),
        _user_agent(request),
        payload.totp_code,
        payload.recovery_code,
    )
    _set_auth_cookies(response, request, session_token, csrf_token)
    return {"user": user, "session": session, "csrfToken": csrf_token}


@router.get("/auth/me")
def me(request: Request, principal: AdminSessionDependency) -> dict:
    sessions = request.app.state.admin_auth.list_sessions(principal)
    current = next((item for item in sessions if item["current"]), None)
    return {
        "user": request.app.state.admin_auth.principal_payload(principal),
        "session": current,
        "csrfToken": principal.csrf_token,
    }


@router.post("/auth/logout")
def logout(request: Request, response: Response, principal: AdminSessionDependency) -> dict:
    request.app.state.admin_auth.logout(principal, _request_ip(request), _user_agent(request))
    _clear_auth_cookies(response, request)
    return {"loggedOut": True}


@router.post("/auth/change-password")
def change_password(
    payload: AdminPasswordChange,
    request: Request,
    response: Response,
    principal: AdminSessionDependency,
) -> dict:
    request.app.state.admin_auth.change_password(
        principal,
        payload.current_password,
        payload.new_password,
        _request_ip(request),
        _user_agent(request),
    )
    _clear_auth_cookies(response, request)
    return {"changed": True, "requiresLogin": True}


@router.post("/auth/totp/setup")
def setup_totp(request: Request, principal: AdminSessionDependency) -> dict:
    return request.app.state.admin_auth.begin_totp_setup(
        principal, _request_ip(request), _user_agent(request)
    )


@router.post("/auth/totp/confirm")
def confirm_totp(payload: AdminTotpConfirm, request: Request, principal: AdminSessionDependency) -> dict:
    recovery_codes = request.app.state.admin_auth.confirm_totp_setup(
        principal, payload.code, _request_ip(request), _user_agent(request)
    )
    return {"enabled": True, "mfaVerified": True, "recoveryCodes": recovery_codes}


@router.post("/auth/totp/rotate/setup")
def setup_totp_rotation(
    payload: AdminTotpRotationStart, request: Request, principal: AdminDependency
) -> dict:
    return request.app.state.admin_auth.begin_totp_rotation(
        principal,
        payload.current_password,
        payload.current_totp_code,
        _request_ip(request),
        _user_agent(request),
    )


@router.post("/auth/totp/rotate/confirm")
def confirm_totp_rotation(
    payload: AdminTotpRotationConfirm, request: Request, principal: AdminDependency
) -> dict:
    result = request.app.state.admin_auth.confirm_totp_rotation(
        principal, payload.code, _request_ip(request), _user_agent(request)
    )
    return {"enabled": True, "mfaVerified": True, **result}


@router.get("/auth/sessions")
def sessions(request: Request, principal: AdminDependency) -> dict:
    return {"sessions": request.app.state.admin_auth.list_sessions(principal)}


@router.delete("/auth/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    response: Response,
    principal: AdminDependency,
) -> dict:
    current = request.app.state.admin_auth.revoke_session(
        principal,
        session_id,
        _request_ip(request),
        _user_agent(request),
    )
    if current:
        _clear_auth_cookies(response, request)
    return {"revoked": True, "sessionId": session_id}


@router.get("/admin/users")
def list_admin_users(request: Request, principal: AdminDependency) -> dict:
    return {"users": request.app.state.admin_auth.list_users(principal)}


@router.get("/admin/audits")
def list_admin_audits(
    request: Request,
    principal: AdminDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"audits": request.app.state.admin_auth.list_audits(principal, limit)}


@router.get("/admin/security-alerts")
def list_security_alerts(
    request: Request,
    principal: AdminDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"alerts": request.app.state.admin_auth.list_security_alerts(principal, limit)}


@router.post("/admin/security-alerts/ack")
def acknowledge_security_alert(
    payload: AdminSecurityAlertAck, request: Request, principal: AdminDependency
) -> dict:
    return {"alert": request.app.state.admin_auth.acknowledge_security_alert(principal, payload.alert_id)}


@router.get("/admin/backups/status")
def backup_status(request: Request, principal: AdminDependency) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    return request.app.state.backup.status()


@router.get("/admin/backups")
def list_backups(request: Request, principal: AdminDependency) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    return {
        "backups": request.app.state.backup.list_backups(),
        "lastRestore": request.app.state.backup.status().get("lastRestore"),
    }


@router.post("/admin/backups/{backup_id}/validate")
def validate_backup(backup_id: str, request: Request, principal: AdminDependency) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    return {"backup": request.app.state.backup.validate_backup(backup_id)}


@router.post("/admin/backups/run")
async def run_backup(payload: AdminSensitiveAction, request: Request, principal: AdminDependency) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    request.app.state.admin_auth.verify_reauthentication(
        principal,
        payload.current_password,
        _request_ip(request),
        _user_agent(request),
        "admin.backup.run",
    )
    return await request.app.state.backup.run_manual_backup()


@router.post("/admin/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    payload: AdminDatabaseRestore,
    request: Request,
    response: Response,
    principal: AdminDependency,
) -> dict:
    request.app.state.admin_auth.require_super_admin(principal)
    if payload.confirmation != RESTORE_CONFIRMATION:
        raise ApiError("请输入“恢复数据库”确认高风险操作", 422, "admin_restore_confirmation_invalid")
    request.app.state.admin_auth.verify_reauthentication(
        principal,
        payload.current_password,
        _request_ip(request),
        _user_agent(request),
        "admin.database.restore",
    )
    request.app.state.admin_auth.verify_sensitive_totp(
        principal,
        payload.totp_code,
        _request_ip(request),
        _user_agent(request),
        "admin.database.restore",
    )
    result = await request.app.state.backup.restore_backup(
        backup_id,
        actor=principal.username,
        source_ip=_request_ip(request),
    )
    _clear_auth_cookies(response, request)
    return result


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def create_admin_user(payload: AdminUserCreate, request: Request, principal: AdminDependency) -> dict:
    user, initial_password = request.app.state.admin_auth.create_admin(
        principal,
        payload.username,
        payload.display_name,
        payload.current_password,
        _request_ip(request),
        _user_agent(request),
    )
    return {"user": user, "initialPassword": initial_password}


@router.put("/admin/users/{user_id}/disable")
def disable_admin_user(
    user_id: str, payload: AdminSensitiveAction, request: Request, principal: AdminDependency
) -> dict:
    user = request.app.state.admin_auth.set_user_enabled(
        principal,
        user_id,
        enabled=False,
        current_password=payload.current_password,
        source_ip=_request_ip(request),
        user_agent=_user_agent(request),
    )
    return {"user": user}


@router.put("/admin/users/{user_id}/enable")
def enable_admin_user(
    user_id: str, payload: AdminSensitiveAction, request: Request, principal: AdminDependency
) -> dict:
    user = request.app.state.admin_auth.set_user_enabled(
        principal,
        user_id,
        enabled=True,
        current_password=payload.current_password,
        source_ip=_request_ip(request),
        user_agent=_user_agent(request),
    )
    return {"user": user}


@router.delete("/admin/users/{user_id}")
def delete_admin_user(
    user_id: str, payload: AdminSensitiveAction, request: Request, principal: AdminDependency
) -> dict:
    user = request.app.state.admin_auth.delete_admin(
        principal,
        user_id,
        payload.current_password,
        _request_ip(request),
        _user_agent(request),
    )
    return {"deleted": True, "userId": user_id, "username": user["username"]}


@router.post("/admin/users/{user_id}/reset-password")
def reset_admin_password(
    user_id: str, payload: AdminSensitiveAction, request: Request, principal: AdminDependency
) -> dict:
    user, initial_password = request.app.state.admin_auth.reset_password(
        principal,
        user_id,
        payload.current_password,
        _request_ip(request),
        _user_agent(request),
    )
    return {"user": user, "initialPassword": initial_password}
