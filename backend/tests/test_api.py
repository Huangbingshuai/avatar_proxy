import json
from pathlib import Path
from types import SimpleNamespace

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
        seedance_ark_api_key="test-ark-key",
        tos_bucket="test-bucket",
        tos_public_base_url="https://cdn.example.com",
        console_admin_token="test-admin",
        database_path=database_path,
        cors_origins="http://localhost:3000",
    )


def create_project(client: TestClient, name: str = "drama_prod") -> None:
    response = client.post(
        "/api/internal/project/create",
        headers=ADMIN_HEADERS,
        json={"name": name, "displayName": "短剧生产", "description": "production"},
    )
    assert response.status_code == 201


def create_key(client: TestClient, project_name: str = "drama_prod") -> tuple[str, str]:
    response = client.post(
        "/api/internal/apikey/create",
        headers=ADMIN_HEADERS,
        json={"name": "production", "projectName": project_name},
    )
    assert response.status_code == 201
    body = response.json()
    return body["apiKey"]["id"], body["secret"]


def test_assets_use_project_bound_to_business_api_key(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = FakeVolcengine()
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "groupId": "group-123",
                "url": "https://example.com/avatar.png",
                "name": "角色正面照",
                "projectName": "attempted_override",
                "assetType": "Video",
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


def test_api_key_defaults_to_avatar_proxy_project_and_injects_it_into_asset_group(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        key_response = client.post(
            "/api/internal/apikey/create",
            headers=ADMIN_HEADERS,
            json={"name": "default-user"},
        )
        assert key_response.status_code == 201
        secret = key_response.json()["secret"]
        assert key_response.json()["apiKey"]["projectName"] == "avatar-proxy"

        app.state.volcengine = FakeVolcengine()
        group_response = client.post(
            "/api/asset-group/create",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "name": "默认素材库",
                "description": "默认项目素材",
                "projectName": "attempted_override",
            },
        )

    assert group_response.status_code == 200
    assert group_response.json()["projectName"] == "avatar-proxy"
    assert group_response.json()["payload"] == {
        "Name": "默认素材库",
        "Description": "默认项目素材",
        "GroupType": "AIGC",
    }


def test_delete_project_moves_keys_to_avatar_proxy_and_protects_default(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, _ = create_key(client)
        deleted = client.request(
            "DELETE",
            "/api/internal/project/delete",
            headers=ADMIN_HEADERS,
            json={"name": "drama_prod"},
        )
        projects = client.get("/api/internal/project/list", headers=ADMIN_HEADERS).json()["projects"]
        keys = client.get("/api/internal/apikey/list", headers=ADMIN_HEADERS).json()["apiKeys"]
        protected = client.request(
            "DELETE",
            "/api/internal/project/delete",
            headers=ADMIN_HEADERS,
            json={"name": "avatar-proxy"},
        )

    assert deleted.status_code == 200
    assert deleted.json()["movedKeyCount"] == 1
    assert all(project["name"] != "drama_prod" for project in projects)
    assert next(key for key in keys if key["id"] == key_id)["projectName"] == "avatar-proxy"
    assert protected.status_code == 400
    assert protected.json()["error"]["code"] == "default_project_protected"


def test_internal_bind_project_and_disable_key(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        create_project(client, "campaign_b")
        key_id, secret = create_key(client)
        bind = client.post(
            "/api/internal/apikey/bind-project",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id, "projectName": "campaign_b"},
        )
        assert bind.status_code == 200

        app.state.volcengine = FakeVolcengine()
        before_disable = client.get(
            "/api/asset-group/list",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert before_disable.json()["projectName"] == "campaign_b"

        disabled = client.put(
            "/api/internal/apikey/disable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        assert disabled.status_code == 200
        after_disable = client.get(
            "/api/asset-group/list",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert after_disable.status_code == 401


def test_api_key_can_only_be_deleted_after_it_is_disabled(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        active_delete = client.request(
            "DELETE",
            "/api/internal/apikey/delete",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        client.put(
            "/api/internal/apikey/disable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        disabled_delete = client.request(
            "DELETE",
            "/api/internal/apikey/delete",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        keys = client.get("/api/internal/apikey/list", headers=ADMIN_HEADERS).json()["apiKeys"]
        auth_after_delete = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {secret}"},
        )

    assert active_delete.status_code == 409
    assert active_delete.json()["error"]["code"] == "api_key_must_be_disabled"
    assert disabled_delete.status_code == 200
    assert all(key["id"] != key_id for key in keys)
    assert auth_after_delete.status_code == 401


def test_disabled_api_key_can_be_enabled_and_use_its_original_secret(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        already_active = client.put(
            "/api/internal/apikey/enable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        client.put(
            "/api/internal/apikey/disable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        disabled_auth = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {secret}"},
        )
        enabled = client.put(
            "/api/internal/apikey/enable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        restored_auth = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {secret}"},
        )

    assert already_active.status_code == 409
    assert already_active.json()["error"]["code"] == "api_key_already_active"
    assert disabled_auth.status_code == 401
    assert enabled.status_code == 200
    assert restored_auth.status_code == 200


def test_missing_api_key_is_rejected(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        response = client.get("/api/asset/list", params={"groupId": "group-123"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_api_key"


def test_api_key_login_returns_bound_project(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {secret}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "apiKeyId": key_id,
    }


def test_api_key_login_rejects_invalid_key(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer vap_live_invalid"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_volcengine_signing_and_project_injection(tmp_path: Path) -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"ok": True})

    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine.transport = httpx.MockTransport(handler)
        response = client.get(
            "/api/asset-group/list",
            headers={"Authorization": f"Bearer {secret}"},
        )

    assert response.status_code == 200
    request = captured["request"]
    assert request.url.params["Action"] == "ListAssetGroups"
    assert request.url.params["Version"] == "2024-01-01"
    assert request.headers["authorization"].startswith("HMAC-SHA256 Credential=test-ak/")
    assert request.headers["x-content-sha256"]
    assert json.loads(request.content)["ProjectName"] == "drama_prod"


def test_one_api_key_can_create_multiple_volcengine_asset_groups(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"Result": {"Id": f"group-{len(requests)}"}})

    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine.transport = httpx.MockTransport(handler)
        auth = {"Authorization": f"Bearer {secret}"}
        first = client.post(
            "/api/asset-group/create",
            headers=auth,
            json={"name": "人物素材", "description": "主要角色"},
        )
        second = client.post(
            "/api/asset-group/create",
            headers=auth,
            json={"name": "场景素材", "description": "背景与环境"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert [request.url.params["Action"] for request in requests] == ["CreateAssetGroup", "CreateAssetGroup"]
    payloads = [json.loads(request.content) for request in requests]
    assert [payload["Name"] for payload in payloads] == ["人物素材", "场景素材"]
    assert all(payload["GroupType"] == "AIGC" for payload in payloads)
    assert all(payload["ProjectName"] == "drama_prod" for payload in payloads)


def test_seedance_create_get_and_cancel_use_server_api_key(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"id": "cgt-test"})
        if request.method == "GET":
            return httpx.Response(200, json={"id": "cgt-test", "status": "running"})
        return httpx.Response(204)

    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.seedance.transport = httpx.MockTransport(handler)
        auth = {"Authorization": f"Bearer {secret}"}
        created = client.post(
            "/api/video/generate",
            headers=auth,
            json={
                "model": "doubao-seedance-test",
                "content": [
                    {"type": "text", "text": "图片1中的人物拿起图片2中的产品"},
                    {"type": "image_url", "image_url": {"url": "asset://asset-1"}, "role": "reference_image"},
                    {"type": "image_url", "image_url": {"url": "asset://asset-2"}, "role": "reference_image"},
                ],
                "returnLastFrame": True,
                "generateAudio": True,
                "ratio": "16:9",
                "duration": 5,
            },
        )
        fetched = client.get("/api/video/task/cgt-test", headers=auth)
        cancelled = client.post("/api/video/task/cgt-test/cancel", headers=auth)

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert cancelled.status_code == 204
    assert [request.method for request in requests] == ["POST", "GET", "DELETE"]
    assert all(request.headers["authorization"] == "Bearer test-ark-key" for request in requests)
    assert requests[0].url.path == "/api/v3/contents/generations/tasks"
    payload = json.loads(requests[0].content)
    assert payload["return_last_frame"] is True
    assert payload["generate_audio"] is True
    assert payload["ratio"] == "16:9"
    assert payload["duration"] == 5
    assert [item["image_url"]["url"] for item in payload["content"][1:]] == ["asset://asset-1", "asset://asset-2"]
    assert requests[1].url.path.endswith("/contents/generations/tasks/cgt-test")


def test_video_history_persists_across_logins_and_is_scoped_to_api_key(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "cgt-persisted",
            "model": "seedance-test",
            "status": "queued",
            "created_at": 1786377600,
        })

    app = create_app(settings(database_path))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.seedance.transport = httpx.MockTransport(handler)
        created = client.post(
            "/api/video/generate",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "model": "seedance-test",
                "content": [{"type": "text", "text": "角色走进雨夜街道"}],
                "ratio": "16:9",
                "duration": 5,
                "resolution": "720p",
                "metadata": {
                    "prompt": "角色走进雨夜街道",
                    "promptDocument": "serialized-prompt",
                    "assets": [{
                        "id": "asset-1",
                        "groupId": "group-1",
                        "name": "主角",
                        "status": "Active",
                        "previewUrl": "https://example.com/asset-1.png",
                    }],
                    "durationMode": "seconds",
                    "generationCount": 1,
                },
            },
        )
        _, other_secret = create_key(client)

    assert created.status_code == 200

    restarted_app = create_app(settings(database_path))
    with TestClient(restarted_app) as restarted_client:
        history = restarted_client.get(
            "/api/video/history",
            headers={"Authorization": f"Bearer {secret}"},
        )
        other_history = restarted_client.get(
            "/api/video/history",
            headers={"Authorization": f"Bearer {other_secret}"},
        )
        removed = restarted_client.delete(
            "/api/video/history/cgt-persisted",
            headers={"Authorization": f"Bearer {secret}"},
        )
        history_after_remove = restarted_client.get(
            "/api/video/history",
            headers={"Authorization": f"Bearer {secret}"},
        )

    assert history.status_code == 200
    assert history.json()["tasks"] == [{
        "id": "cgt-persisted",
        "createdAt": 1786377600000,
        "prompt": "角色走进雨夜街道",
        "promptDocument": "serialized-prompt",
        "assetName": "主角",
        "assetNames": ["主角"],
        "assets": [{
            "id": "asset-1",
            "groupId": "group-1",
            "name": "主角",
            "status": "Active",
            "previewUrl": "https://example.com/asset-1.png",
        }],
        "model": "seedance-test",
        "ratio": "16:9",
        "duration": 5,
        "durationMode": "seconds",
        "resolution": "720p",
        "generationCount": 1,
        "status": "queued",
    }]
    assert other_history.json()["tasks"] == []
    assert removed.json() == {"removed": True}
    assert history_after_remove.json()["tasks"] == []


def test_existing_browser_history_can_be_imported_once(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        auth = {"Authorization": f"Bearer {secret}"}
        imported = client.post(
            "/api/video/history/import",
            headers=auth,
            json={"tasks": [{
                "id": "legacy-task",
                "createdAt": 1786377600000,
                "prompt": "旧浏览器任务",
                "status": "succeeded",
                "videoUrl": "https://example.com/legacy.mp4",
            }]},
        )
        history = client.get("/api/video/history", headers=auth)
        cleared = client.delete("/api/video/history", headers=auth)

    assert imported.json() == {"imported": 1}
    assert history.json()["tasks"][0]["id"] == "legacy-task"
    assert history.json()["tasks"][0]["videoUrl"] == "https://example.com/legacy.mp4"
    assert cleared.json() == {"removed": 1}


def test_video_usage_is_scoped_to_current_api_key_and_deduplicates_tasks(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "cgt-usage", "model": "seedance-test", "created_at": 1786377600})
        return httpx.Response(200, json={
            "id": "cgt-usage", "model": "seedance-test", "status": "succeeded",
            "created_at": 1786377600,
            "usage": {"total_tokens": 35800},
        })

    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.seedance.transport = httpx.MockTransport(handler)
        auth = {"Authorization": f"Bearer {secret}"}
        client.post("/api/video/generate", headers=auth, json={
            "model": "seedance-test", "content": [{"type": "text", "text": "测试"}],
        })
        client.get("/api/video/task/cgt-usage", headers=auth)
        client.get("/api/video/task/cgt-usage", headers=auth)
        usage = client.get("/api/video/usage?days=30", headers=auth)

        _, other_secret = create_key(client)
        other_usage = client.get(
            "/api/video/usage?days=30", headers={"Authorization": f"Bearer {other_secret}"}
        )

    assert usage.status_code == 200
    assert usage.json()["summary"] == {
        "inputTokens": 0, "outputTokens": 35800, "totalTokens": 35800, "requestCount": 1,
    }
    assert other_usage.json()["summary"]["totalTokens"] == 0


def test_seedance_rejects_more_than_nine_reference_images(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        content = [{"type": "text", "text": "使用全部参考图生成视频"}]
        content.extend(
            {"type": "image_url", "image_url": {"url": f"asset://asset-{index}"}, "role": "reference_image"}
            for index in range(10)
        )
        response = client.post(
            "/api/video/generate",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-seedance-test", "content": content},
        )

    assert response.status_code == 422


def test_production_docs_are_disabled_by_default(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_upload_file_stores_image_in_project_namespace(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    class FakeTosClient:
        def __init__(self, ak, sk, endpoint, region):
            captured["credentials"] = (ak, sk, endpoint, region)

        def put_object(self, bucket, key, **kwargs):
            captured["upload"] = (bucket, key, kwargs)
            return SimpleNamespace(etag="etag-test", request_id="request-test")

    monkeypatch.setattr("app.storage.tos.TosClientV2", FakeTosClient)
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = client.post(
            "/api/asset/upload-file",
            headers={"Authorization": f"Bearer {secret}"},
            files={"file": ("portrait.png", b"\x89PNG\r\n\x1a\nbody", "image/png")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://cdn.example.com/avatar-assets/drama_prod/")
    assert body["contentType"] == "image/png"
    assert body["size"] == 12
    bucket, key, kwargs = captured["upload"]
    assert bucket == "test-bucket"
    assert key.startswith("avatar-assets/drama_prod/")
    assert kwargs["content"] == b"\x89PNG\r\n\x1a\nbody"


def test_upload_file_rejects_placeholder_bucket(tmp_path: Path) -> None:
    invalid_settings = settings(tmp_path / "test.db")
    invalid_settings.tos_bucket = "your_bucket"
    app = create_app(invalid_settings)
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = client.post(
            "/api/asset/upload-file",
            headers={"Authorization": f"Bearer {secret}"},
            files={"file": ("portrait.png", b"\x89PNG\r\n\x1a\nbody", "image/png")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "tos_not_configured"
