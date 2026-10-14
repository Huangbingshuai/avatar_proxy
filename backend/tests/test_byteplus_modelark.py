"""BytePlus integration tests use only temporary databases and MockTransport."""

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.billing import current_month
from app.database import Database, SCHEMA
from app.errors import ApiError
from app.official_rates import (
    BYTEPLUS_RATE_EFFECTIVE_MONTH,
    BYTEPLUS_RATE_SOURCE_URL,
    BYTEPLUS_RATE_VERSION,
    USD_CNY_FX,
)
from app.provider_relay import ProviderRelay
from app.schemas import AdminProviderChannelCreate
from app.security import ApiPrincipal
from conftest import ADMIN_HEADERS, build_settings, create_key, create_project
from test_billing import SUPER_ACTOR
from test_provider_relay import provision, relay_client


TASKS = "/api/v3/contents/generations/tasks"
MODELS = [
    ("dreamina-seedance-2.5", "dreamina-seedance-2-5-260628"),
    ("dreamina-seedance-2.0", "dreamina-seedance-2-0-260128"),
    ("dreamina-seedance-2.0-fast", "dreamina-seedance-2-0-fast-260128"),
    ("dreamina-seedance-2.0-mini", "dreamina-seedance-2-0-mini-260615"),
]
IMAGE_MODELS = [
    ("dola-seedream-5.0-pro", "dola-seedream-5-0-pro-260628"),
    ("dola-seedream-5.0-flash", "dola-seedream-5-0-flash-260915"),
    ("dola-seedream-5.0-lite", "seedream-5-0-lite-260128"),
]


@pytest.mark.parametrize(("alias", "upstream"), IMAGE_MODELS)
def test_byteplus_image_generation_editing_idempotency_and_billing(tmp_path: Path, alias: str, upstream: str) -> None:
    requests: list[httpx.Request] = []
    lite = alias.endswith("lite")
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
        assert request.headers["authorization"] == "Bearer secret-byteplus_modelark-abcdefgh"
        payload = json.loads(request.content)
        assert payload["model"] == upstream
        assert "n" not in payload
        assert payload["image"] == ["https://example.com/ref1.png", "https://example.com/ref2.png"]
        assert payload["stream"] is False
        assert payload["size"] == "2K" and payload["output_format"] == "png"
        if lite:
            assert payload["sequential_image_generation"] == "auto"
            assert payload["sequential_image_generation_options"] == {"max_images": 2}
        else:
            assert "sequential_image_generation" not in payload
        data = [{"url": "https://example.com/image1.png", "size": "2048x2048"}]
        if lite:
            data.extend([{"url": "https://example.com/image2.png", "size": "2048x2048"}, {"error": {"code": "moderation", "message": "blocked"}}])
        return httpx.Response(200, json={"model": upstream, "data": data}, headers={"x-request-id": "global-image-request"})

    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(client, provider="byteplus_modelark", alias=alias, upstream_model="ignored")
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}", "Idempotency-Key": "global-image"}
        payload = {
            "model": alias, "prompt": "Draw an ocean sunrise", "n": 2 if lite else 1,
            "image": ["https://example.com/ref1.png", "https://example.com/ref2.png"],
            "output_format": "png", "watermark": False,
        }
        response = client.post("/v1/images/generations", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["model"] == alias
        assert client.post("/v1/images/generations", headers=headers, json=payload).json() == response.json()
        assert client.post("/v1/images/generations", headers=headers, json={**payload, "prompt": "Different"}).status_code == 409
        with client.app.state.database.connect() as connection:
            row = connection.execute(
                "SELECT u.*,m.modality,m.provider,t.metadata_json,t.billing_metadata_json FROM inference_usage u "
                "JOIN model_catalog m ON m.alias=u.model_alias JOIN inference_tasks t ON t.id=u.task_id"
            ).fetchone()
        assert row["api_key_id"] == key_id
        assert row["generated_images"] == (2 if lite else 1)
        assert row["input_tokens"] is row["output_tokens"] is row["total_tokens"] is None
        rate = client.app.state.billing.get_rate(alias, current_month())
        assert rate["configured"]
        assert rate["officialSource"]["url"] == BYTEPLUS_RATE_SOURCE_URL
        measurements, reason = client.app.state.billing._relay_measurements(dict(row))
        assert reason is None
        assert [(metric, dimension, str(quantity)) for metric, dimension, quantity in measurements] == (
            [("image", "output:gt2610000", "1"), ("image", "input:after_first", "1")]
            if alias.endswith("pro") else [("image", "", "2" if lite else "1")]
        )
        overseas = [item for item in relay.catalog() if item["provider"] == "byteplus_modelark"]
        assert {item["id"] for item in overseas} == {item[0] for item in MODELS + IMAGE_MODELS}
    assert len(requests) == 1


@pytest.mark.parametrize(("alias", "extra", "code"), [
    ("dola-seedream-5.0-pro", {"n": 2}, "image_count_unsupported"),
    ("dola-seedream-5.0-flash", {"sequential_image_generation": "auto"}, "image_sequence_unsupported"),
    ("dola-seedream-5.0-pro", {"size": "4K"}, "image_size_invalid"),
    ("dola-seedream-5.0-lite", {"size": "1K"}, "image_size_invalid"),
    ("dola-seedream-5.0-pro", {"size": "512x512"}, "image_size_invalid"),
    ("dola-seedream-5.0-flash", {"output_format": "webp"}, "image_output_format_unsupported"),
    ("dola-seedream-5.0-lite", {"optimize_prompt_options": {"mode": "fast"}}, "image_parameter_unsupported"),
    ("dola-seedream-5.0-pro", {"quality": "high"}, "image_parameter_unsupported"),
    ("dola-seedream-5.0-pro", {"stream": True}, "image_stream_unsupported"),
    ("dola-seedream-5.0-lite", {"image": ["https://example.com/ref.png"] * 14, "n": 2}, "image_input_count_invalid"),
    ("dola-seedream-5.0-lite", {"sequential_image_generation_options": {"max_images": 0}}, "image_count_unsupported"),
    ("dola-seedream-5.0-pro", {"watermark": "yes"}, "image_parameter_unsupported"),
])
def test_byteplus_image_capability_rejections(tmp_path: Path, alias: str, extra: dict, code: str) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias=alias, upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda _: pytest.fail("Invalid request reached upstream"))
        response = client.post("/v1/images/generations", headers={"Authorization": f"Bearer {secret}"}, json={"model": alias, "prompt": "Ocean sunrise", **extra})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == code


def test_byteplus_empty_image_response_does_not_create_zero_usage(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias=IMAGE_MODELS[0][0], upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))
        response = client.post("/v1/images/generations", headers={"Authorization": f"Bearer {secret}"}, json={"model": IMAGE_MODELS[0][0], "prompt": "Ocean sunrise"})
        assert response.status_code == 502
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT status FROM inference_tasks").fetchone()[0] == "failed"
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0


def test_current_schema_upgrade_preserves_channels_credentials_and_history(tmp_path: Path) -> None:
    path = tmp_path / "existing.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA.replace("'byteplus_modelark',", ""))
    database = Database(path)
    database.create_project("existing", "Existing", "")
    database.create_api_key("old-key", "Existing key", "test", "test-hash", "existing")
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO model_catalog(alias,display_name,provider,modality,protocol,upstream_model) "
            "VALUES ('existing-video','Existing video','volcengine_ark','video','async_video','old-model')"
        )
    relay = ProviderRelay(build_settings(path, multi_provider_enabled=True), database)
    channel = relay.create_channel(
        project_name="existing", name="Existing", provider="volcengine_ark",
        config={}, secret="existing-provider-secret", actor_id="owner",
    )
    relay.set_project_models("existing", [{"model": "existing-video", "channelId": channel["id"]}], "owner")
    principal = ApiPrincipal("old-key", "existing")
    route = relay.resolve(principal, "existing-video")
    task, _ = relay._create_task(principal, route, "video", {"prompt": "old"}, "old-idempotency")
    relay._record_usage(request_id="old-usage", principal=principal, route=route, status="succeeded", task_id=task["id"], usage={"completion_tokens": 7})
    tables = ("provider_channels", "provider_credentials", "project_model_bindings", "inference_tasks", "inference_usage", "api_keys", "projects")
    with database.connect() as connection:
        snapshots = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")] for table in tables}

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        for table, expected in snapshots.items():
            assert [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")] == expected
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM project_model_bindings WHERE model_alias LIKE 'dreamina-%'").fetchone()[0] == 0
    new = relay.create_channel(
        project_name="existing", name="Global", provider="byteplus_modelark",
        config={}, secret="byteplus-test-secret", actor_id="owner",
    )
    assert new["provider"] == "byteplus_modelark"
    assert new["config"] == {}


@pytest.mark.parametrize(("alias", "upstream"), MODELS)
def test_byteplus_submit_query_rotation_idempotency_and_usage(tmp_path: Path, alias: str, upstream: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "ark.ap-southeast.bytepluses.com"
        assert request.headers["authorization"] == "Bearer secret-byteplus_modelark-abcdefgh"
        assert "projectname" not in request.headers
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload == {
                "model": upstream, "duration": 5, "resolution": "720p", "ratio": "16:9",
                "generate_audio": True,
                "content": [{"type": "text", "text": "An ocean sunrise"}],
            }
            return httpx.Response(200, json={"id": "cgt-byteplus"}, headers={"x-request-id": "byteplus-create"})
        assert request.method == "GET"
        assert request.url.path == TASKS + "/cgt-byteplus"
        return httpx.Response(200, json={
            "id": "cgt-byteplus", "status": "succeeded", "model": upstream,
            "content": {"video_url": "https://video.example.com/global.mp4"},
            "duration": 5, "resolution": "720p",
            "usage": {"completion_tokens": 1000, "total_tokens": 1000},
        }, headers={"x-request-id": "byteplus-query"})

    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(client, provider="byteplus_modelark", alias=alias, upstream_model="ignored")
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}", "Idempotency-Key": "global-create"}
        listed = client.get("/v1/models", headers=headers).json()["data"]
        assert [model["id"] for model in listed] == [alias]
        assert listed[0]["capabilities"]["billingMetric"] == "output_tokens"
        payload = {
            "model": alias, "duration": 5, "resolution": "720p", "ratio": "16:9", "generate_audio": True,
            "content": [{"type": "text", "text": "An ocean sunrise"}],
        }
        created = client.post(TASKS, headers=headers, json=payload)
        assert created.status_code == 200, created.text
        assert client.post(TASKS, headers=headers, json=payload).json() == created.json()
        conflict = client.post(TASKS, headers=headers, json={**payload, "duration": 6})
        assert conflict.status_code == 409
        _, other_secret = create_key(client, "relay_project", "other-key")
        task_url = f"{TASKS}/{created.json()['id']}"
        assert client.get(task_url, headers={"Authorization": f"Bearer {other_secret}"}).status_code == 404
        relay.rotate_channel_secret(channel["id"], "rotated-byteplus-secret", "owner")
        relay.set_channel_status(channel["id"], False)
        assert client.get("/v1/models", headers=headers).json()["data"] == []
        finished = client.get(task_url, headers=headers)
        assert finished.status_code == 200, finished.text
        assert finished.json()["model"] == alias
        assert finished.json()["content"]["video_url"].endswith("global.mp4")
        assert finished.json()["usage"]["completion_tokens"] == 1000
        assert client.get(task_url, headers=headers).json() == finished.json()
        usage = client.get("/api/internal/inference/usage?provider=byteplus_modelark", headers=ADMIN_HEADERS)
        assert usage.status_code == 200
        assert len(usage.json()["usage"]) == 1
        assert usage.json()["usage"][0]["apiKeyId"] == key_id
        with client.app.state.database.connect() as connection:
            row = connection.execute("SELECT output_tokens,total_tokens,input_tokens,video_seconds FROM inference_usage").fetchone()
            assert tuple(row) == (1000, 1000, None, 5.0)
            logs = connection.execute("SELECT request_params_json,response_summary_json FROM request_logs WHERE is_model_call=1 AND success=1").fetchall()
            assert any(json.loads(row["request_params_json"])["body"]["model"] == alias for row in logs)
    assert [call.method for call in calls] == ["POST", "GET"]


def test_byteplus_channel_validation_project_boundary_and_free_probe(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, _, channel = provision(client, provider="byteplus_modelark", alias=MODELS[0][0], upstream_model="ignored")
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda _: pytest.fail("Channel test must not create paid tasks"))
        assert asyncio.run(relay.test_channel(channel["id"]))["status"] == "manual"
        assert relay.get_channel(channel["id"])["lastTestStatus"] == "manual"
        for config in ({"baseUrl": "https://evil.example"}, {"region": "eu-west-1"}, {"projectName": "domestic"}):
            with pytest.raises(ApiError) as rejected:
                relay._validate_provider_config("byteplus_modelark", config)
            assert rejected.value.code == "provider_config_field_forbidden"
        create_project(client, "other_project")
        with pytest.raises(ApiError) as cross_project:
            relay.set_project_models("other_project", [{"model": MODELS[0][0], "channelId": channel["id"]}], "admin")
        assert cross_project.value.code == "cross_project_channel_forbidden"
        with pytest.raises(ApiError) as mismatch:
            relay.set_project_models("relay_project", [{"model": "doubao-seedance-2.5", "channelId": channel["id"]}], "admin")
        assert mismatch.value.code == "model_provider_mismatch"
        with client.app.state.database.connect() as connection:
            dump = " ".join(connection.iterdump())
        assert "secret-byteplus_modelark-abcdefgh" not in dump
        model = AdminProviderChannelCreate.model_validate({
            "projectName": "relay_project", "name": "Global", "provider": "byteplus_modelark",
            "secret": "global-secret", "currentPassword": "test-password", "totpCode": "123456",
        })
        assert model.provider == "byteplus_modelark"
        denied = client.post("/api/internal/provider/channels", headers=ADMIN_HEADERS, json=model.model_dump(by_alias=True))
        assert denied.status_code == 403


@pytest.mark.parametrize(("extra", "code"), [
    ({"duration": 31}, "video_duration_invalid"),
    ({"duration": 3}, "video_duration_invalid"),
    ({"resolution": "4k"}, "video_resolution_invalid"),
    ({"service_tier": "flex"}, "video_service_tier_invalid"),
    ({"seed": 1}, "video_seed_unsupported"),
    ({"camera_fixed": True}, "video_camera_unsupported"),
    ({"draft": True}, "video_draft_unsupported"),
    ({"output_format": "avi"}, "video_output_format_invalid"),
    ({"base_url": "https://evil.example"}, "route_override_forbidden"),
    ({"content": [{"type": "image_url", "image_url": {"url": "https://example.com/image.png"}, "role": "last_frame"}]}, "video_content_invalid"),
    ({"content": [{"type": "image_url", "image_url": {"url": "https://example.com/a.png"}, "role": "first_frame"}, {"type": "video_url", "video_url": {"url": "https://example.com/video.mp4"}, "role": "reference_video"}]}, "video_content_invalid"),
])
def test_byteplus_rejects_unsupported_requests_before_upstream(tmp_path: Path, extra: dict, code: str) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias=MODELS[0][0], upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda _: pytest.fail("Invalid request reached upstream"))
        response = client.post(TASKS, headers={"Authorization": f"Bearer {secret}"}, json={
            "model": MODELS[0][0], "content": [{"type": "text", "text": "Hello"}], **extra,
        })
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == code


def test_byteplus_multimodal_mov_and_cancel(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    content = [
        {"type": "text", "text": "Ocean at sunrise"},
        {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}, "role": "reference_image"},
        {"type": "video_url", "video_url": {"url": "https://example.com/video.mp4"}, "role": "reference_video"},
        {"type": "audio_url", "audio_url": {"url": "https://example.com/audio.mp3"}, "role": "reference_audio"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content)["content"] == content
            return httpx.Response(200, json={"id": "cgt-global"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={
            "status": "succeeded", "duration": 5, "resolution": "1080p", "output_format": "mov",
            "content": {"video_url": "https://example.com/out.mov", "last_frame_url": "https://example.com/last.jpg"},
        })

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias=MODELS[0][0], upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        payload = {"model": MODELS[0][0], "content": content, "duration": -1, "output_format": "mov", "return_last_frame": True}
        created = client.post(TASKS, headers=headers, json=payload)
        assert created.status_code == 200
        task_url = f"{TASKS}/{created.json()['id']}"
        finished = client.get(task_url, headers=headers).json()
        assert finished["output_format"] == "mov"
        assert finished["content"]["last_frame_url"].endswith("last.jpg")
        with client.app.state.database.connect() as connection:
            usage = connection.execute("SELECT output_tokens,video_seconds FROM inference_usage").fetchone()
            assert tuple(usage) == (None, 5.0)
            assert connection.execute("SELECT result_format FROM inference_tasks").fetchone()[0] == "mov"
        second = client.post(TASKS, headers=headers, json=payload).json()["id"]
        assert client.delete(f"{TASKS}/{second}", headers=headers).status_code == 204
        assert client.get(f"{TASKS}/{second}", headers=headers).json()["status"] == "cancelled"
    assert [call.method for call in calls] == ["POST", "GET", "POST", "DELETE"]


def test_byteplus_20_capability_limits_are_enforced(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias="dreamina-seedance-2.0-mini", upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda _: pytest.fail("Invalid request reached upstream"))
        base = {"model": "dreamina-seedance-2.0-mini", "content": [{"type": "text", "text": "Hello"}]}
        image = {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}, "role": "reference_image"}
        cases = [
            ({"resolution": "1080p"}, "video_resolution_invalid"),
            ({"duration": 16}, "video_duration_invalid"),
            ({"return_last_frame": True}, "video_last_frame_unsupported"),
            ({"output_format": "mov"}, "video_output_format_invalid"),
            ({"content": [image] * 10}, "video_content_limit"),
            ({"content": [{"type": "audio_url", "audio_url": {"url": "https://example.com/a.mp3"}, "role": "reference_audio"}]}, "video_content_invalid"),
            ({"content": [{**image, "role": "first_frame"}] * 2}, "video_content_invalid"),
        ]
        for extra, code in cases:
            response = client.post(TASKS, headers={"Authorization": f"Bearer {secret}"}, json={**base, **extra})
            assert response.status_code == 422, response.text
            assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("failure", ["denied", "timeout", "missing_id"])
def test_byteplus_submission_failure_is_not_retried_or_billed(tmp_path: Path, failure: str) -> None:
    calls: list[httpx.Request] = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if failure == "denied":
            return httpx.Response(403, json={"error": {"message": "Model is not activated"}})
        return httpx.Response(200, json={})
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias=MODELS[0][0], upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        response = client.post(TASKS, headers={"Authorization": f"Bearer {secret}"}, json={"model": MODELS[0][0], "content": [{"type": "text", "text": "Hello"}]})
        assert response.status_code == (403 if failure == "denied" else 502)
        assert "secret-byteplus_modelark-abcdefgh" not in response.text
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT status FROM inference_tasks").fetchone()[0] == "failed"
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0
    assert len(calls) == 1


@pytest.mark.parametrize("state", ["failed", "expired", "cancelled"])
def test_byteplus_terminal_failure_does_not_bill(tmp_path: Path, state: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "cgt-error"})
        return httpx.Response(200, json={"status": state, "usage": {"completion_tokens": 999}})
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(client, provider="byteplus_modelark", alias=MODELS[0][0], upstream_model="ignored")
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        created = client.post(TASKS, headers=headers, json={"model": MODELS[0][0], "content": [{"type": "text", "text": "Hello"}]}).json()
        response = client.get(f"{TASKS}/{created['id']}", headers=headers)
        assert response.json()["status"] == ("failed" if state == "expired" else state)
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0


def test_byteplus_token_billing_has_independent_prices_and_pending_unknown_usage(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(client, provider="byteplus_modelark", alias=MODELS[0][0], upstream_model="ignored")
        billing = client.app.state.billing
        month = current_month()
        # Overseas models ship with a bundled price card, so drop it to observe
        # the genuinely unconfigured state this scenario is about.
        with client.app.state.database.connect() as connection:
            connection.execute("DELETE FROM billing_model_rates WHERE model_alias=?", (MODELS[0][0],))
        rate = billing.get_rate(MODELS[0][0], month)
        assert not rate["configured"] and rate["officialSource"] == {
            "version": BYTEPLUS_RATE_VERSION,
            "url": BYTEPLUS_RATE_SOURCE_URL,
            "currency": "USD",
            "fxRateToCny": str(USD_CNY_FX),
        }
        assert len(rate["editableRules"]) == 6
        assert all(rule["metric"] == "output_tokens" and rule["unitPriceYuan"] is None for rule in rate["editableRules"])
        billing.set_project_terms("relay_project", month, True, 8000, SUPER_ACTOR)
        relay = client.app.state.provider_relay
        principal = ApiPrincipal(key_id, "relay_project")
        route = relay.resolve(principal, MODELS[0][0])
        for suffix, with_video in (("plain", False), ("video", True)):
            content = [{"type": "video_url"}] if with_video else []
            task, _ = relay._create_task(principal, route, "video", {"metadata": {"resolution": "720p", "content": content}}, suffix)
            with client.app.state.database.connect() as connection:
                connection.execute("UPDATE inference_tasks SET status='succeeded' WHERE id=?", (task["id"],))
            relay._record_usage(request_id=suffix, task_id=task["id"], principal=principal, route=route, status="succeeded", usage={"completion_tokens": 1000000})
        asyncio.run(billing.reconcile())
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM billing_usage_items WHERE status='pending'").fetchone()[0] == 2
        billing.set_rate(MODELS[0][0], month, {"rules": [
            {"metric": "output_tokens", "dimension": "720p:no_video", "unitSize": 1000000, "unitPriceYuan": "10.00"},
            {"metric": "output_tokens", "dimension": "720p:video", "unitSize": 1000000, "unitPriceYuan": "6.00"},
        ]}, SUPER_ACTOR)
        asyncio.run(billing.reconcile())
        with client.app.state.database.connect() as connection:
            rows = connection.execute("SELECT metric,resolution,quantity,list_amount_micros,net_amount_micros FROM billing_usage_components ORDER BY resolution").fetchall()
            assert [tuple(row) for row in rows] == [
                ("output_tokens", "720p:no_video", "1000000", 10000000, 8000000),
                ("output_tokens", "720p:video", "1000000", 6000000, 4800000),
            ]
        pricing = client.get("/v1/pricing?model=dreamina-seedance-2.5", headers={"Authorization": f"Bearer {secret}"}).json()
        assert pricing["currency"] == "CNY"
        assert len(pricing["data"]) == 1 and pricing["data"][0]["configured"]
        measurements, reason = billing._relay_measurements({
            "provider": "byteplus_modelark", "modality": "video", "model_alias": MODELS[0][0],
            "output_tokens": None, "video_seconds": 5,
        })
        assert measurements is None and reason == "usage_unknown"
