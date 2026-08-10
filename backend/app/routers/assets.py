from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from ..schemas import AssetCreate, AssetGroupCreate, AssetGroupUpdate, AssetUpdate
from ..security import PrincipalDependency


router = APIRouter(prefix="/api/v1", tags=["虚拟人像素材资产"])


async def upstream(request: Request, action: str, body: dict[str, Any], principal: PrincipalDependency) -> Response:
    body.pop("ProjectName", None)
    body.pop("projectName", None)
    return await request.app.state.volcengine.call(action, body, principal)


@router.post("/asset-groups")
async def create_asset_group(payload: AssetGroupCreate, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(
        request,
        "CreateAssetGroup",
        {"Name": payload.name, "Description": payload.description, "GroupType": "AIGC"},
        principal,
    )


@router.get("/asset-groups")
async def list_asset_groups(
    request: Request,
    principal: PrincipalDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str | None = None,
    group_id: list[str] = Query(default=[]),
) -> Response:
    return await upstream(request, "ListAssetGroups", {
        "PageNumber": page,
        "PageSize": page_size,
        "Filter": {"Name": name, "GroupType": "AIGC", "GroupIds": group_id},
    }, principal)


@router.get("/asset-groups/{group_id}")
async def get_asset_group(group_id: str, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(request, "GetAssetGroup", {"Id": group_id}, principal)


@router.patch("/asset-groups/{group_id}")
async def update_asset_group(
    group_id: str, payload: AssetGroupUpdate, request: Request, principal: PrincipalDependency
) -> Response:
    body = {"Id": group_id, "Name": payload.name, "Description": payload.description}
    return await upstream(request, "UpdateAssetGroup", {key: value for key, value in body.items() if value is not None}, principal)


@router.delete("/asset-groups/{group_id}")
async def delete_asset_group(group_id: str, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(request, "DeleteAssetGroup", {"Id": group_id}, principal)


@router.post("/assets")
async def create_asset(payload: AssetCreate, request: Request, principal: PrincipalDependency) -> Response:
    body = {
        "GroupId": payload.group_id,
        "URL": payload.url,
        "AssetType": payload.asset_type,
        "Name": payload.name,
    }
    return await upstream(request, "CreateAsset", {key: value for key, value in body.items() if value is not None}, principal)


@router.get("/assets")
async def list_assets(
    request: Request,
    principal: PrincipalDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str | None = None,
    group_id: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    sort_by: str = "CreateTime",
    sort_order: str = "Desc",
) -> Response:
    return await upstream(request, "ListAssets", {
        "PageNumber": page,
        "PageSize": page_size,
        "SortBy": sort_by,
        "SortOrder": sort_order,
        "Filter": {"GroupIds": group_id, "GroupType": "AIGC", "Statuses": status, "Name": name},
    }, principal)


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(request, "GetAsset", {"Id": asset_id}, principal)


@router.patch("/assets/{asset_id}")
async def update_asset(
    asset_id: str, payload: AssetUpdate, request: Request, principal: PrincipalDependency
) -> Response:
    return await upstream(request, "UpdateAsset", {"Id": asset_id, "Name": payload.name}, principal)


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(request, "DeleteAsset", {"Id": asset_id}, principal)
