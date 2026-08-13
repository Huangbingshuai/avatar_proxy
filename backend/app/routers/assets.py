import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response

from ..errors import ApiError
from ..schemas import AssetCreate, AssetGroupCreate, AssetGroupUpdate, AssetUpdate
from ..security import PrincipalDependency


router = APIRouter(prefix="/api", tags=["素材库"])


async def upstream(request: Request, action: str, body: dict[str, Any], principal: PrincipalDependency) -> Response:
    body.pop("ProjectName", None)
    body.pop("projectName", None)
    return await request.app.state.volcengine.call(action, body, principal)


def response_json(response: Response) -> dict[str, Any]:
    try:
        value = json.loads(response.body)
    except (AttributeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def find_asset_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("AssetId", "assetId", "Id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith("asset-"):
                return candidate
        for nested in value.values():
            candidate = find_asset_id(nested)
            if candidate:
                return candidate
    elif isinstance(value, list):
        for nested in value:
            candidate = find_asset_id(nested)
            if candidate:
                return candidate
    return None


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
    database = request.app.state.database
    record = database.find_upload_record(
        principal.project_name,
        principal.id,
        upload_id=payload.upload_id,
        source_url=None if payload.upload_id else payload.url,
    )
    if payload.upload_id and record is None:
        raise ApiError("uploadId 不存在或不属于当前 API Key", 404, "upload_not_found")
    record_id = record["record_id"] if record else f"assetrec_{uuid.uuid4().hex}"
    reservation_id = request.app.state.quota.reserve(principal.project_name, principal.id, {
        "daily_asset_creates": 1,
        "total_assets": 1,
    })
    try:
        if record:
            database.update_asset_record(record_id, "registering", group_id=payload.group_id)
        else:
            database.create_asset_record(
                record_id,
                principal.project_name,
                principal.id,
                "external_url",
                payload.url,
                status="registering",
                group_id=payload.group_id,
            )
        response = await upstream(request, "CreateAsset", {k: v for k, v in body.items() if v is not None}, principal)
    except Exception as error:
        request.app.state.quota.finish_reservation(reservation_id, commit=False)
        database.update_asset_record(record_id, "registration_failed", last_error=str(error))
        raise
    if 200 <= response.status_code < 300:
        asset_id = find_asset_id(response_json(response))
        database.update_asset_record(record_id, "active", group_id=payload.group_id, asset_id=asset_id)
        request.app.state.quota.finish_reservation(reservation_id, commit=True)
    else:
        database.update_asset_record(record_id, "registration_failed", last_error=f"HTTP {response.status_code}")
        request.app.state.quota.finish_reservation(reservation_id, commit=False)
    return response


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
    record = request.app.state.database.find_asset_by_asset_id(principal.project_name, asset_id)
    response = await upstream(request, "DeleteAsset", {"Id": asset_id}, principal)
    if record and 200 <= response.status_code < 300:
        await request.app.state.storage.delete_record_object(record)
    return response


@router.post("/asset/upload-file")
async def upload_asset_file(
    request: Request,
    principal: PrincipalDependency,
    file: UploadFile = File(...),
) -> dict[str, str | int]:
    return await request.app.state.storage.upload_image(file, principal)
