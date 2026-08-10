import json
from pathlib import Path

import httpx
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


ADMIN_HEADERS = {"x-admin-token": "test-admin", "content-type": "application/json"}


class FakeVolcengine:
    async def call(self, action, payload, principal):
        return JSONResponse({"action": action, "payload": payload, "projectName": principal.project_name})


def settings(database_path: Path) -> Settings:
    return Settings(
        volcengine_access_key="test-ak",
        volcengine_secret_key="test-sk",
        console_admin_token="test-admin",
        database_path=database_path,
        cors_origins="http://localhost:3000",
    )


def create_project_and_key(client: TestClient) -> str:
    project = client.post(
        "/api/admin/projects",
        headers=ADMIN_HEADERS,
        json={"name": "drama_prod", "displayName": "短剧生产", "description": "production"},
    )
    assert project.status_code == 201
    key = client.post(
        "/api/admin/api-keys",
        headers=ADMIN_HEADERS,
        json={"name": "production", "projectName": "drama_prod"},
    )
    assert key.status_code == 201
    return key.json()["secret"]


def test_admin_and_project_bound_api_key(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        secret = create_project_and_key(client)
        app.state.volcengine = FakeVolcengine()
        response = client.post(
            "/api/v1/assets",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "group_id": "group-123",
                "url": "https://example.com/avatar.png",
                "asset_type": "Image",
                "name": "角色正面照",
                "projectName": "attempted_override",
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "action": "CreateAsset",
            "payload": {
                "GroupId": "group-123",
                "URL": "https://example.com/avatar.png",
                "AssetType": "Image",
                "Name": "角色正面照",
            },
            "projectName": "drama_prod",
        }


def test_missing_api_key_is_rejected(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        response = client.get("/api/v1/assets")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_api_key"


def test_volcengine_signing_and_project_injection(tmp_path: Path) -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"ok": True})

    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        secret = create_project_and_key(client)
        app.state.volcengine.transport = httpx.MockTransport(handler)
        response = client.get("/api/v1/asset-groups", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == 200
    request = captured["request"]
    assert request.url.params["Action"] == "ListAssetGroups"
    assert request.url.params["Version"] == "2024-01-01"
    assert request.headers["authorization"].startswith("HMAC-SHA256 Credential=test-ak/")
    assert request.headers["x-content-sha256"]
    assert json.loads(request.content)["ProjectName"] == "drama_prod"
