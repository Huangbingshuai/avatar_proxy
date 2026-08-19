import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated, AsyncIterator

from fastapi import Cookie, Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .admin_auth import AdminPrincipal
from .database import Database
from .errors import ApiError


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ApiPrincipal:
    id: str
    project_name: str


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"vap_live_{secrets.token_urlsafe(24)}"


def generate_key_id() -> str:
    return str(uuid.uuid4())


def require_admin_session(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias="avatar_admin_session")] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias="avatar_admin_csrf")] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AdminPrincipal:
    return request.app.state.admin_auth.authenticate_session(
        session_token,
        csrf_cookie,
        csrf_header,
        require_csrf=request.method.upper() not in {"GET", "HEAD", "OPTIONS"},
    )


def require_admin(
    principal: Annotated[AdminPrincipal, Depends(require_admin_session)],
) -> AdminPrincipal:
    if principal.must_change_password:
        raise ApiError("首次登录必须先修改密码", 403, "password_change_required")
    return principal


async def require_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AsyncIterator[ApiPrincipal]:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise ApiError("请使用 Authorization: Bearer <API_KEY>", 401, "missing_api_key")
    database: Database = request.app.state.database
    row = database.find_api_key(hash_api_key(credentials.credentials))
    if not row:
        raise ApiError("API Key 无效或已禁用", 401, "invalid_api_key")
    project_name = (row.get("projectName") or "").strip()
    if not project_name or not database.project_exists(project_name):
        raise ApiError("API Key 未绑定有效项目", 403, "invalid_project_binding")
    principal = ApiPrincipal(id=row["id"], project_name=project_name)
    async with request.app.state.quota.request_slot(
        principal.project_name,
        principal.id,
        write=request.app.state.quota.is_write_request(request),
    ):
        database.touch_api_key(row["id"])
        yield principal


AdminSessionDependency = Annotated[AdminPrincipal, Depends(require_admin_session)]
AdminDependency = Annotated[AdminPrincipal, Depends(require_admin)]
PrincipalDependency = Annotated[ApiPrincipal, Depends(require_api_key)]
