from typing import Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response

from ..schemas import AssetCreate, AssetGroupCreate, AssetGroupUpdate, AssetUpdate
from ..security import PrincipalDependency


router = APIRouter(prefix="/api", tags=["素材库"])


async def upstream(request: Request, action: str, body: dict[str, Any], principal: PrincipalDependency) -> Response:
    body.pop("ProjectName", None)
    body.pop("projectName", None)
    return await request.app.state.volcengine.call(action, body, principal)


@router.post("/asset-group/create")
async def create_asset_group(payload: AssetGroupCreate, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(
        request,
        "CreateAssetGroup",
        {"Name": payload.name, "Description": payload.description, "GroupType": "AIGC"},
        principal,
    )


@router.get("/asset-group/list")
async def list_asset_groups(
    request: Request,
    principal: PrincipalDependency,
    page_number: int = Query(default=1, ge=1, alias="pageNumber"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    name: str | None = None,
    group_ids: list[str] = Query(default=[], alias="groupIds"),
) -> Response:
    filters: dict[str, Any] = {"GroupType": "AIGC"}
    if name:
        filters["Name"] = name
    if group_ids:
        filters["GroupIds"] = group_ids
    return await upstream(request, "ListAssetGroups", {
        "PageNumber": page_number,
        "PageSize": page_size,
        "Filter": filters,
    }, principal)


@router.get("/asset-group/get")
async def get_asset_group(
    request: Request,
    principal: PrincipalDependency,
    group_id: str = Query(min_length=1, alias="groupId"),
) -> Response:
    return await upstream(request, "GetAssetGroup", {"Id": group_id}, principal)


@router.put("/asset-group/update")
async def update_asset_group(
    payload: AssetGroupUpdate,
    request: Request,
    principal: PrincipalDependency,
) -> Response:
    body = {"Id": payload.group_id, "Name": payload.name, "Description": payload.description}
    return await upstream(request, "UpdateAssetGroup", {k: v for k, v in body.items() if v is not None}, principal)


@router.delete("/asset-group/delete")
async def delete_asset_group(
    request: Request,
    principal: PrincipalDependency,
    group_id: str = Query(min_length=1, alias="groupId"),
) -> Response:
    return await upstream(request, "DeleteAssetGroup", {"Id": group_id}, principal)


@router.post("/asset/create")
async def create_asset(payload: AssetCreate, request: Request, principal: PrincipalDependency) -> Response:
    body = {
        "GroupId": payload.group_id,
        "URL": payload.url,
        "AssetType": "Image",
        "Name": payload.name,
    }
    return await upstream(request, "CreateAsset", {k: v for k, v in body.items() if v is not None}, principal)


@router.get("/asset/list")
async def list_assets(
    request: Request,
    principal: PrincipalDependency,
    group_id: str = Query(min_length=1, alias="groupId"),
    page_number: int = Query(default=1, ge=1, alias="pageNumber"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    name: str | None = None,
    statuses: list[str] = Query(default=[]),
    sort_by: str = Query(default="CreateTime", alias="sortBy"),
    sort_order: str = Query(default="Desc", alias="sortOrder"),
) -> Response:
    filters: dict[str, Any] = {"GroupIds": [group_id], "GroupType": "AIGC"}
    if statuses:
        filters["Statuses"] = statuses
    if name:
        filters["Name"] = name
    return await upstream(request, "ListAssets", {
        "PageNumber": page_number,
        "PageSize": page_size,
        "SortBy": sort_by,
        "SortOrder": sort_order,
        "Filter": filters,
    }, principal)


@router.get("/asset/get")
async def get_asset(
    request: Request,
    principal: PrincipalDependency,
    asset_id: str = Query(min_length=1, alias="assetId"),
) -> Response:
    return await upstream(request, "GetAsset", {"Id": asset_id}, principal)


@router.put("/asset/update")
async def update_asset(payload: AssetUpdate, request: Request, principal: PrincipalDependency) -> Response:
    return await upstream(request, "UpdateAsset", {"Id": payload.asset_id, "Name": payload.name}, principal)


@router.delete("/asset/delete")
async def delete_asset(
    request: Request,
    principal: PrincipalDependency,
    asset_id: str = Query(min_length=1, alias="assetId"),
) -> Response:
    return await upstream(request, "DeleteAsset", {"Id": asset_id}, principal)


@router.post("/asset/upload-file")
async def upload_asset_file(
    request: Request,
    principal: PrincipalDependency,
    file: UploadFile = File(...),
) -> dict[str, str | int]:
    return await request.app.state.storage.upload_image(file, principal)
