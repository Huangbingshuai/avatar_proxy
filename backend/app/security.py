import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


def require_admin(
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    configured = request.app.state.settings.console_admin_token
    if not configured:
        raise ApiError("服务端尚未配置 CONSOLE_ADMIN_TOKEN", 503, "admin_not_configured")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, configured):
        raise ApiError("管理令牌无效", 401, "invalid_admin_token")


def require_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ApiPrincipal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise ApiError("请使用 Authorization: Bearer <API_KEY>", 401, "missing_api_key")
    database: Database = request.app.state.database
    row = database.find_api_key(hash_api_key(credentials.credentials))
    if not row:
        raise ApiError("API Key 无效或已撤销", 401, "invalid_api_key")
    database.touch_api_key(row["id"])
    return ApiPrincipal(id=row["id"], project_name=row["projectName"])


AdminDependency = Annotated[None, Depends(require_admin)]
PrincipalDependency = Annotated[ApiPrincipal, Depends(require_api_key)]
