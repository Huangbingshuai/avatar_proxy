import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import tos


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


def test_delete_project_preserves_asset_ledger_in_default_project(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, _ = create_key(client)
        app.state.database.create_asset_record(
            "asset-record", "drama_prod", key_id, "tos", "https://cdn.example.com/asset.png",
            bucket="test-bucket", object_key="avatar-assets/drama_prod/asset.png", size_bytes=12,
            status="active", group_id="group-1",
        )
        app.state.database.update_asset_record("asset-record", "active", asset_id="asset-preserved")
        deleted = client.request(
            "DELETE", "/api/internal/project/delete", headers=ADMIN_HEADERS, json={"name": "drama_prod"},
        )
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "avatar-proxy"},
        ).json()["usage"]
        record = app.state.database.find_asset_by_asset_id("avatar-proxy", "asset-preserved")

    assert deleted.status_code == 200
    assert record is not None
    assert usage["totalAssets"] == 1
    assert usage["totalStorageBytes"] == 12


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


def test_project_write_qpm_is_hard_limited_and_defaults_to_unlimited(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = FakeVolcengine()
        auth = {"Authorization": f"Bearer {secret}"}

        unlimited = client.post("/api/asset-group/create", headers=auth, json={"name": "first"})
        quota = client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "writeQpm": 1},
        )
        first = client.post("/api/asset-group/create", headers=auth, json={"name": "second"})
        limited = client.post("/api/asset-group/create", headers=auth, json={"name": "third"})

    assert unlimited.status_code == 200
    assert quota.status_code == 200
    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["error"]["metric"] == "writeQpm"
    assert int(limited.headers["retry-after"]) >= 1


def test_read_qpm_only_creates_deduplicated_alerts(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = FakeVolcengine()
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "readQpm": 1},
        )
        auth = {"Authorization": f"Bearer {secret}"}
        responses = [client.get("/api/asset-group/list", headers=auth) for _ in range(3)]
        events = client.get("/api/internal/quota/events", headers=ADMIN_HEADERS).json()["events"]

    assert all(response.status_code == 200 for response in responses)
    read_events = [event for event in events if event["metric"] == "read_qpm"]
    assert {event["threshold"] for event in read_events} == {70, 90, 100}
    assert len(read_events) == 3


def test_api_key_subquota_cannot_exceed_project_quota(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, _ = create_key(client)
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "writeQpm": 10},
        )
        response = client.put(
            "/api/internal/apikey/quota",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id, "writeQpm": 11},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "key_quota_exceeds_project"


def test_upload_id_is_scoped_to_the_creating_api_key(tmp_path: Path, monkeypatch) -> None:
    class FakeTosClient:
        def __init__(self, *args):
            pass

        def put_object(self, *args, **kwargs):
            return SimpleNamespace(etag="etag", request_id="request")

    monkeypatch.setattr("app.storage.tos.TosClientV2", FakeTosClient)
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, first_secret = create_key(client)
        _, second_secret = create_key(client)
        upload = client.post(
            "/api/asset/upload-file",
            headers={"Authorization": f"Bearer {first_secret}"},
            files={"file": ("portrait.png", b"\x89PNG\r\n\x1a\nbody", "image/png")},
        ).json()
        response = client.post(
            "/api/asset/create",
            headers={"Authorization": f"Bearer {second_secret}"},
            json={"groupId": "group-1", "url": upload["url"], "uploadId": upload["uploadId"]},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "upload_not_found"


def test_upload_id_rejects_a_different_url(tmp_path: Path, monkeypatch) -> None:
    class FakeTosClient:
        def __init__(self, *args):
            pass

        def put_object(self, *args, **kwargs):
            return SimpleNamespace(etag="etag", request_id="request")

    monkeypatch.setattr("app.storage.tos.TosClientV2", FakeTosClient)
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        auth = {"Authorization": f"Bearer {secret}"}
        upload = client.post(
            "/api/asset/upload-file",
            headers=auth,
            files={"file": ("portrait.png", b"\x89PNG\r\n\x1a\nbody", "image/png")},
        ).json()
        response = client.post(
            "/api/asset/create",
            headers=auth,
            json={
                "groupId": "group-1",
                "url": "https://example.com/a-different-object.png",
                "uploadId": upload["uploadId"],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upload_url_mismatch"


def test_deleting_registered_tos_asset_deletes_object_and_releases_storage(tmp_path: Path, monkeypatch) -> None:
    deleted = []

    class FakeTosClient:
        def __init__(self, *args):
            pass

        def put_object(self, *args, **kwargs):
            return SimpleNamespace(etag="etag", request_id="request")

        def delete_object(self, bucket, key):
            deleted.append((bucket, key))
            return SimpleNamespace(status_code=204)

    class AssetVolcengine:
        async def call(self, action, payload, principal):
            if action == "CreateAsset":
                return JSONResponse({"Result": {"AssetId": "asset-created"}})
            return JSONResponse({"ok": True})

    monkeypatch.setattr("app.storage.tos.TosClientV2", FakeTosClient)
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = AssetVolcengine()
        auth = {"Authorization": f"Bearer {secret}"}
        upload = client.post(
            "/api/asset/upload-file",
            headers=auth,
            files={"file": ("portrait.png", b"\x89PNG\r\n\x1a\nbody", "image/png")},
        ).json()
        created = client.post(
            "/api/asset/create",
            headers=auth,
            json={"groupId": "group-1", "url": upload["url"], "uploadId": upload["uploadId"]},
        )
        before = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()
        removed = client.delete("/api/asset/delete", headers=auth, params={"assetId": "asset-created"})
        after = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()

    assert created.status_code == 200
    assert removed.status_code == 200
    assert before["usage"]["totalStorageBytes"] == 12
    assert after["usage"]["totalStorageBytes"] == 0
    assert len(deleted) == 1


def test_pending_upload_older_than_48_hours_is_cleaned(tmp_path: Path, monkeypatch) -> None:
    deleted = []

    class FakeTosClient:
        def __init__(self, *args):
            pass

        def delete_object(self, bucket, key):
            deleted.append((bucket, key))
            return SimpleNamespace(status_code=204)

    monkeypatch.setattr("app.storage.tos.TosClientV2", FakeTosClient)
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app):
        app.state.database.create_asset_record(
            "upload-old", "avatar-proxy", "key-old", "tos", "https://cdn.example.com/old.png",
            bucket="test-bucket", object_key="avatar-assets/avatar-proxy/old.png", size_bytes=10,
        )
        with app.state.database.connect() as connection:
            connection.execute(
                "UPDATE asset_records SET created_at=? WHERE record_id='upload-old'",
                ((datetime.utcnow() - timedelta(hours=49)).strftime("%Y-%m-%d %H:%M:%S"),),
            )
        cleaned = asyncio.run(app.state.storage.cleanup_once())
        record = app.state.database.get_asset_record("upload-old")

    assert cleaned == 1
    assert record["status"] == "deleted"
    assert deleted == [("test-bucket", "avatar-assets/avatar-proxy/old.png")]


def test_existing_database_upgrades_without_losing_projects_or_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    first_app = create_app(settings(database_path))
    with TestClient(first_app) as client:
        create_project(client)
        key_id, secret = create_key(client)

    risk_tables = (
        "quota_events", "admin_audit_logs", "asset_records", "quota_reservations",
        "quota_usage_windows", "api_key_quotas", "project_quotas",
    )
    with first_app.state.database.connect() as connection:
        for table in risk_tables:
            connection.execute(f"DROP TABLE {table}")

    upgraded_app = create_app(settings(database_path))
    with TestClient(upgraded_app) as client:
        projects = client.get("/api/internal/project/list", headers=ADMIN_HEADERS).json()["projects"]
        keys = client.get("/api/internal/apikey/list", headers=ADMIN_HEADERS).json()["apiKeys"]
        login = client.get("/api/auth/me", headers={"Authorization": f"Bearer {secret}"})
        quota = client.get(
            "/api/internal/project/quota", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        )

    assert any(project["name"] == "drama_prod" for project in projects)
    assert any(key["id"] == key_id for key in keys)
    assert login.status_code == 200
    assert quota.json()["quota"]["enabled"] is False


def test_api_key_subquota_takes_effect_immediately(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        app.state.volcengine = FakeVolcengine()
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "writeQpm": 10},
        )
        configured = client.put(
            "/api/internal/apikey/quota",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id, "writeQpm": 1},
        )
        auth = {"Authorization": f"Bearer {secret}"}
        first = client.post("/api/asset-group/create", headers=auth, json={"name": "first"})
        second = client.post("/api/asset-group/create", headers=auth, json={"name": "second"})
        audits = client.get("/api/internal/quota/audits", headers=ADMIN_HEADERS).json()["audits"]

    assert configured.status_code == 200
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["scope"] == "api_key"
    assert {audit["action"] for audit in audits} == {"quota.project.update", "quota.apikey.update"}


def test_failed_external_registration_rolls_back_and_does_not_use_tos_storage(tmp_path: Path) -> None:
    class FailOnceVolcengine:
        def __init__(self):
            self.calls = 0

        async def call(self, action, payload, principal):
            if action != "CreateAsset":
                return JSONResponse({"ok": True})
            self.calls += 1
            if self.calls == 1:
                return JSONResponse({"error": "upstream failed"}, status_code=502)
            return JSONResponse({"Result": {"AssetId": f"asset-{self.calls}"}})

    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = FailOnceVolcengine()
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "dailyAssetCreates": 1, "totalAssets": 1},
        )
        auth = {"Authorization": f"Bearer {secret}"}
        failed = client.post(
            "/api/asset/create", headers=auth,
            json={"groupId": "group-1", "url": "https://example.com/failed.png"},
        )
        succeeded = client.post(
            "/api/asset/create", headers=auth,
            json={"groupId": "group-1", "url": "https://example.com/active.png"},
        )
        limited = client.post(
            "/api/asset/create", headers=auth,
            json={"groupId": "group-1", "url": "https://example.com/limited.png"},
        )
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"},
        ).json()["usage"]

    assert failed.status_code == 502
    assert succeeded.status_code == 200
    assert limited.status_code == 429
    assert usage["dailyAssetCreates"] == 1
    assert usage["totalAssets"] == 1
    assert usage["totalStorageBytes"] == 0


def test_tos_delete_failure_keeps_storage_until_background_retry(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    class FailOnceTosClient:
        def __init__(self, *args):
            pass

        def delete_object(self, bucket, key):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise tos.exceptions.TosClientError("temporary delete failure")
            return SimpleNamespace(status_code=204)

    monkeypatch.setattr("app.storage.tos.TosClientV2", FailOnceTosClient)
    app = create_app(settings(tmp_path / "test.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        app.state.volcengine = FakeVolcengine()
        app.state.database.create_asset_record(
            "upload-retry", "drama_prod", key_id, "tos", "https://cdn.example.com/retry.png",
            bucket="test-bucket", object_key="avatar-assets/drama_prod/retry.png", size_bytes=12,
            status="active", group_id="group-1",
        )
        app.state.database.update_asset_record("upload-retry", "active", asset_id="asset-retry")
        auth = {"Authorization": f"Bearer {secret}"}
        removed = client.delete("/api/asset/delete", headers=auth, params={"assetId": "asset-retry"})
        pending = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"},
        ).json()
        cleaned = asyncio.run(app.state.storage.cleanup_once())
        complete = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"},
        ).json()

    assert removed.status_code == 200
    assert pending["usage"]["totalStorageBytes"] == 12
    assert pending["cleanupObjects"][0]["status"] == "cleanup_pending"
    assert cleaned == 1
    assert complete["usage"]["totalStorageBytes"] == 0
    assert calls == 2
