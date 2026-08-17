from pathlib import Path

import pytest
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient

from app.main import create_app
from app.routers.assets import find_asset_id, response_json

from conftest import ADMIN_HEADERS, PNG, build_settings, create_key, create_project
from test_storage_deep import SuccessfulTosClient, upload


class RecordingVolcengine:
    def __init__(self, responses: dict[str, Response] | None = None):
        self.calls: list[tuple[str, dict, str]] = []
        self.responses = responses or {}

    async def call(self, action, payload, principal):
        self.calls.append((action, payload, principal.project_name))
        return self.responses.get(action, JSONResponse({"ok": True, "action": action}))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"Result": {"AssetId": "asset-official"}}, "asset-official"),
        ({"result": [{"assetId": "asset-list"}]}, "asset-list"),
        ({"ResponseMetadata": {}, "Data": {"Items": [{"Id": "asset-nested"}]}}, "asset-nested"),
        ({"AssetId": 123, "id": "group-not-an-asset"}, None),
        ([{"id": "asset-top-list"}], "asset-top-list"),
    ],
)
def test_create_asset_response_id_shapes(payload, expected) -> None:
    assert find_asset_id(payload) == expected


def test_response_json_handles_invalid_and_non_object_bodies() -> None:
    assert response_json(Response(content=b"not-json")) == {}
    assert response_json(Response(content=b"[1,2,3]")) == {}
    assert response_json(Response(content=b'{"ok":true}')) == {"ok": True}


@pytest.mark.parametrize(
    ("asset_type", "expected"),
    [(None, "Image"), ("Image", "Image"), ("Video", "Video"), ("Audio", "Audio")],
)
def test_create_asset_forwards_all_official_asset_types_and_defaults_to_image(
    tmp_path: Path, asset_type: str | None, expected: str
) -> None:
    app = create_app(build_settings(tmp_path / f"asset-type-{expected}-{asset_type}.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        recorder = RecordingVolcengine()
        app.state.volcengine = recorder
        body = {
            "groupId": "group-1",
            "url": f"https://example.com/material-{expected.lower()}",
            "name": "客户素材",
        }
        if asset_type is not None:
            body["assetType"] = asset_type
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {secret}"},
            json=body,
        )

    assert response.status_code == 200
    assert recorder.calls[0][1]["AssetType"] == expected


def test_create_asset_rejects_upload_id_asset_type_mismatch(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "upload-type-mismatch.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        app.state.database.create_asset_record(
            "upload_video",
            "drama_prod",
            key_id,
            "tos",
            "https://cdn.example.com/material.mp4",
            bucket="test-bucket",
            object_key="material.mp4",
            asset_type="Video",
            content_type="video/mp4",
        )
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "groupId": "group-1",
                "url": "https://cdn.example.com/material.mp4",
                "uploadId": "upload_video",
                "assetType": "Image",
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_asset_type_mismatch"


def test_asset_name_is_limited_to_sixty_four_characters(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "asset-name.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "groupId": "group-1",
                "url": "https://example.com/image.png",
                "name": "素" * 65,
            },
        )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "upstream_payload",
    [
        {"Result": {"AssetId": "asset-official"}},
        {"Result": {"Assets": [{"assetId": "asset-list"}]}},
        {"Data": [{"Nested": {"Id": "asset-nested"}}]},
    ],
)
def test_create_asset_persists_ids_from_nested_official_response_shapes(
    tmp_path: Path, upstream_payload: dict
) -> None:
    app = create_app(build_settings(tmp_path / f"asset-{find_asset_id(upstream_payload)}.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = RecordingVolcengine({"CreateAsset": JSONResponse(upstream_payload)})
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {secret}"},
            json={"groupId": "group-1", "url": "https://example.com/image.png"},
        )
        record = app.state.database.find_asset_by_asset_id("drama_prod", find_asset_id(upstream_payload))

    assert response.status_code == 200
    assert record["status"] == "active"


def test_missing_asset_id_preserves_tos_object_and_storage(tmp_path: Path, monkeypatch) -> None:
    SuccessfulTosClient.deletes.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / "missing-id.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        auth = {"Authorization": f"Bearer {secret}"}
        uploaded = upload(client, secret, "portrait.png", PNG, "image/png").json()
        app.state.volcengine = RecordingVolcengine({"CreateAsset": JSONResponse({"Result": {"Accepted": True}})})
        response = client.post(
            "/api/asset/create",
            headers=auth,
            json={"groupId": "group-1", "url": uploaded["url"], "uploadId": uploaded["uploadId"]},
        )
        record = app.state.database.get_asset_record(uploaded["uploadId"])
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()["usage"]

    assert response.status_code == 200
    assert record["status"] == "active"
    assert record["asset_id"] is None
    assert usage["totalAssets"] == 1
    assert usage["totalStorageBytes"] == len(PNG)
    assert SuccessfulTosClient.deletes == []


def test_upload_registration_failure_can_retry_once_then_is_consumed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)

    class InspectingVolcengine:
        def __init__(self, database, record_id):
            self.database = database
            self.record_id = record_id
            self.calls = 0

        async def call(self, action, payload, principal):
            self.calls += 1
            record = self.database.get_asset_record(self.record_id)
            assert record["status"] == "registering"
            if self.calls == 1:
                raise RuntimeError("upstream unavailable")
            return JSONResponse({"Result": [{"AssetId": "asset-retried"}]})

    app = create_app(build_settings(tmp_path / "retry.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        create_project(client)
        _, secret = create_key(client)
        auth = {"Authorization": f"Bearer {secret}"}
        uploaded = upload(client, secret, "portrait.png", PNG, "image/png").json()
        app.state.volcengine = InspectingVolcengine(app.state.database, uploaded["uploadId"])
        body = {"groupId": "group-1", "url": uploaded["url"], "uploadId": uploaded["uploadId"]}
        failed = client.post("/api/asset/create", headers=auth, json=body)
        failed_record = app.state.database.get_asset_record(uploaded["uploadId"])
        succeeded = client.post("/api/asset/create", headers=auth, json=body)
        repeated = client.post("/api/asset/create", headers=auth, json=body)
        final_record = app.state.database.get_asset_record(uploaded["uploadId"])

    assert failed.status_code == 500
    assert failed_record["status"] == "registration_failed"
    assert "upstream unavailable" in failed_record["last_error"]
    assert succeeded.status_code == 200
    assert final_record["status"] == "active"
    assert final_record["asset_id"] == "asset-retried"
    assert repeated.status_code == 404
    assert repeated.json()["error"]["code"] == "upload_not_found"


def test_non_2xx_registration_rolls_back_asset_quota_but_retains_tos_until_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    SuccessfulTosClient.deletes.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / "non-2xx.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        auth = {"Authorization": f"Bearer {secret}"}
        uploaded = upload(client, secret, "portrait.png", PNG, "image/png").json()
        app.state.volcengine = RecordingVolcengine(
            {"CreateAsset": JSONResponse({"error": "moderation"}, status_code=422)}
        )
        response = client.post(
            "/api/asset/create",
            headers=auth,
            json={"groupId": "group-1", "url": uploaded["url"], "uploadId": uploaded["uploadId"]},
        )
        record = app.state.database.get_asset_record(uploaded["uploadId"])
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()["usage"]

    assert response.status_code == 422
    assert record["status"] == "registration_failed"
    assert usage.get("dailyAssetCreates", 0) == 0
    assert usage["totalAssets"] == 0
    assert usage["totalStorageBytes"] == len(PNG)
    assert SuccessfulTosClient.deletes == []


def test_upload_id_is_rejected_across_project_boundary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / "project-scope.db"))
    with TestClient(app) as client:
        create_project(client, "customer_a")
        create_project(client, "customer_b")
        _, first_secret = create_key(client, "customer_a", "a")
        _, second_secret = create_key(client, "customer_b", "b")
        uploaded = upload(client, first_secret, "portrait.png", PNG, "image/png").json()
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {second_secret}"},
            json={"groupId": "group-1", "url": uploaded["url"], "uploadId": uploaded["uploadId"]},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "upload_not_found"


def test_public_url_asset_never_contributes_tos_storage(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "public-url.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = RecordingVolcengine(
            {"CreateAsset": JSONResponse({"Result": {"AssetId": "asset-public"}})}
        )
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {secret}"},
            json={"groupId": "group-1", "url": "https://customer.example.com/image.png"},
        )
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()["usage"]

    assert response.status_code == 200
    assert usage["totalAssets"] == 1
    assert usage["totalStorageBytes"] == 0


def test_asset_group_and_asset_crud_contracts_build_expected_filters(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "crud.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        recorder = RecordingVolcengine()
        app.state.volcengine = recorder
        auth = {"Authorization": f"Bearer {secret}"}
        responses = [
            client.get(
                "/api/asset-group/list",
                headers=auth,
                params=[("pageNumber", 2), ("pageSize", 5), ("name", "people"), ("groupIds", "g1"), ("groupIds", "g2")],
            ),
            client.get("/api/asset-group/get", headers=auth, params={"groupId": "g1"}),
            client.put(
                "/api/asset-group/update", headers=auth,
                json={"groupId": "g1", "name": "new-name"},
            ),
            client.delete("/api/asset-group/delete", headers=auth, params={"groupId": "g1"}),
            client.get(
                "/api/asset/list",
                headers=auth,
                params=[
                    ("groupId", "g1"), ("pageNumber", 3), ("pageSize", 9), ("name", "portrait"),
                    ("statuses", "Active"), ("statuses", "Failed"), ("sortBy", "Name"), ("sortOrder", "Asc"),
                ],
            ),
            client.get("/api/asset/get", headers=auth, params={"assetId": "asset-1"}),
            client.put("/api/asset/update", headers=auth, json={"assetId": "asset-1", "name": "renamed"}),
        ]

    assert all(response.status_code == 200 for response in responses)
    calls = {action: payload for action, payload, _ in recorder.calls}
    assert calls["ListAssetGroups"]["Filter"] == {"GroupType": "AIGC", "Name": "people", "GroupIds": ["g1", "g2"]}
    assert calls["GetAssetGroup"] == {"Id": "g1"}
    assert calls["UpdateAssetGroup"] == {"Id": "g1", "Name": "new-name"}
    assert calls["DeleteAssetGroup"] == {"Id": "g1"}
    assert calls["ListAssets"] == {
        "PageNumber": 3,
        "PageSize": 9,
        "SortBy": "Name",
        "SortOrder": "Asc",
        "Filter": {"GroupIds": ["g1"], "GroupType": "AIGC", "Statuses": ["Active", "Failed"], "Name": "portrait"},
    }
    assert calls["GetAsset"] == {"Id": "asset-1"}
    assert calls["UpdateAsset"] == {"Id": "asset-1", "Name": "renamed"}


def test_failed_upstream_delete_keeps_tos_record_active(tmp_path: Path, monkeypatch) -> None:
    SuccessfulTosClient.deletes.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / "delete-upstream.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        app.state.database.create_asset_record(
            "upload-1", "drama_prod", key_id, "tos", "https://cdn.example.com/image.png",
            bucket="test-bucket", object_key="image.png", size_bytes=10, status="active",
        )
        app.state.database.update_asset_record("upload-1", "active", asset_id="asset-1")
        app.state.volcengine = RecordingVolcengine(
            {"DeleteAsset": JSONResponse({"error": "busy"}, status_code=503)}
        )
        response = client.delete(
            "/api/asset/delete",
            headers={"Authorization": f"Bearer {secret}"},
            params={"assetId": "asset-1"},
        )
        record = app.state.database.get_asset_record("upload-1")

    assert response.status_code == 503
    assert record["status"] == "active"
    assert SuccessfulTosClient.deletes == []
