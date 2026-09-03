import json
import time
from pathlib import Path

import httpx
import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import create_app
from app.security import ApiPrincipal
from conftest import ADMIN_HEADERS, build_settings, create_key, create_project


def relay_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings = build_settings(
        tmp_path / "relay.db",
        multi_provider_enabled=True,
        provider_credential_encryption_key=Fernet.generate_key().decode("ascii"),
        **overrides,
    )
    return TestClient(create_app(settings))


def provision(
    client: TestClient,
    *,
    provider: str,
    alias: str,
    upstream_model: str,
    config: dict | None = None,
    project_name: str = "relay_project",
    key_name: str = "relay-key",
) -> tuple[str, str, dict]:
    create_project(client, project_name)
    key_id, secret = create_key(client, project_name, key_name)
    relay = client.app.state.provider_relay
    channel = relay.create_channel(
        project_name=project_name,
        name=f"{provider}-production",
        provider=provider,
        config=config or {},
        secret=f"secret-{provider}-abcdefgh",
        actor_id="super-admin",
    )
    relay.set_project_models(
        project_name,
        [
            {
                "model": alias,
                "channelId": channel["id"],
                "upstreamModel": upstream_model,
                "enabled": True,
            }
        ],
        "business-admin",
    )
    return key_id, secret, channel


def test_default_disabled_isolated_from_existing_api(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "disabled.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)

        existing = client.get("/api/auth/me", headers={"Authorization": f"Bearer {secret}"})
        disabled = client.get("/v1/models", headers={"Authorization": f"Bearer {secret}"})

    assert existing.status_code == 200
    assert disabled.status_code == 503
    assert disabled.json()["error"] == {
        "message": "多供应商模型中转尚未启用",
        "type": "upstream_error",
        "param": None,
        "code": "multi_provider_disabled",
    }
    assert disabled.json()["request_id"].startswith("req_")
    assert disabled.headers["x-request-id"] == disabled.json()["request_id"]


def test_credentials_are_encrypted_masked_and_cross_project_binding_is_rejected(tmp_path: Path) -> None:
    raw_secret = "ark-production-secret-123456"
    with relay_client(tmp_path) as client:
        create_project(client, "project_a")
        create_project(client, "project_b")
        relay = client.app.state.provider_relay
        channel = relay.create_channel(
            project_name="project_a",
            name="ark-a",
            provider="volcengine_ark",
            config={"projectName": "wrong-project-must-be-ignored"},
            secret=raw_secret,
            actor_id="owner",
        )
        with client.app.state.database.connect() as connection:
            stored = connection.execute(
                "SELECT secret_ciphertext,secret_hint FROM provider_credentials"
            ).fetchone()
            dump = " ".join(connection.iterdump())

        assert raw_secret not in stored["secret_ciphertext"]
        assert raw_secret not in dump
        assert channel["secretHint"] == "ark****3456"
        assert channel["config"] == {"projectName": "project_a"}
        assert "secret" not in channel

        with pytest.raises(ApiError) as error:
            relay.set_project_models(
                "project_b",
                [{"model": "glm-5.2", "channelId": channel["id"], "upstreamModel": "ignored-model"}],
                "admin",
            )
        assert error.value.code == "cross_project_channel_forbidden"


def test_project_model_access_and_channel_status_are_immediate_for_all_keys(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, channel = provision(
            client,
            provider="volcengine_ark",
            alias="glm-5.2",
            upstream_model="must-be-ignored",
        )
        _, second_secret = create_key(client, "relay_project", "second-key")
        headers = {"Authorization": f"Bearer {secret}"}
        second_headers = {"Authorization": f"Bearer {second_secret}"}

        listed = client.get("/v1/models", headers=headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["data"]] == ["glm-5.2"]
        assert client.get("/v1/models", headers=second_headers).json()["data"] == listed.json()["data"]
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM api_key_model_permissions").fetchone()[0] == 0

        client.app.state.provider_relay.set_project_models("relay_project", [], "admin")
        assert client.get("/v1/models", headers=headers).json()["data"] == []
        assert client.get("/v1/models", headers=second_headers).json()["data"] == []
        denied = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "glm-5.2", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "model_not_allowed"

        client.app.state.provider_relay.set_project_models(
            "relay_project",
            [{"model": "glm-5.2", "channelId": channel["id"], "enabled": True}],
            "admin",
        )
        assert [item["id"] for item in client.get("/v1/models", headers=second_headers).json()["data"]] == ["glm-5.2"]
        client.app.state.provider_relay.set_channel_status(channel["id"], False)
        assert client.get("/v1/models", headers=headers).json()["data"] == []


def test_chat_and_responses_rewrite_model_and_record_only_real_usage(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                headers={"x-request-id": "ark-chat-request"},
                json={
                    "id": "chatcmpl-upstream",
                    "model": payload["model"],
                    "choices": [],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
                },
            )
        return httpx.Response(
            200,
            headers={"x-request-id": "ark-response-request"},
            json={"id": "resp-upstream", "model": payload["model"], "output": []},
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias="deepseek-v4-flash",
            upstream_model="ep-deepseek-v4-flash",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}

        chat = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]},
        )
        response = client.post(
            "/v1/responses",
            headers=headers,
            json={"model": "deepseek-v4-flash", "input": "hello"},
        )

        assert chat.status_code == response.status_code == 200
        assert chat.json()["model"] == response.json()["model"] == "deepseek-v4-flash"
        assert all(json.loads(item.content)["model"] == "deepseek-v4-flash-260425" for item in requests)
        with client.app.state.database.connect() as connection:
            usage = connection.execute(
                "SELECT request_id,input_tokens,output_tokens,total_tokens FROM inference_usage ORDER BY created_at"
            ).fetchall()
        assert [dict(item) for item in usage] == [
            {"request_id": "ark-chat-request", "input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
            {"request_id": "ark-response-request", "input_tokens": None, "output_tokens": None, "total_tokens": None},
        ]


def test_sse_rewrites_alias_and_does_not_invent_usage(tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        body = (
            'data: {"id":"stream-1","model":"ep-real","choices":[{"delta":{"content":"hi"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, headers={"x-request-id": "upstream-stream"}, content=body)

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias="glm-5.2",
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        result = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "glm-5.2", "messages": [], "stream": True},
        )
        with client.app.state.database.connect() as connection:
            usage = dict(connection.execute("SELECT * FROM inference_usage").fetchone())

    assert result.status_code == 200
    assert '"model":"glm-5.2"' in result.text
    assert usage["status"] == "unknown"
    assert usage["input_tokens"] is usage["output_tokens"] is usage["total_tokens"] is None


def test_image_idempotency_prevents_duplicates_and_conflicts(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url == httpx.URL("https://api.openai.com/v1/images/generations")
        assert request.headers["authorization"] == "Bearer secret-openai-abcdefgh"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-image-2"
        return httpx.Response(
            200,
            headers={"x-request-id": "openai-image-request"},
            json={"created": 1, "data": [{"url": "https://cdn.example.com/image.png"}]},
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="openai",
            alias="image2.0",
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}", "Idempotency-Key": "same-image"}
        first = client.post(
            "/v1/images/generations", headers=headers, json={"model": "image2.0", "prompt": "cat"}
        )
        second = client.post(
            "/v1/images/generations", headers=headers, json={"model": "image2.0", "prompt": "cat"}
        )
        conflict = client.post(
            "/v1/images/generations", headers=headers, json={"model": "image2.0", "prompt": "dog"}
        )
        with client.app.state.database.connect() as connection:
            task_count = connection.execute("SELECT COUNT(*) FROM inference_tasks").fetchone()[0]
            usage = connection.execute("SELECT generated_images FROM inference_usage").fetchone()[0]

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"
    assert calls == task_count == usage == 1


@pytest.mark.parametrize(
    ("alias", "upstream_model"),
    [
        ("doubao-seed-2.1-pro", "doubao-seed-2-1-pro-260628"),
        ("doubao-seed-2.1-turbo", "doubao-seed-2-1-turbo-260628"),
        ("doubao-seed-2.0-pro", "doubao-seed-2-0-pro-260215"),
        ("doubao-seed-2.0-lite", "doubao-seed-2-0-lite-260428"),
        ("doubao-seed-2.0-mini", "doubao-seed-2-0-mini-260215"),
    ],
)
def test_all_volcengine_vision_models_forward_multimodal_chat(
    tmp_path: Path, alias: str, upstream_model: str
) -> None:
    forwarded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        forwarded.append(payload)
        return httpx.Response(
            200,
            headers={"x-request-id": "ark-vision-request"},
            json={
                "id": "chatcmpl-vision",
                "model": payload["model"],
                "choices": [{"message": {"role": "assistant", "content": "一只猫"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24},
            },
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias=alias,
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "model": alias,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}},
                        {"type": "text", "text": "图片里有什么？"},
                    ],
                }],
            },
        )

    assert response.status_code == 200
    assert response.json()["model"] == alias
    assert forwarded[0]["model"] == upstream_model
    assert forwarded[0]["messages"][0]["content"][0]["type"] == "image_url"


def test_non_vision_text_model_rejects_image_input(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias="deepseek-v4-flash",
            upstream_model="ignored-model",
        )
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {secret}"},
            json={
                "model": "deepseek-v4-flash",
                "messages": [{
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": "https://example.com/a.png"}}],
                }],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "model_image_input_unsupported"


@pytest.mark.parametrize(
    ("alias", "upstream_model", "count", "sequential", "reference_image", "legacy_controls"),
    [
        ("seedream-5.0-pro", "doubao-seedream-5-0-pro-260628", 1, False, True, False),
        ("seedream-5.0-lite", "doubao-seedream-5-0-lite-260128", 15, True, True, False),
        ("seedream-5.0", "doubao-seedream-5-0-260128", 1, False, True, False),
        ("seedream-4.5", "doubao-seedream-4-5-251128", 2, True, True, False),
        ("seedream-4.0", "doubao-seedream-4-0-250828", 2, True, True, False),
    ],
)
def test_all_volcengine_image_models_translate_openai_image_requests(
    tmp_path: Path,
    alias: str,
    upstream_model: str,
    count: int,
    sequential: bool,
    reference_image: bool,
    legacy_controls: bool,
) -> None:
    forwarded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        forwarded.append(payload)
        return httpx.Response(
            200,
            headers={"x-request-id": "ark-image-request"},
            json={
                "model": payload["model"],
                "data": [{"url": f"https://example.com/{index}.png"} for index in range(count)],
                "usage": {"generated_images": count, "output_tokens": 100, "total_tokens": 100},
            },
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias=alias,
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        request_body = {
            "model": alias,
            "prompt": "将参考图改为水彩风格" if reference_image else "生成水彩风景",
            "n": count,
            "quality": "high",
            "response_format": "url",
        }
        if reference_image:
            request_body["image"] = "https://example.com/reference.png"
        if legacy_controls:
            request_body.update({"seed": 21, "guidance_scale": 5.5})
        response = client.post(
            "/v1/images/generations",
            headers={
                "Authorization": f"Bearer {secret}",
                "Idempotency-Key": f"image-{alias}",
            },
            json=request_body,
        )

    assert response.status_code == 200
    assert response.json()["model"] == alias
    assert forwarded[0]["model"] == upstream_model
    if reference_image:
        assert forwarded[0]["image"] == "https://example.com/reference.png"
    else:
        assert "image" not in forwarded[0]
    assert "n" not in forwarded[0]
    assert "quality" not in forwarded[0]
    assert forwarded[0]["stream"] is False
    if sequential:
        assert forwarded[0]["sequential_image_generation"] == "auto"
        assert forwarded[0]["sequential_image_generation_options"] == {"max_images": count}
    else:
        assert "sequential_image_generation" not in forwarded[0]
    if legacy_controls:
        assert forwarded[0]["seed"] == 21
        assert forwarded[0]["guidance_scale"] == 5.5

@pytest.mark.parametrize(
    ("alias", "upstream_model", "image"),
    [
        ("seedance-2.5", "doubao-seedance-2-5-260628", None),
        ("seedance-2.0", "doubao-seedance-2-0-260128", None),
        ("seedance-2.0-fast", "doubao-seedance-2-0-fast-260128", None),
        ("seedance-2.0-mini", "doubao-seedance-2-0-mini-260615", None),
        ("seedance-1.0-pro", "doubao-seedance-1-0-pro-250528", None),
        ("seedance-1.0-pro-fast", "doubao-seedance-1-0-pro-fast-251015", None),
    ],
)
def test_all_volcengine_video_models_submit_and_refresh(
    tmp_path: Path, alias: str, upstream_model: str, image: str | None
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "ark.cn-beijing.volces.com"
        assert request.headers["authorization"] == "Bearer secret-volcengine_ark-abcdefgh"
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["model"] == upstream_model
            assert payload["content"][0] == {"type": "text", "text": "sunrise over the sea"}
            if image:
                assert payload["content"][1] == {
                    "type": "image_url",
                    "image_url": {"url": image},
                    "role": "first_frame",
                }
            assert payload["duration"] == 5
            return httpx.Response(200, headers={"x-request-id": "ark-submit"}, json={"id": "cgt-test"})
        return httpx.Response(
            200,
            headers={"x-request-id": "ark-query"},
            json={
                "id": "cgt-test",
                "model": upstream_model,
                "status": "succeeded",
                "content": {"video_url": "https://video.example.com/seedance.mp4"},
                "duration": "5",
                "resolution": "720p",
                "ratio": "16:9",
                "usage": {"completion_tokens": 1200, "total_tokens": 1200},
            },
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias=alias,
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        payload: dict[str, object] = {
            "model": alias,
            "content": [{"type": "text", "text": "sunrise over the sea"}],
            "duration": 5,
        }
        if image:
            payload["content"].append({
                "type": "image_url",
                "image_url": {"url": image},
                "role": "first_frame",
            })
        created = client.post("/api/v3/contents/generations/tasks", headers=headers, json=payload)
        finished = client.get(
            f"/api/v3/contents/generations/tasks/{created.json()['id']}", headers=headers
        )

    assert created.status_code == 200
    assert set(created.json()) == {"id"}
    assert finished.status_code == 200
    assert finished.json()["status"] == "succeeded"
    assert finished.json()["model"] == alias
    assert finished.json()["content"]["video_url"] == "https://video.example.com/seedance.mp4"
    assert [request.url.path for request in requests] == [
        "/api/v3/contents/generations/tasks",
        "/api/v3/contents/generations/tasks/cgt-test",
    ]


def test_volcengine_video_advanced_payloads_are_filtered_and_forwarded(tmp_path: Path) -> None:
    submitted: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        submitted.append(payload)
        return httpx.Response(200, json={"id": f"cgt-{len(submitted)}"})

    with relay_client(tmp_path) as client:
        _, secret, channel = provision(
            client,
            provider="volcengine_ark",
            alias="seedance-2.5",
            upstream_model="ignored-model",
        )
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        pro_25 = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "seedance-2.5",
                "duration": 6,
                "seed": 42,
                "content": [
                    {"type": "text", "text": "cinematic sunrise"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "asset://asset-example"},
                        "role": "first_frame",
                    },
                ],
                "resolution": "1080p",
                "ratio": "16:9",
                "generate_audio": True,
                "watermark": False,
                "return_last_frame": True,
                "service_tier": "flex",
                "execution_expires_after": 3600,
            },
        )

        relay.set_project_models(
            "relay_project",
            [{"model": "seedance-1.0-pro", "channelId": channel["id"], "enabled": True}],
            "admin",
        )
        pro_10 = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "seedance-1.0-pro",
                "content": [{"type": "text", "text": "fixed camera"}],
                "frames": 29,
                "resolution": "720p",
                "ratio": "adaptive",
                "camera_fixed": True,
                "service_tier": "default",
            },
        )

    assert pro_25.status_code == pro_10.status_code == 200
    assert submitted == [
        {
            "model": "doubao-seedance-2-5-260628",
            "content": [
                {"type": "text", "text": "cinematic sunrise"},
                {
                    "type": "image_url",
                    "image_url": {"url": "asset://asset-example"},
                    "role": "first_frame",
                },
            ],
            "duration": 6,
            "resolution": "1080p",
            "ratio": "16:9",
            "generate_audio": True,
            "watermark": False,
            "return_last_frame": True,
            "service_tier": "flex",
            "execution_expires_after": 3600,
            "seed": 42,
        },
        {
            "model": "doubao-seedance-1-0-pro-250528",
            "content": [{"type": "text", "text": "fixed camera"}],
            "frames": 29,
            "resolution": "720p",
            "ratio": "adaptive",
            "camera_fixed": True,
            "service_tier": "default",
        },
    ]


def test_ark_native_video_contract_is_owned_idempotent_and_cancellable(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["model"] == "doubao-seedance-2-5-260628"
            assert payload["task_type"] == "i2v"
            assert payload["content"] == [
                {"type": "text", "text": "RichiDrama native request"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AA=="},
                    "role": "reference_image",
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "asset://asset-video"},
                    "role": "reference_video",
                },
                {
                    "type": "audio_url",
                    "audio_url": {"url": "data:audio/wav;base64,AA=="},
                    "role": "reference_audio",
                },
            ]
            return httpx.Response(200, json={"id": "cgt-native"})
        return httpx.Response(204)

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias="seedance-2.5",
            upstream_model="ignored-model",
        )
        _, other_secret = create_key(client, "relay_project", "other-key")
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {
            "Authorization": f"Bearer {secret}",
            "Idempotency-Key": "richidrama-video-1",
        }
        payload = {
            "model": "seedance-2.5",
            "content": [
                {"type": "text", "text": "RichiDrama native request"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AA=="},
                    "role": "reference_image",
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "asset://asset-video"},
                    "role": "reference_video",
                },
                {
                    "type": "audio_url",
                    "audio_url": {"url": "data:audio/wav;base64,AA=="},
                    "role": "reference_audio",
                },
            ],
            "task_type": "i2v",
            "duration": 5,
        }
        created = client.post("/api/v3/contents/generations/tasks", headers=headers, json=payload)
        replayed = client.post("/api/v3/contents/generations/tasks", headers=headers, json=payload)
        forbidden = client.get(
            f"/api/v3/contents/generations/tasks/{created.json()['id']}",
            headers={"Authorization": f"Bearer {other_secret}"},
        )
        cancelled = client.delete(
            f"/api/v3/contents/generations/tasks/{created.json()['id']}", headers=headers
        )
        legacy_fixed = client.post("/api/video/generate", headers=headers, json=payload)
        legacy_openai = client.post("/v1/videos", headers=headers, json=payload)

    assert created.status_code == replayed.status_code == 200
    assert created.json() == replayed.json()
    assert forbidden.status_code == 404
    assert cancelled.status_code == 204
    assert legacy_fixed.status_code == legacy_openai.status_code == 404
    assert [request.method for request in requests] == ["POST", "DELETE"]
    assert [request.url.path for request in requests] == [
        "/api/v3/contents/generations/tasks",
        "/api/v3/contents/generations/tasks/cgt-native",
    ]


def test_volcengine_video_model_capability_validation(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, channel = provision(
            client,
            provider="volcengine_ark",
            alias="seedance-2.0-fast",
            upstream_model="ignored-model",
        )
        headers = {"Authorization": f"Bearer {secret}"}
        relay = client.app.state.provider_relay
        unsupported_resolution = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "seedance-2.0-fast",
                "content": [{"type": "text", "text": "x"}],
                "duration": 5,
                "resolution": "1080p",
            },
        )
        assert unsupported_resolution.json()["error"]["code"] == "video_resolution_invalid"
        fixed_camera_20 = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "seedance-2.0-fast",
                "content": [{"type": "text", "text": "x"}],
                "duration": 5,
                "camera_fixed": True,
            },
        )
        assert fixed_camera_20.json()["error"]["code"] == "video_camera_unsupported"

        relay.set_project_models(
            "relay_project",
            [{"model": "seedance-1.0-pro", "channelId": channel["id"], "enabled": True}],
            "admin",
        )
        invalid_frames = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={"model": "seedance-1.0-pro", "content": [{"type": "text", "text": "x"}], "frames": 30},
        )
        unsupported_audio = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "seedance-1.0-pro",
                "content": [{"type": "text", "text": "x"}],
                "duration": 5,
                "generate_audio": True,
            },
        )
        assert invalid_frames.json()["error"]["code"] == "video_frames_invalid"
        assert unsupported_audio.json()["error"]["code"] == "video_audio_unsupported"


def test_channel_delete_protection_and_business_admin_cannot_manage_secrets(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, _, channel = provision(
            client,
            provider="volcengine_ark",
            alias="glm-5.2",
            upstream_model="ignored-model",
        )
        with pytest.raises(ApiError) as in_use:
            client.app.state.provider_relay.delete_channel(channel["id"])
        assert in_use.value.code == "provider_channel_in_use"

        forbidden = client.post(
            "/api/internal/provider/channels",
            headers=ADMIN_HEADERS,
            json={
                "projectName": "relay_project",
                "name": "forbidden",
                "provider": "volcengine_ark",
                "config": {},
                "secret": "must-not-be-stored",
                "currentPassword": "Test-admin-password!2026",
                "totpCode": "123456",
            },
        )
        with client.app.state.database.connect() as connection:
            dump = " ".join(connection.iterdump())

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "super_admin_required"
    assert "must-not-be-stored" not in dump


def test_schema_migration_is_idempotent_and_catalog_has_no_default_bindings(tmp_path: Path) -> None:
    path = tmp_path / "migration.db"
    app = create_app(build_settings(path))
    with TestClient(app):
        pass
    with app.state.database.connect() as connection:
        connection.execute(
            "INSERT INTO model_catalog "
            "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
            "VALUES ('glm-5.3','GLM 5.3','volcengine_ark','text','openai_text','legacy-glm','{}')"
        )
        connection.execute(
            "INSERT INTO model_catalog "
            "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
            "VALUES ('wan3.0','Wan 3.0','aliyun_bailian','video','async_video','legacy-wan','{}')"
        )
        connection.execute(
            "INSERT INTO model_catalog "
            "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
            "VALUES ('seedance-1.0-lite-t2v','Retired Lite','volcengine_ark','video',"
            "'async_video','retired-lite','{}')"
        )
        connection.execute(
            "INSERT INTO model_catalog "
            "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
            "VALUES ('seedance-1.5-pro','Unavailable 1.5 Pro','volcengine_ark','video',"
            "'async_video','doubao-seedance-1-5-pro-251215','{}')"
        )
        connection.executemany(
            "INSERT INTO model_catalog "
            "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                ("seedream-3.0-t2i", "Seedream 3.0 T2I", "volcengine_ark", "image", "openai_image", "retired", "{}"),
                ("seededit-3.0-i2i", "SeedEdit 3.0 I2I", "volcengine_ark", "image", "openai_image", "retired", "{}"),
                ("doubao-seed-1.8", "Doubao Seed 1.8", "volcengine_ark", "text", "openai_text", "retired", "{}"),
                ("doubao-seed-1.6-vision", "Doubao Seed 1.6 Vision", "volcengine_ark", "text", "openai_text", "retired", "{}"),
            ],
        )
    app.state.database.initialize()
    with app.state.database.connect() as connection:
        aliases = [
            row[0]
            for row in connection.execute(
                "SELECT alias FROM model_catalog WHERE enabled=1 ORDER BY alias"
            )
        ]
        retired_status = dict(connection.execute(
            "SELECT alias,enabled FROM model_catalog WHERE alias IN ("
            "'seedance-1.0-lite-t2v','seedance-1.5-pro','seedream-3.0-t2i','seededit-3.0-i2i',"
            "'doubao-seed-1.8','doubao-seed-1.6-vision')"
        ))
        bindings = connection.execute("SELECT COUNT(*) FROM project_model_bindings").fetchone()[0]
        permissions = connection.execute("SELECT COUNT(*) FROM api_key_model_permissions").fetchone()[0]

    assert aliases == sorted([
        "deepseek-v4-flash", "glm-5.2", "image2.0", "minimax-h3", "seedream-5.0-pro",
        "seedream-5.0-lite", "seedream-5.0", "seedream-4.5", "seedream-4.0",
        "doubao-seed-2.1-pro", "doubao-seed-2.1-turbo", "doubao-seed-2.0-pro", "doubao-seed-2.0-lite",
        "doubao-seed-2.0-mini",
        "seedance-2.5", "seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini",
        "seedance-1.0-pro", "seedance-1.0-pro-fast",
        "wan3.0-video",
    ])
    with app.state.database.connect() as connection:
        upstream_models = dict(
            connection.execute(
                "SELECT alias,upstream_model FROM model_catalog WHERE enabled=1"
            )
        )
    assert upstream_models == {
        "deepseek-v4-flash": "deepseek-v4-flash-260425",
        "glm-5.2": "glm-5-2-260617",
        "image2.0": "gpt-image-2",
        "minimax-h3": "MiniMax-H3",
        "seedream-5.0-pro": "doubao-seedream-5-0-pro-260628",
        "seedream-5.0-lite": "doubao-seedream-5-0-lite-260128",
        "seedream-5.0": "doubao-seedream-5-0-260128",
        "seedream-4.5": "doubao-seedream-4-5-251128",
        "seedream-4.0": "doubao-seedream-4-0-250828",
        "doubao-seed-2.1-pro": "doubao-seed-2-1-pro-260628",
        "doubao-seed-2.1-turbo": "doubao-seed-2-1-turbo-260628",
        "doubao-seed-2.0-pro": "doubao-seed-2-0-pro-260215",
        "doubao-seed-2.0-lite": "doubao-seed-2-0-lite-260428",
        "doubao-seed-2.0-mini": "doubao-seed-2-0-mini-260215",
        "seedance-2.5": "doubao-seedance-2-5-260628",
        "seedance-2.0": "doubao-seedance-2-0-260128",
        "seedance-2.0-fast": "doubao-seedance-2-0-fast-260128",
        "seedance-2.0-mini": "doubao-seedance-2-0-mini-260615",
        "seedance-1.0-pro": "doubao-seedance-1-0-pro-250528",
        "seedance-1.0-pro-fast": "doubao-seedance-1-0-pro-fast-251015",
        "wan3.0-video": "wan3.0-video",
    }
    assert bindings == permissions == 0
    assert retired_status == {
        "seedance-1.0-lite-t2v": 0,
        "seedance-1.5-pro": 0,
        "seedream-3.0-t2i": 0,
        "seededit-3.0-i2i": 0,
        "doubao-seed-1.8": 0,
        "doubao-seed-1.6-vision": 0,
    }


def test_super_admin_channel_creation_requires_reauth_totp_and_audit_redacts_secret(tmp_path: Path) -> None:
    password = "Initial-provider-owner!2026"
    changed_password = "Changed-provider-owner!2026"
    with relay_client(tmp_path) as client:
        client.app.state.database.create_project("secure_project", "Secure Project", "")
        _, initial = client.app.state.admin_auth.create_initial_super_admin(
            "provider-owner", "Provider Owner", password=password
        )
        assert initial == password
        login = client.post(
            "/api/internal/auth/login",
            json={"username": "provider-owner", "password": password},
        ).json()
        changed = client.post(
            "/api/internal/auth/change-password",
            headers={"X-CSRF-Token": login["csrfToken"]},
            json={"currentPassword": password, "newPassword": changed_password},
        )
        assert changed.status_code == 200
        login = client.post(
            "/api/internal/auth/login",
            json={"username": "provider-owner", "password": changed_password},
        ).json()
        setup = client.post(
            "/api/internal/auth/totp/setup",
            headers={"X-CSRF-Token": login["csrfToken"]},
        ).json()
        now = int(time.time())
        client.app.state.admin_auth.clock = lambda: now
        confirmed = client.post(
            "/api/internal/auth/totp/confirm",
            headers={"X-CSRF-Token": login["csrfToken"]},
            json={"code": pyotp.TOTP(setup["secret"]).at(now)},
        )
        assert confirmed.status_code == 200
        client.app.state.admin_auth.clock = lambda: now + 30
        secret = "super-sensitive-provider-secret"
        created = client.post(
            "/api/internal/provider/channels",
            headers={"X-CSRF-Token": login["csrfToken"]},
            json={
                "projectName": "secure_project",
                "name": "secure-ark",
                "provider": "volcengine_ark",
                "config": {},
                "secret": secret,
                "currentPassword": changed_password,
                "totpCode": pyotp.TOTP(setup["secret"]).at(now + 30),
            },
        )
        with client.app.state.database.connect() as connection:
            audit = dict(
                connection.execute(
                    "SELECT actor,action,after_json FROM admin_audit_logs "
                    "WHERE action='provider.channel.create' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            )
            dump = " ".join(connection.iterdump())

    assert created.status_code == 201, created.text
    assert created.json()["channel"]["secretHint"] == "sup****cret"
    assert created.json()["channel"]["config"] == {"projectName": "secure_project"}
    assert audit["actor"] == "provider-owner"
    assert secret not in audit["after_json"]
    assert secret not in dump
