import json
import time
from pathlib import Path

import httpx
import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.errors import ApiError
from app.provider_relay import (
    CredentialVault,
    ModelRoute,
    _loaded,
    _provider_request_id,
    _secret_hint,
)
from app.security import ApiPrincipal
from conftest import ADMIN_HEADERS, build_settings, create_key, create_project
from test_provider_relay import provision, relay_client


def error_code(callable_value) -> str:
    with pytest.raises(ApiError) as captured:
        callable_value()
    return captured.value.code


def test_vault_and_provider_config_validation_branches(tmp_path: Path) -> None:
    assert _loaded(None, {"fallback": True}) == {"fallback": True}
    assert _loaded("not-json", []) == []
    assert _secret_hint("tiny") == "****"
    assert _provider_request_id(httpx.Headers(), {"requestId": "body-request"}) == "body-request"
    assert _provider_request_id(httpx.Headers(), {"id": 3}) is None
    missing = CredentialVault(build_settings(tmp_path / "missing.db"))
    invalid = CredentialVault(
        build_settings(
            tmp_path / "invalid.db",
            provider_credential_encryption_key=SecretStr("not-a-fernet-key"),
        )
    )
    valid = CredentialVault(
        build_settings(
            tmp_path / "valid.db",
            provider_credential_encryption_key=SecretStr(Fernet.generate_key().decode()),
        )
    )
    assert error_code(missing._fernet) == "provider_encryption_key_missing"
    assert error_code(invalid._fernet) == "provider_encryption_key_invalid"
    assert error_code(lambda: valid.encrypt("short")) == "provider_secret_invalid"
    assert error_code(lambda: valid.decrypt(Fernet.generate_key().decode())) == "provider_secret_decrypt_failed"
    encrypted = valid.encrypt("provider-secret-long")
    assert valid.decrypt(encrypted) == "provider-secret-long"

    with relay_client(tmp_path) as client:
        validate = client.app.state.provider_relay._validate_provider_config
        assert error_code(lambda: validate("unknown", {})) == "provider_not_supported"
        assert error_code(lambda: validate("openai", [])) == "provider_config_invalid"
        assert error_code(lambda: validate("openai", {"base_url": "http://127.0.0.1"})) == "provider_config_field_forbidden"
        assert error_code(lambda: validate("aliyun_bailian", {})) == "aliyun_workspace_invalid"
        assert error_code(lambda: validate("aliyun_bailian", {"workspaceId": "bad workspace"})) == "aliyun_workspace_invalid"
        assert error_code(lambda: validate("aliyun_bailian", {"workspaceId": "ok", "region": "moon"})) == "aliyun_region_invalid"
        assert error_code(lambda: validate("openai", {"project": "x" * 257})) == "provider_config_invalid"
        assert validate("aliyun_bailian", {"workspaceId": "work_1"}) == {
            "workspaceId": "work_1",
            "region": "cn-beijing",
        }


def test_base_url_and_header_guards(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        relay = client.app.state.provider_relay
        base = dict(
            alias="x", display_name="x", modality="text", protocol="test", capabilities={},
            upstream_model="real", channel_id="channel", channel_name="channel",
            credential_id="credential", secret="secret-value",
        )
        openai = ModelRoute(provider="openai", channel_config={"organization": "org", "project": "proj"}, **base)
        headers = relay._headers(openai)
        assert headers["openai-organization"] == "org" and headers["openai-project"] == "proj"
        assert error_code(lambda: relay._base_url(ModelRoute(provider="unknown", channel_config={}, **base))) == "provider_adapter_missing"
        bad_ali = ModelRoute(provider="aliyun_bailian", channel_config={}, **base)
        assert error_code(lambda: relay._base_url(bad_ali)) == "aliyun_channel_invalid"


def test_channel_full_lifecycle_and_not_found_branches(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        create_project(client, "channels")
        relay = client.app.state.provider_relay
        first = relay.create_channel(
            project_name="channels",
            name="openai-main",
            provider="openai",
            config={"organization": "org-a", "project": "proj-a"},
            secret="openai-secret-abcdefgh",
            actor_id="owner",
        )
        assert relay.list_channels("channels")[0]["id"] == first["id"]
        assert error_code(lambda: relay.create_channel(
            project_name="channels", name="openai-main", provider="openai", config={},
            secret="another-secret-abcdefgh", actor_id="owner"
        )) == "provider_channel_exists"
        assert error_code(lambda: relay.create_channel(
            project_name="missing", name="x", provider="openai", config={},
            secret="another-secret-abcdefgh", actor_id="owner"
        )) == "project_not_found"
        assert error_code(lambda: relay.create_channel(
            project_name="channels", name="", provider="openai", config={},
            secret="another-secret-abcdefgh", actor_id="owner"
        )) == "provider_channel_name_invalid"

        rotated = relay.rotate_channel_secret(first["id"], "rotated-secret-abcdefgh", "owner")
        assert rotated["secretHint"].endswith("efgh")
        with client.app.state.database.connect() as connection:
            statuses = [row[0] for row in connection.execute(
                "SELECT status FROM provider_credentials WHERE channel_id=? ORDER BY created_at", (first["id"],)
            )]
        assert statuses == ["retired", "active"]
        assert relay.set_channel_status(first["id"], False)["status"] == "disabled"
        assert relay.set_channel_status(first["id"], True)["status"] == "active"
        assert error_code(lambda: relay.rotate_channel_secret("missing", "new-secret-abcdefgh", "owner")) == "provider_channel_not_found"
        assert error_code(lambda: relay.set_channel_status("missing", True)) == "provider_channel_not_found"

        relay.delete_channel(first["id"])
        assert relay.get_channel(first["id"]) is None
        assert relay.list_channels("channels") == []
        with client.app.state.database.connect() as connection:
            row = connection.execute("SELECT status,deleted_at FROM provider_channels WHERE id=?", (first["id"],)).fetchone()
            credentials = connection.execute("SELECT COUNT(*) FROM provider_credentials WHERE channel_id=?", (first["id"],)).fetchone()[0]
        assert row["status"] == "disabled" and row["deleted_at"]
        assert credentials == 2
        assert error_code(lambda: relay.delete_channel(first["id"])) == "provider_channel_not_found"

        reused = relay.create_channel(
            project_name="channels", name="openai-main", provider="openai", config={},
            secret="reuse-secret-abcdefgh", actor_id="owner"
        )
        assert reused["id"] != first["id"]


def test_project_binding_validation_and_access_branches(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        create_project(client, "binding")
        key_id, _ = create_key(client, "binding")
        relay = client.app.state.provider_relay
        ark = relay.create_channel(
            project_name="binding", name="ark", provider="volcengine_ark", config={},
            secret="ark-secret-abcdefgh", actor_id="owner"
        )
        openai = relay.create_channel(
            project_name="binding", name="openai", provider="openai", config={},
            secret="openai-secret-abcdefgh", actor_id="owner"
        )
        assert error_code(lambda: relay.project_models("missing")) == "project_not_found"
        assert error_code(lambda: relay.set_project_models("missing", [], "admin")) == "project_not_found"
        duplicate = [
            {"model": "glm-5.2", "channelId": ark["id"], "upstreamModel": "ep-1"},
            {"model": "glm-5.2", "channelId": ark["id"], "upstreamModel": "ep-2"},
        ]
        assert error_code(lambda: relay.set_project_models("binding", duplicate, "admin")) == "model_binding_invalid"
        assert error_code(lambda: relay.set_project_models(
            "binding", [{"model": "missing", "channelId": ark["id"], "upstreamModel": "ep"}], "admin"
        )) == "model_or_channel_not_found"
        assert error_code(lambda: relay.set_project_models(
            "binding", [{"model": "glm-5.2", "channelId": openai["id"], "upstreamModel": "ep"}], "admin"
        )) == "model_provider_mismatch"

        saved = relay.set_project_models(
            "binding", [{"model": "glm-5.2", "channelId": ark["id"], "upstreamModel": "client-override"}], "admin"
        )
        assert next(item for item in saved if item["model"] == "glm-5.2")["upstreamModel"] == "glm-5-2-260617"
        assert relay.resolve(ApiPrincipal(key_id, "binding"), "glm-5.2").alias == "glm-5.2"
        relay.set_project_models("binding", [], "admin")
        assert relay.project_models("binding")[0]["enabled"] is False
        assert error_code(lambda: relay.resolve(ApiPrincipal(key_id, "binding"), "glm-5.2")) == "model_not_allowed"


@pytest.mark.asyncio
async def test_upstream_error_mapping_invalid_response_and_unreachable(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, _, _ = provision(
            client, provider="volcengine_ark", alias="glm-5.2", upstream_model="ep-glm"
        )
        relay = client.app.state.provider_relay
        principal = ApiPrincipal(key_id, "relay_project")
        route = relay.resolve(principal, "glm-5.2")

        relay.transport = httpx.MockTransport(lambda _: httpx.Response(
            429, headers={"x-request-id": "up-429"}, json={"error": {"message": "rate limited"}}
        ))
        with pytest.raises(ApiError) as rejected:
            await relay._request(route, "POST", "/chat/completions", {})
        assert rejected.value.status_code == 429
        assert rejected.value.message == "rate limited"
        assert rejected.value.details["upstreamRequestId"] == "up-429"

        relay.transport = httpx.MockTransport(lambda _: httpx.Response(200, text="not-json"))
        with pytest.raises(ApiError) as invalid:
            await relay._request(route, "GET", "/models")
        assert invalid.value.code == "provider_response_invalid"

        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        relay.transport = httpx.MockTransport(unreachable)
        with pytest.raises(ApiError) as offline:
            await relay._request(route, "GET", "/models")
        assert offline.value.code == "provider_unreachable"


@pytest.mark.asyncio
async def test_channel_test_success_and_failure_persist_result(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        create_project(client, "test-channel")
        relay = client.app.state.provider_relay
        channel = relay.create_channel(
            project_name="test-channel", name="mini", provider="minimax", config={},
            secret="minimax-secret-abcdefgh", actor_id="owner"
        )
        paths: list[str] = []

        def success(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"data": []})

        relay.transport = httpx.MockTransport(success)
        assert (await relay.test_channel(channel["id"]))["status"] == "success"
        assert paths == ["/v1/models"]
        relay.transport = httpx.MockTransport(lambda _: httpx.Response(401, json={"message": "invalid key"}))
        failed = await relay.test_channel(channel["id"])
        assert failed["status"] == "failed" and failed["message"] == "invalid key"
        assert relay.get_channel(channel["id"])["lastTestStatus"] == "failed"
        with pytest.raises(ApiError) as missing:
            await relay.test_channel("missing")
        assert missing.value.code == "provider_channel_not_found"


def test_public_parameter_validation_and_openai_error_contract(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client, provider="volcengine_ark", alias="glm-5.2", upstream_model="ep-glm"
        )
        headers = {"Authorization": f"Bearer {secret}"}
        cases = [
            ("/v1/chat/completions", {"messages": []}, "model_required"),
            ("/v1/chat/completions", {"model": "glm-5.2", "messages": [], "provider": "openai"}, "route_override_forbidden"),
            ("/v1/chat/completions", {"model": "glm-5.2", "messages": [], "unknown": 1}, "text_parameter_unsupported"),
            ("/v1/chat/completions", {"model": "glm-5.2", "messages": [], "stream": "yes"}, "stream_parameter_invalid"),
        ]
        for path, payload, code in cases:
            response = client.post(path, headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code
            assert response.json()["request_id"] == response.headers["x-request-id"]

        non_object = client.post("/v1/chat/completions", headers=headers, json=[])
        assert non_object.status_code == 422
        assert non_object.json()["error"]["code"] == "invalid_request_parameter"

    with relay_client(tmp_path / "images") as client:
        _, secret, _ = provision(
            client, provider="openai", alias="image2.0", upstream_model="gpt-image-real"
        )
        headers = {"Authorization": f"Bearer {secret}"}
        images = [
            ({"model": "image2.0", "prompt": "x", "unknown": 1}, "image_parameter_unsupported"),
            ({"model": "image2.0", "prompt": ""}, "image_prompt_invalid"),
            ({"model": "image2.0", "prompt": "x", "n": 0}, "image_count_invalid"),
            ({"model": "image2.0", "prompt": "x", "response_format": "raw"}, "image_response_format_invalid"),
        ]
        for payload, code in images:
            response = client.post("/v1/images/generations", headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code
        too_long = client.post(
            "/v1/images/generations",
            headers={**headers, "Idempotency-Key": "x" * 129},
            json={"model": "image2.0", "prompt": "x"},
        )
        assert too_long.json()["error"]["code"] == "idempotency_key_invalid"


def test_image_failure_in_progress_failed_replay_and_modality(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, secret, _ = provision(
            client, provider="openai", alias="image2.0", upstream_model="gpt-image-real"
        )
        relay = client.app.state.provider_relay
        headers = {"Authorization": f"Bearer {secret}", "Idempotency-Key": "failed-image"}
        relay.transport = httpx.MockTransport(lambda _: httpx.Response(500, json={"message": "image failed"}))
        failed = client.post(
            "/v1/images/generations", headers=headers,
            json={"model": "image2.0", "prompt": "x"},
        )
        replay = client.post(
            "/v1/images/generations", headers=headers,
            json={"model": "image2.0", "prompt": "x"},
        )
        assert failed.status_code == 500
        assert replay.status_code == 409 and replay.json()["error"]["code"] == "idempotency_request_failed"

        route = relay.resolve(ApiPrincipal(key_id, "relay_project"), "image2.0")
        relay._create_task(
            ApiPrincipal(key_id, "relay_project"), route, "image",
            {"model": "image2.0", "prompt": "pending"}, "pending-image"
        )
        pending = client.post(
            "/v1/images/generations",
            headers={"Authorization": f"Bearer {secret}", "Idempotency-Key": "pending-image"},
            json={"model": "image2.0", "prompt": "pending"},
        )
        assert pending.json()["error"]["code"] == "idempotency_request_in_progress"

        mismatch = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "image2.0", "messages": []},
        )
        assert mismatch.json()["error"]["code"] == "model_modality_mismatch"


def test_video_validation_and_task_access_boundaries(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, secret, _ = provision(
            client, provider="minimax", alias="minimax-h3", upstream_model="MiniMax-H3"
        )
        _, second_secret = create_key(client, "relay_project", "other-key")
        headers = {"Authorization": f"Bearer {secret}"}
        invalid_cases = [
            ({"model": "minimax-h3"}, "video_input_required"),
            ({"model": "minimax-h3", "prompt": "x", "metadata": {"audio": True}}, "video_metadata_forbidden"),
            ({"model": "minimax-h3", "prompt": "x", "width": 1920}, "video_parameter_unsupported"),
            ({"model": "minimax-h3", "metadata": {"content": []}}, "video_input_required"),
            ({"model": "minimax-h3", "metadata": {"content": [{"type": "audio"}]}}, "video_content_invalid"),
            ({"model": "minimax-h3", "metadata": {"content": [{"type": "text", "text": "x", "extra": 1}]}}, "video_content_invalid"),
            ({"model": "minimax-h3", "metadata": {"content": [{"type": "image_url", "image_url": {"url": "file:///x"}}]}}, "video_content_invalid"),
        ]
        for payload, code in invalid_cases:
            response = client.post("/v1/videos", headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code

        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda request: httpx.Response(
            200,
            json={"task_id": "mini-ok"} if request.method == "POST" else {
                "task": {"status": "running", "resolution": "768P", "ratio": "16:9"}
            },
        ))
        created = client.post(
            "/v1/videos", headers=headers,
            json={"model": "minimax-h3", "prompt": "x"},
        )
        task_id = created.json()["id"]
        forbidden = client.get(
            f"/v1/videos/{task_id}", headers={"Authorization": f"Bearer {second_secret}"}
        )
        content = client.get(f"/v1/videos/{task_id}/content", headers=headers)
        running = client.get(f"/v1/videos/{task_id}", headers=headers)
        assert forbidden.status_code == 404
        assert content.status_code == 409
        assert running.json()["status"] == "running"
        assert error_code(lambda: relay.get_local_task(ApiPrincipal(key_id, "relay_project"), "missing")) == "video_task_not_found"


def test_aliyun_validation_usage_filters_and_management_routes(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(
            client,
            provider="aliyun_bailian",
            alias="wan3.0-video",
            upstream_model="wan-real",
            config={"workspaceId": "workspace", "region": "cn-beijing"},
        )
        headers = {"Authorization": f"Bearer {secret}"}
        invalid_seed = client.post(
            "/v1/videos", headers=headers,
            json={"model": "wan3.0-video", "prompt": "x", "seed": 1},
        )
        assert invalid_seed.json()["error"]["code"] == "video_parameter_unsupported"
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda request: httpx.Response(
            200,
            json={"output": {"task_id": "ali-failed"}} if request.method == "POST" else {
                "output": {"task_status": "FAILED", "message": "generation failed"}
            },
        ))
        created = client.post(
            "/v1/videos", headers=headers,
            json={"model": "wan3.0-video", "prompt": "x", "metadata": {"aigc_watermark": True}},
        )
        failed = client.get(f"/v1/videos/{created.json()['id']}", headers=headers)
        assert failed.json()["status"] == "failed"
        assert failed.json()["error"]["message"] == "generation failed"

        catalog = client.get("/api/internal/model/catalog", headers=ADMIN_HEADERS)
        project_models = client.get("/api/internal/project/relay_project/models", headers=ADMIN_HEADERS)
        legacy_key_models = client.get(f"/api/internal/apikey/{key_id}/models", headers=ADMIN_HEADERS)
        usage = client.get(
            "/api/internal/inference/usage?projectName=relay_project&keyId="
            f"{key_id}&model=wan3.0-video&provider=aliyun_bailian&start=2020&end=2030",
            headers=ADMIN_HEADERS,
        )
        tasks = client.get(
            f"/api/internal/inference/tasks?projectName=relay_project&keyId={key_id}&model=wan3.0-video",
            headers=ADMIN_HEADERS,
        )
        saved_project = client.put(
            "/api/internal/project/relay_project/models",
            headers=ADMIN_HEADERS,
            json={"bindings": [{"model": "wan3.0-video", "channelId": channel["id"], "enabled": True}]},
        )

    assert all(item.status_code == 200 for item in [catalog, project_models, usage, tasks, saved_project])
    assert legacy_key_models.status_code == 404
    assert any(item["id"] == "wan3.0-video" for item in catalog.json()["models"])
    assert next(item for item in catalog.json()["models"] if item["id"] == "wan3.0-video")["upstreamModel"] == "wan3.0-video"
    assert next(item for item in saved_project.json()["models"] if item["model"] == "wan3.0-video")["upstreamModel"] == "wan3.0-video"
    assert tasks.json()["tasks"][0]["status"] == "failed"


def test_super_admin_provider_management_routes_cover_full_lifecycle(tmp_path: Path) -> None:
    initial_password = "Initial-provider-security!2026"
    password = "Changed-provider-security!2026"
    with relay_client(tmp_path) as client:
        client.app.state.database.create_project("super-project", "Super Project", "")
        client.app.state.admin_auth.create_initial_super_admin(
            "provider-security", "Provider Security", password=initial_password
        )
        login = client.post(
            "/api/internal/auth/login",
            json={"username": "provider-security", "password": initial_password},
        ).json()
        assert client.post(
            "/api/internal/auth/change-password",
            headers={"X-CSRF-Token": login["csrfToken"]},
            json={"currentPassword": initial_password, "newPassword": password},
        ).status_code == 200
        login = client.post(
            "/api/internal/auth/login",
            json={"username": "provider-security", "password": password},
        ).json()
        setup = client.post(
            "/api/internal/auth/totp/setup", headers={"X-CSRF-Token": login["csrfToken"]}
        ).json()
        now = int(time.time())
        auth = client.app.state.admin_auth
        auth.clock = lambda: now
        assert client.post(
            "/api/internal/auth/totp/confirm",
            headers={"X-CSRF-Token": login["csrfToken"]},
            json={"code": pyotp.TOTP(setup["secret"]).at(now)},
        ).status_code == 200
        csrf = {"X-CSRF-Token": login["csrfToken"], "User-Agent": "provider-test-agent"}

        projects = client.get("/api/internal/provider/projects")
        channels = client.get("/api/internal/provider/channels")
        assert projects.json()["projects"] == [{"name": "super-project", "displayName": "Super Project"}]
        assert channels.json()["channels"] == []

        auth.clock = lambda: now + 30
        created = client.post(
            "/api/internal/provider/channels",
            headers=csrf,
            json={
                "projectName": "super-project",
                "name": "temporary-openai",
                "provider": "openai",
                "config": {},
                "secret": "openai-temporary-abcdefgh",
                "currentPassword": password,
                "totpCode": pyotp.TOTP(setup["secret"]).at(now + 30),
            },
        )
        assert created.status_code == 201, created.text
        channel_id = created.json()["channel"]["id"]

        client.app.state.provider_relay.transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": []})
        )
        tested = client.post(f"/api/internal/provider/channels/{channel_id}/test", headers=csrf)
        assert tested.json()["test"]["status"] == "success"

        auth.clock = lambda: now + 60
        rotated = client.post(
            f"/api/internal/provider/channels/{channel_id}/rotate-key",
            headers=csrf,
            json={
                "secret": "openai-rotated-abcdefgh",
                "currentPassword": password,
                "totpCode": pyotp.TOTP(setup["secret"]).at(now + 60),
            },
        )
        assert rotated.json()["channel"]["secretHint"].endswith("efgh")

        auth.clock = lambda: now + 90
        disabled = client.put(
            f"/api/internal/provider/channels/{channel_id}/status",
            headers=csrf,
            json={
                "enabled": False,
                "currentPassword": password,
                "totpCode": pyotp.TOTP(setup["secret"]).at(now + 90),
            },
        )
        assert disabled.json()["channel"]["status"] == "disabled"

        auth.clock = lambda: now + 120
        deleted = client.request(
            "DELETE",
            f"/api/internal/provider/channels/{channel_id}",
            headers=csrf,
            json={
                "currentPassword": password,
                "totpCode": pyotp.TOTP(setup["secret"]).at(now + 120),
            },
        )
        assert deleted.json() == {"deleted": True, "channelId": channel_id}
        with client.app.state.database.connect() as connection:
            actions = [row[0] for row in connection.execute(
                "SELECT action FROM admin_audit_logs WHERE action LIKE 'provider.channel.%' ORDER BY id"
            )]
        assert actions == [
            "provider.channel.create", "provider.channel.test", "provider.channel.rotate",
            "provider.channel.status", "provider.channel.delete",
        ]
