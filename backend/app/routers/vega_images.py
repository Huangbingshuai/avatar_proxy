"""Asynchronous Vega image endpoints, authenticated with the business API Key."""
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request

from ..security import PrincipalDependency
from ..vega_image_relay import VegaImages
from .openai_compat import _payload

router = APIRouter(prefix="/v1/images/tasks", tags=["Vega异步生图"])


@router.post("")
async def create_image_task(request: Request, principal: PrincipalDependency,
                            raw: Annotated[dict[str, Any], Body()],
                            idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None):
    payload = _payload(raw)
    return await VegaImages(request.app.state.provider_relay).create(principal, payload["model"], payload, idempotency_key)


@router.get("/{task_id}")
async def get_image_task(request: Request, principal: PrincipalDependency, task_id: str):
    return await VegaImages(request.app.state.provider_relay).refresh(principal, task_id)
