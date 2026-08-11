from fastapi import APIRouter

from ..security import PrincipalDependency


router = APIRouter(prefix="/api/auth", tags=["API Key 登录"])


@router.get("/me")
def current_session(principal: PrincipalDependency) -> dict[str, str | bool]:
    return {
        "authenticated": True,
        "apiKeyId": principal.id,
    }
