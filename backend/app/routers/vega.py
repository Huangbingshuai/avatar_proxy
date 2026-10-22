from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request

from ..errors import ApiError
from ..security import PrincipalDependency
from ..vega_resources import VegaResources

router = APIRouter(prefix="/v1/vega", tags=["Vega素材与活体认证"])


@router.post("/{action}")
async def resources(action: str, request: Request, principal: PrincipalDependency,
                    raw: Annotated[dict[str, Any], Body()],
                    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None):
    body = dict(raw)
    alias = body.pop("model", None)
    if not isinstance(alias, str) or not alias or len(alias) > 128:
        raise ApiError("model不能为空", 422, "model_required")
    if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
        raise ApiError("Idempotency-Key长度无效", 422, "idempotency_key_invalid")
    return await VegaResources(request.app.state.provider_relay).call(principal, alias, action, body, idempotency_key)
