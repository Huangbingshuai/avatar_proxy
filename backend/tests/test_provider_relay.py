import base64
import asyncio
import json
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.database import Database
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


def test_legacy_relay_constraints_upgrade_preserves_rows(tmp_path: Path) -> None:
    path = tmp_path / "legacy-relay.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE projects(name TEXT PRIMARY KEY,display_name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO projects(name,display_name) VALUES ('legacy','Legacy');
            CREATE TABLE provider_channels(
              id TEXT PRIMARY KEY,project_name TEXT NOT NULL,name TEXT NOT NULL,
              provider TEXT NOT NULL CHECK(provider IN ('openai','volcengine_ark','aliyun_bailian','minimax')),
              config_json TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'active',
              last_test_status TEXT CHECK(last_test_status IN ('success','failed')),last_test_at TEXT,
              last_test_latency_ms INTEGER,last_test_error TEXT,created_by TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              deleted_at TEXT,UNIQUE(project_name,name));
            INSERT INTO provider_channels(id,project_name,name,provider) VALUES ('old-channel','legacy','Old','volcengine_ark');
            CREATE TABLE model_catalog(
              alias TEXT PRIMARY KEY,display_name TEXT NOT NULL,provider TEXT NOT NULL,
              modality TEXT NOT NULL CHECK(modality IN ('text','image','video')),protocol TEXT NOT NULL,
              upstream_model TEXT NOT NULL,capabilities_json TEXT NOT NULL DEFAULT '{}',enabled INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO model_catalog(alias,display_name,provider,modality,protocol,upstream_model) VALUES ('legacy-model','Legacy','volcengine_ark','text','openai_text','legacy-upstream');
            CREATE TABLE billing_model_rates(
              id TEXT PRIMARY KEY,model_alias TEXT NOT NULL,
              metric TEXT NOT NULL CHECK(metric IN ('input_tokens','output_tokens','image','video_second')),
              resolution TEXT NOT NULL DEFAULT '',effective_month TEXT NOT NULL,unit_size INTEGER NOT NULL,
              unit_price_micros INTEGER NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(model_alias,metric,resolution,effective_month));
            INSERT INTO billing_model_rates(id,model_alias,metric,effective_month,unit_size,unit_price_micros,created_by)
              VALUES ('old-rate','legacy-model','input_tokens','2026-09',1000000,1,'admin');
            CREATE TABLE inference_tasks(
              id TEXT PRIMARY KEY,api_key_id TEXT,project_name TEXT,model_alias TEXT,channel_id TEXT,
              credential_id TEXT,operation TEXT,status TEXT,progress INTEGER,request_hash TEXT,idempotency_key TEXT,
              result_url TEXT,result_format TEXT,error_code TEXT,error_message TEXT,provider_request_id TEXT,
              metadata_json TEXT,created_at INTEGER,updated_at TEXT,completed_at TEXT);
            CREATE TABLE inference_usage(
              id TEXT PRIMARY KEY,request_id TEXT,task_id TEXT,api_key_id TEXT,project_name TEXT,model_alias TEXT,
              channel_id TEXT,provider_request_id TEXT,status TEXT,input_tokens INTEGER,output_tokens INTEGER,
              total_tokens INTEGER,generated_images INTEGER,video_seconds REAL,video_width INTEGER,video_height INTEGER,
              created_at TEXT,settled_at TEXT);
            """
        )
    Database(path).initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT provider FROM provider_channels WHERE id='old-channel'").fetchone()[0] == "volcengine_ark"
        assert connection.execute("SELECT COUNT(*) FROM model_catalog WHERE modality IN ('embedding','audio')").fetchone()[0] == 4
        assert connection.execute("SELECT metric FROM billing_model_rates WHERE id='old-rate'").fetchone()[0] == "input_tokens"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        provider_sql = connection.execute("SELECT sql FROM sqlite_master WHERE name='provider_channels'").fetchone()[0]
        assert "volcengine_speech" in provider_sql and "manual" in provider_sql


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


def test_embedding_vision_rewrites_model_and_records_real_tokens(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/embeddings/multimodal"
        assert request.headers["authorization"] == "Bearer secret-volcengine_ark-abcdefgh"
        payload = json.loads(request.content)
        assert payload["model"] == "doubao-embedding-vision-251215"
        assert payload["input"] == [{"type": "text", "text": "测试向量"}]
        return httpx.Response(
            200,
            headers={"x-request-id": "embedding-upstream"},
            json={"object": "multimodal_embedding", "data": {"object": "embedding", "embedding": [0.1, 0.2]}, "usage": {"prompt_tokens": 9, "total_tokens": 9}},
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client, provider="volcengine_ark", alias="doubao-embedding-vision", upstream_model="ignored"
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        response = client.post(
            "/v1/embeddings",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": "测试向量"},
        )
        assert response.status_code == 200
        assert response.json()["model"] == "doubao-embedding-vision"
        assert response.json()["data"] == [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}
        ]
        batch = client.post(
            "/v1/embeddings",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": ["one", "two"]},
        )
        assert batch.status_code == 422
        assert batch.json()["error"]["code"] == "embedding_batch_unsupported"
        invalid_type = client.post(
            "/v1/embeddings",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": {"text": "one"}},
        )
        assert invalid_type.status_code == 422
        assert invalid_type.json()["error"]["code"] == "embedding_input_invalid"
        client.app.state.provider_relay.transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": {}, "usage": {}})
        )
        invalid_response = client.post(
            "/v1/embeddings",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": ["one"]},
        )
        assert invalid_response.status_code == 502
        assert invalid_response.json()["error"]["code"] == "provider_response_invalid"
        with client.app.state.database.connect() as connection:
            usage = connection.execute("SELECT input_tokens,total_tokens FROM inference_usage").fetchone()
        assert tuple(usage) == (9, 9)


def test_speech_tts_uses_separate_key_and_returns_audio(tmp_path: Path) -> None:
    audio = base64.b64encode(b"mock-mp3").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/tts/unidirectional/sse"
        assert request.headers["x-api-key"] == "secret-volcengine_speech-abcdefgh"
        assert request.headers["x-api-resource-id"] == "seed-tts-2.0"
        assert "authorization" not in request.headers
        return httpx.Response(200, headers={"x-tt-logid": "tts-log"}, text=f'data: {{"code":0,"data":"{audio}"}}\n\n')

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client, provider="volcengine_speech", alias="doubao-seed-tts-2.0", upstream_model="ignored"
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        response = client.post(
            "/v1/audio/speech",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-seed-tts-2.0", "input": "你好", "voice": "zh_female_vv_uranus_bigtts"},
        )
        assert response.status_code == 200
        assert response.content == b"mock-mp3"
        assert response.headers["content-type"].startswith("audio/mpeg")
        with client.app.state.database.connect() as connection:
            usage = connection.execute("SELECT input_characters FROM inference_usage").fetchone()[0]
        assert usage == 2


def test_seed_audio_and_async_asr_protocols(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["x-api-key"] == "secret-volcengine_speech-abcdefgh"
        if request.url.path.endswith("/tts/create"):
            payload = json.loads(request.content)
            assert payload["text_prompt"] == "轻柔雨声"
            assert "prompt" not in payload
            return httpx.Response(200, headers={"x-tt-logid": "audio-log"}, json={"data": {"url": "https://cdn.example/audio.mp3", "original_duration": 12}})
        if request.url.path.endswith("/submit"):
            return httpx.Response(200, headers={"x-api-status-code": "20000000", "x-tt-logid": "asr-submit"}, json={})
        return httpx.Response(200, headers={"x-api-status-code": "20000000", "x-tt-logid": "asr-query"}, json={"audio_info": {"duration": 2500}, "result": {"text": "识别完成"}})

    with relay_client(tmp_path) as client:
        create_project(client, "speech-project")
        _, secret = create_key(client, "speech-project", "speech-key")
        relay = client.app.state.provider_relay
        channel = relay.create_channel(
            project_name="speech-project", name="speech", provider="volcengine_speech", config={},
            secret="secret-volcengine_speech-abcdefgh", actor_id="super-admin",
        )
        relay.set_project_models("speech-project", [
            {"model": "seed-audio-1.0", "channelId": channel["id"], "enabled": True},
            {"model": "doubao-seedasr-2.0", "channelId": channel["id"], "enabled": True},
        ], "admin")
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        generated = client.post("/v1/audio/generations", headers=headers, json={"model": "seed-audio-1.0", "prompt": "轻柔雨声"})
        assert generated.status_code == 200
        assert generated.json()["data"][0]["url"].endswith("audio.mp3")
        submitted = client.post(
            "/v1/audio/transcriptions", headers={**headers, "Idempotency-Key": "asr-one"},
            json={"model": "doubao-seedasr-2.0", "url": "https://cdn.example/input.mp3"},
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["id"]
        assert task_id.startswith("asr_")
        completed = client.get(f"/v1/audio/transcriptions/{task_id}", headers=headers)
        assert completed.status_code == 200
        assert completed.json()["text"] == "识别完成"
        with client.app.state.database.connect() as connection:
            seconds = [row[0] for row in connection.execute("SELECT audio_seconds FROM inference_usage ORDER BY created_at")]
        assert seconds == [12.0, 2.5]
    assert calls == ["/api/v3/tts/create", "/api/v3/auc/bigmodel/submit", "/api/v3/auc/bigmodel/query"]


def test_speech_validation_guards_and_manual_channel_test(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        create_project(client, "speech-guards")
        _, secret = create_key(client, "speech-guards", "key")
        relay = client.app.state.provider_relay
        channel = relay.create_channel(
            project_name="speech-guards", name="speech", provider="volcengine_speech", config={},
            secret="speech-secret-abcdefgh", actor_id="owner",
        )
        relay.set_project_models("speech-guards", [
            {"model": "doubao-seed-tts-2.0", "channelId": channel["id"], "enabled": True},
            {"model": "doubao-seedasr-2.0", "channelId": channel["id"], "enabled": True},
            {"model": "seed-audio-1.0", "channelId": channel["id"], "enabled": True},
        ], "admin")
        headers = {"Authorization": f"Bearer {secret}"}
        cases = [
            ("/v1/audio/speech", {"model": "doubao-seed-tts-2.0", "input": "", "voice": "voice"}, "audio_input_invalid"),
            ("/v1/audio/speech", {"model": "doubao-seed-tts-2.0", "input": "hi", "voice": ""}, "audio_voice_invalid"),
            ("/v1/audio/speech", {"model": "doubao-seed-tts-2.0", "input": "hi", "voice": "voice", "response_format": "wav"}, "audio_format_invalid"),
            ("/v1/audio/speech", {"model": "doubao-seed-tts-2.0", "input": "hi", "voice": "voice", "sample_rate": 123}, "audio_sample_rate_invalid"),
            ("/v1/audio/speech", {"model": "doubao-seed-tts-2.0", "input": "hi", "voice": "voice", "speed": 101}, "audio_speed_invalid"),
            ("/v1/audio/generations", {"model": "seed-audio-1.0", "prompt": ""}, "audio_prompt_invalid"),
            ("/v1/audio/transcriptions", {"model": "doubao-seedasr-2.0", "url": "http://private/audio.mp3"}, "audio_url_invalid"),
            ("/v1/audio/speech", {"model": "doubao-seed-tts-2.0", "input": "hi", "voice": "voice", "unknown": 1}, "audio_parameter_unsupported"),
            ("/v1/audio/generations", {"model": "seed-audio-1.0", "prompt": "rain", "unknown": 1}, "audio_parameter_unsupported"),
            ("/v1/audio/transcriptions", {"model": "doubao-seedasr-2.0", "url": "https://cdn.example/a.mp3", "unknown": 1}, "audio_parameter_unsupported"),
        ]
        for path, body, code in cases:
            response = client.post(path, headers=headers, json=body)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code
        manual = asyncio.run(relay.test_channel(channel["id"]))
        assert manual["status"] == "manual"
        assert relay.get_channel(channel["id"])["lastTestStatus"] == "manual"
        assert client.post(
            "/v1/audio/transcriptions", headers={**headers, "Idempotency-Key": ""},
            json={"model": "doubao-seedasr-2.0", "url": "https://cdn.example/a.mp3"},
        ).json()["error"]["code"] == "idempotency_key_invalid"
        assert client.post(
            "/v1/audio/speech", headers=headers,
            json={"model": "seed-audio-1.0", "input": "hi", "voice": "voice"},
        ).json()["error"]["code"] == "model_modality_mismatch"
        assert client.post(
            "/v1/audio/generations", headers=headers,
            json={"model": "doubao-seed-tts-2.0", "prompt": "rain"},
        ).json()["error"]["code"] == "model_modality_mismatch"
        assert client.post(
            "/v1/audio/transcriptions", headers=headers,
            json={"model": "doubao-seed-tts-2.0", "url": "https://cdn.example/a.mp3"},
        ).json()["error"]["code"] == "model_modality_mismatch"


def test_multimodal_embedding_and_speech_error_mapping(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(
            client, provider="volcengine_ark", alias="doubao-embedding-vision", upstream_model="ignored"
        )
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"x-request-id": "multi-id"},
            json={"data": [{"embedding": [0.3]}], "usage": {"prompt_tokens": 3}},
        ))
        good = client.post(
            "/v1/embeddings/multimodal",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": [{"type": "text", "text": "hello"}]},
        )
        assert good.status_code == 200
        relay.set_project_models("relay_project", [
            {"model": "doubao-embedding-vision", "channelId": channel["id"], "enabled": True},
            {"model": "glm-5.2", "channelId": channel["id"], "enabled": True},
        ], "admin")
        assert client.post(
            "/v1/embeddings", headers={"Authorization": f"Bearer {secret}"},
            json={"model": "glm-5.2", "input": "x"},
        ).json()["error"]["code"] == "model_modality_mismatch"
        assert client.post(
            "/v1/embeddings", headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": "", "dimensions": 2048},
        ).json()["error"]["code"] == "embedding_input_invalid"
        assert client.post(
            "/v1/embeddings", headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": "x", "dimensions": 3},
        ).json()["error"]["code"] == "embedding_dimensions_invalid"
        assert client.post(
            "/v1/embeddings", headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": "x", "unknown": 1},
        ).json()["error"]["code"] == "embedding_parameter_unsupported"
        with relay.database.connect() as connection:
            connection.execute(
                "UPDATE model_catalog SET capabilities_json=? WHERE alias='doubao-embedding-vision'",
                ('{"embeddings":true,"multimodal":false}',),
            )
        assert client.post(
            "/v1/embeddings/multimodal", headers={"Authorization": f"Bearer {secret}"},
            json={"model": "doubao-embedding-vision", "input": [{"type": "text", "text": "x"}]},
        ).json()["error"]["code"] == "model_operation_unsupported"

        route = relay.resolve(ApiPrincipal(key_id, "relay_project"), "doubao-embedding-vision")
        speech_route = route.__class__(**{
            **route.__dict__, "provider": "volcengine_speech", "modality": "audio",
            "protocol": "speech_tts", "upstream_model": "seed-tts-2.0",
        })

        async def exercise_errors() -> None:
            relay.transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline", request=request)))
            with pytest.raises(ApiError) as unreachable:
                await relay._speech_request(speech_route, "/x", {}, request_id="r", resource_id=None)
            assert unreachable.value.code == "provider_unreachable"
            relay.transport = httpx.MockTransport(lambda _: httpx.Response(200, headers={"x-api-status-code": "45000030", "x-api-message": "not granted"}, json={}))
            with pytest.raises(ApiError) as denied:
                await relay._speech_request(speech_route, "/x", {}, request_id="r", resource_id=None)
            assert denied.value.code == "provider_request_failed"
            relay.transport = httpx.MockTransport(
                lambda _: httpx.Response(
                    400, json={"code": 45001116, "message": "text_prompt is required"}
                )
            )
            with pytest.raises(ApiError) as body_denied:
                await relay._speech_request(speech_route, "/x", {}, request_id="r", resource_id=None)
            assert body_denied.value.message == "text_prompt is required"
            relay.transport = httpx.MockTransport(lambda _: httpx.Response(200, text="not-json"))
            with pytest.raises(ApiError) as invalid:
                await relay._speech_request(speech_route, "/x", {}, request_id="r", resource_id=None)
            assert invalid.value.code == "provider_response_invalid"

        asyncio.run(exercise_errors())


def test_speech_tts_failure_responses_are_safely_mapped(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client, provider="volcengine_speech", alias="doubao-seed-tts-2.0", upstream_model="ignored"
        )
        relay = client.app.state.provider_relay
        headers = {"Authorization": f"Bearer {secret}"}
        body = {"model": "doubao-seed-tts-2.0", "input": "hello", "voice": "voice"}
        responses = [
            httpx.Response(503, headers={"x-api-message": "busy"}, json={}),
            httpx.Response(200, text="event: audio\ndata: not-json\ndata: []\n"),
            httpx.Response(200, text='data: {"code":45000030,"message":"not granted"}\n'),
            httpx.Response(200, text='data: {"code":0,"data":"%%%"}\n'),
        ]
        expected = [503, 502, 502, 502]
        for upstream, status in zip(responses, expected, strict=True):
            relay.transport = httpx.MockTransport(lambda _, value=upstream: value)
            result = client.post("/v1/audio/speech", headers=headers, json=body)
            assert result.status_code == status
        relay.transport = httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline", request=request))
        )
        assert client.post("/v1/audio/speech", headers=headers, json=body).status_code == 502


def test_audio_generation_unknown_duration_and_asr_submit_failure(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        create_project(client, "speech-errors")
        key_id, secret = create_key(client, "speech-errors", "key")
        relay = client.app.state.provider_relay
        channel = relay.create_channel(
            project_name="speech-errors", name="speech", provider="volcengine_speech", config={},
            secret="speech-secret-abcdefgh", actor_id="owner",
        )
        relay.set_project_models("speech-errors", [
            {"model": "seed-audio-1.0", "channelId": channel["id"], "enabled": True},
            {"model": "doubao-seedasr-2.0", "channelId": channel["id"], "enabled": True},
        ], "admin")
        headers = {"Authorization": f"Bearer {secret}"}
        relay.transport = httpx.MockTransport(lambda _: httpx.Response(
            200, json={"data": {"audio": "YWJj", "original_duration": "unknown"}}
        ))
        generated = client.post(
            "/v1/audio/generations", headers=headers,
            json={"model": "seed-audio-1.0", "prompt": "rain"},
        )
        assert generated.status_code == 200
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT audio_seconds FROM inference_usage").fetchone()[0] is None

        relay.transport = httpx.MockTransport(lambda _: httpx.Response(
            500, headers={"x-api-message": "submit failed"}, json={}
        ))
        failed = client.post(
            "/v1/audio/transcriptions", headers=headers,
            json={"model": "doubao-seedasr-2.0", "url": "https://cdn.example/fail.mp3", "language": "zh"},
        )
        assert failed.status_code == 500
        with client.app.state.database.connect() as connection:
            task = dict(connection.execute("SELECT * FROM inference_tasks WHERE operation='transcription'").fetchone())
        assert task["status"] == "failed"
        principal = ApiPrincipal(key_id, "speech-errors")
        assert asyncio.run(relay.refresh_transcription(principal, task["id"]))["status"] == "failed"
        route = relay.resolve(principal, "seed-audio-1.0")
        other, _ = relay._create_task(principal, route, "image", {"model": route.alias}, None)
        with pytest.raises(ApiError) as wrong:
            asyncio.run(relay.refresh_transcription(principal, other["id"]))
        assert wrong.value.code == "transcription_task_not_found"


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
        ("doubao-seedream-5.0-pro", "doubao-seedream-5-0-pro-260628", 1, False, True, False),
        ("doubao-seedream-5.0-lite", "doubao-seedream-5-0-lite-260128", 15, True, True, False),
        ("doubao-seedream-5.0", "doubao-seedream-5-0-260128", 1, False, True, False),
        ("doubao-seedream-4.5", "doubao-seedream-4-5-251128", 2, True, True, False),
        ("doubao-seedream-4.0", "doubao-seedream-4-0-250828", 2, True, True, False),
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
        ("doubao-seedance-2.5", "doubao-seedance-2-5-260628", None),
        ("doubao-seedance-2.0", "doubao-seedance-2-0-260128", None),
        ("doubao-seedance-2.0-fast", "doubao-seedance-2-0-fast-260128", None),
        ("doubao-seedance-2.0-mini", "doubao-seedance-2-0-mini-260615", None),
        ("doubao-seedance-1.0-pro", "doubao-seedance-1-0-pro-250528", None),
        ("doubao-seedance-1.0-pro-fast", "doubao-seedance-1-0-pro-fast-251015", None),
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
            alias="doubao-seedance-2.5",
            upstream_model="ignored-model",
        )
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        pro_25 = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "doubao-seedance-2.5",
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
            [{"model": "doubao-seedance-1.0-pro", "channelId": channel["id"], "enabled": True}],
            "admin",
        )
        pro_10 = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "doubao-seedance-1.0-pro",
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
            alias="doubao-seedance-2.5",
            upstream_model="ignored-model",
        )
        _, other_secret = create_key(client, "relay_project", "other-key")
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {
            "Authorization": f"Bearer {secret}",
            "Idempotency-Key": "richidrama-video-1",
        }
        payload = {
            "model": "doubao-seedance-2.5",
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
            alias="doubao-seedance-2.0-fast",
            upstream_model="ignored-model",
        )
        headers = {"Authorization": f"Bearer {secret}"}
        relay = client.app.state.provider_relay
        unsupported_resolution = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "doubao-seedance-2.0-fast",
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
                "model": "doubao-seedance-2.0-fast",
                "content": [{"type": "text", "text": "x"}],
                "duration": 5,
                "camera_fixed": True,
            },
        )
        assert fixed_camera_20.json()["error"]["code"] == "video_camera_unsupported"

        relay.set_project_models(
            "relay_project",
            [{"model": "doubao-seedance-1.0-pro", "channelId": channel["id"], "enabled": True}],
            "admin",
        )
        invalid_frames = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={"model": "doubao-seedance-1.0-pro", "content": [{"type": "text", "text": "x"}], "frames": 30},
        )
        unsupported_audio = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "doubao-seedance-1.0-pro",
                "content": [{"type": "text", "text": "x"}],
                "duration": 5,
                "generate_audio": True,
            },
        )
        assert invalid_frames.json()["error"]["code"] == "video_frames_invalid"
        assert unsupported_audio.json()["error"]["code"] == "video_audio_unsupported"


def test_aliyun_video_is_restored_on_ark_compatible_contract(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "workspace-a.cn-beijing.maas.aliyuncs.com"
        assert request.headers["authorization"] == "Bearer secret-aliyun_bailian-abcdefgh"
        assert request.headers["x-dashscope-async"] == "enable"
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload == {
                "model": "wan3.0-video",
                "input": {
                    "prompt": "ocean sunrise",
                    "media": [{"type": "first_frame", "url": "https://example.com/frame.jpg"}],
                },
                "parameters": {
                    "resolution": "1080P",
                    "ratio": "16:9",
                    "prompt_extend": True,
                    "audio": False,
                    "aigc_watermark": False,
                    "duration": 8,
                },
            }
            return httpx.Response(200, json={"output": {"task_id": "ali-task-1"}})
        return httpx.Response(
            200,
            json={
                "output": {
                    "task_status": "SUCCEEDED",
                    "video_url": "https://video.example.com/ali.mp4",
                    "video_duration": 8,
                },
                "usage": {"duration": 8},
            },
        )

    with relay_client(tmp_path) as client:
        catalog = client.app.state.provider_relay.catalog()
        assert {item["id"] for item in catalog} >= {"wan3.0-video", "minimax-h3"}
        _, secret, _ = provision(
            client,
            provider="aliyun_bailian",
            alias="wan3.0-video",
            upstream_model="ignored-model",
            config={"workspaceId": "workspace-a", "region": "cn-beijing"},
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        assert [model["id"] for model in client.get("/v1/models", headers=headers).json()["data"]] == [
            "wan3.0-video"
        ]
        created = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "wan3.0-video",
                "content": [
                    {"type": "text", "text": "ocean sunrise"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/frame.jpg"},
                        "role": "first_frame",
                    },
                ],
                "duration": 8,
                "resolution": "1080P",
                "ratio": "16:9",
                "generate_audio": False,
                "watermark": False,
            },
        )
        finished = client.get(
            f"/api/v3/contents/generations/tasks/{created.json()['id']}", headers=headers
        )
        unsupported_cancel = client.delete(
            f"/api/v3/contents/generations/tasks/{created.json()['id']}", headers=headers
        )
        with client.app.state.database.connect() as connection:
            usage_seconds = connection.execute(
                "SELECT video_seconds FROM inference_usage WHERE model_alias='wan3.0-video'"
            ).fetchone()[0]

    assert created.status_code == 200
    assert finished.status_code == 200
    assert finished.json()["status"] == "succeeded"
    assert finished.json()["content"]["video_url"] == "https://video.example.com/ali.mp4"
    assert unsupported_cancel.status_code == 422
    assert unsupported_cancel.json()["error"]["code"] == "video_cancel_unsupported"
    assert usage_seconds == 8
    assert [request.url.path for request in requests] == [
        "/api/v1/services/aigc/video-generation/video-synthesis",
        "/api/v1/tasks/ali-task-1",
    ]


def test_response_only_model_rejects_chat_and_stream_before_upstream(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "translation-request"},
            json={"id": "resp-translation", "model": payload["model"], "output": []},
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="volcengine_ark",
            alias="doubao-seed-translation",
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        chat = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={"model": "doubao-seed-translation", "messages": []},
        )
        streamed = client.post(
            "/v1/responses",
            headers=headers,
            json={"model": "doubao-seed-translation", "input": [], "stream": True},
        )
        response = client.post(
            "/v1/responses",
            headers=headers,
            json={"model": "doubao-seed-translation", "input": [], "stream": False},
        )

    assert chat.status_code == 422
    assert chat.json()["error"]["code"] == "model_operation_unsupported"
    assert streamed.status_code == 422
    assert streamed.json()["error"]["code"] == "model_stream_unsupported"
    assert response.status_code == 200
    assert response.json()["model"] == "doubao-seed-translation"
    assert len(requests) == 1


def test_minimax_video_is_restored_on_ark_compatible_contract(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "api.minimax.cn"
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload == {
                "model": "MiniMax-H3",
                "content": [{"type": "text", "text": "camera move"}],
                "resolution": "768P",
                "ratio": "adaptive",
                "duration": 6,
                "seed": 12,
            }
            return httpx.Response(200, json={"task_id": "mini-task-1"})
        return httpx.Response(
            200,
            json={
                "task": {
                    "status": "succeeded",
                    "content": {"url": "https://video.example.com/minimax.mp4"},
                    "usage": {"output_seconds": 6},
                    "duration": 6,
                    "resolution": "768P",
                    "ratio": "adaptive",
                }
            },
        )

    with relay_client(tmp_path) as client:
        _, secret, _ = provision(
            client,
            provider="minimax",
            alias="minimax-h3",
            upstream_model="ignored-model",
        )
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": f"Bearer {secret}"}
        created = client.post(
            "/api/v3/contents/generations/tasks",
            headers=headers,
            json={
                "model": "minimax-h3",
                "content": [{"type": "text", "text": "camera move"}],
                "duration": 6,
                "seed": 12,
            },
        )
        finished = client.get(
            f"/api/v3/contents/generations/tasks/{created.json()['id']}", headers=headers
        )

    assert created.status_code == 200
    assert finished.status_code == 200
    assert finished.json()["model"] == "minimax-h3"
    assert finished.json()["status"] == "succeeded"
    assert finished.json()["content"]["video_url"] == "https://video.example.com/minimax.mp4"
    assert [request.url.path for request in requests] == [
        "/v2/video_generation",
        "/v2/query/video_generation/mini-task-1",
    ]


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
                ("doubao-seed-code", "Doubao Seed Code", "volcengine_ark", "text", "openai_text", "retired", "{}"),
                ("glm-4.7", "GLM 4.7", "volcengine_ark", "text", "openai_text", "retired", "{}"),
                ("qwen3-32b", "Qwen3 32B", "volcengine_ark", "text", "openai_text", "unavailable", "{}"),
                ("qwen3-14b", "Qwen3 14B", "volcengine_ark", "text", "openai_text", "unavailable", "{}"),
                ("qwen3-8b", "Qwen3 8B", "volcengine_ark", "text", "openai_text", "unavailable", "{}"),
                ("qwen3-0.6b", "Qwen3 0.6B", "volcengine_ark", "text", "openai_text", "unavailable", "{}"),
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
        removed_count = connection.execute(
            "SELECT COUNT(*) FROM model_catalog WHERE alias IN ("
            "'doubao-seed-code','glm-4.7','qwen3-32b','qwen3-14b','qwen3-8b','qwen3-0.6b')"
        ).fetchone()[0]
        bindings = connection.execute("SELECT COUNT(*) FROM project_model_bindings").fetchone()[0]
        permissions = connection.execute("SELECT COUNT(*) FROM api_key_model_permissions").fetchone()[0]

    assert aliases == sorted([
        "deepseek-v4-flash", "deepseek-v4-pro", "glm-5.2",
        "image2.0", "minimax-h3", "doubao-seedream-5.0-pro",
        "doubao-seedream-5.0-lite", "doubao-seedream-5.0", "doubao-seedream-4.5", "doubao-seedream-4.0",
        "doubao-seed-2.1-pro", "doubao-seed-2.1-turbo", "doubao-seed-2.0-pro", "doubao-seed-2.0-lite",
        "doubao-seed-2.0-mini", "doubao-seed-evolving", "doubao-seed-character",
        "doubao-seed-2.0-code", "doubao-seed-translation",
        "doubao-seedance-2.5", "doubao-seedance-2.0", "doubao-seedance-2.0-fast", "doubao-seedance-2.0-mini",
        "doubao-seedance-1.0-pro", "doubao-seedance-1.0-pro-fast",
        "wan3.0-video", "doubao-embedding-vision", "doubao-seed-tts-2.0",
        "doubao-seedasr-2.0", "seed-audio-1.0",
    ])
    with app.state.database.connect() as connection:
        upstream_models = dict(
            connection.execute(
                "SELECT alias,upstream_model FROM model_catalog WHERE enabled=1"
            )
        )
        seedream_capabilities = {
            row["alias"]: json.loads(row["capabilities_json"])
            for row in connection.execute(
                "SELECT alias,capabilities_json FROM model_catalog "
                "WHERE alias LIKE 'doubao-seedream-%' AND enabled=1"
            )
        }
    assert upstream_models == {
        "deepseek-v4-flash": "deepseek-v4-flash-260425",
        "deepseek-v4-pro": "deepseek-v4-pro-ga-260813",
        "glm-5.2": "glm-5-2-260617",
        "image2.0": "gpt-image-2",
        "minimax-h3": "MiniMax-H3",
        "doubao-seedream-5.0-pro": "doubao-seedream-5-0-pro-260628",
        "doubao-seedream-5.0-lite": "doubao-seedream-5-0-lite-260128",
        "doubao-seedream-5.0": "doubao-seedream-5-0-260128",
        "doubao-seedream-4.5": "doubao-seedream-4-5-251128",
        "doubao-seedream-4.0": "doubao-seedream-4-0-250828",
        "doubao-seed-2.1-pro": "doubao-seed-2-1-pro-260628",
        "doubao-seed-2.1-turbo": "doubao-seed-2-1-turbo-260628",
        "doubao-seed-2.0-pro": "doubao-seed-2-0-pro-260215",
        "doubao-seed-2.0-lite": "doubao-seed-2-0-lite-260428",
        "doubao-seed-2.0-mini": "doubao-seed-2-0-mini-260215",
        "doubao-seed-evolving": "doubao-seed-evolving",
        "doubao-seed-character": "doubao-seed-character-260628",
        "doubao-seed-2.0-code": "doubao-seed-2-0-code-preview-260215",
        "doubao-seed-translation": "doubao-seed-translation-250915",
        "doubao-seedance-2.5": "doubao-seedance-2-5-260628",
        "doubao-seedance-2.0": "doubao-seedance-2-0-260128",
        "doubao-seedance-2.0-fast": "doubao-seedance-2-0-fast-260128",
        "doubao-seedance-2.0-mini": "doubao-seedance-2-0-mini-260615",
        "doubao-seedance-1.0-pro": "doubao-seedance-1-0-pro-250528",
        "doubao-seedance-1.0-pro-fast": "doubao-seedance-1-0-pro-fast-251015",
        "wan3.0-video": "wan3.0-video",
        "doubao-embedding-vision": "doubao-embedding-vision-251215",
        "doubao-seed-tts-2.0": "seed-tts-2.0",
        "doubao-seedasr-2.0": "volc.seedasr.auc",
        "seed-audio-1.0": "seed-audio-1.0",
    }
    assert seedream_capabilities
    assert all(
        capabilities["maxInputImageBytes"] == 10 * 1024 * 1024
        for capabilities in seedream_capabilities.values()
    )
    assert bindings == permissions == 0
    assert removed_count == 0
    assert retired_status == {
        "seedance-1.0-lite-t2v": 0,
        "seedance-1.5-pro": 0,
        "seedream-3.0-t2i": 0,
        "seededit-3.0-i2i": 0,
        "doubao-seed-1.8": 0,
        "doubao-seed-1.6-vision": 0,
    }


def test_doubao_alias_migration_rewrites_configuration_and_rejects_old_alias(tmp_path: Path) -> None:
    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(
            client,
            provider="volcengine_ark",
            alias="doubao-seedance-2.0",
            upstream_model="doubao-seedance-2-0-260128",
        )
        database = client.app.state.database
        with database.connect() as connection:
            connection.execute(
                "INSERT INTO model_catalog "
                "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
                "SELECT 'seedance-2.0',display_name,provider,modality,protocol,upstream_model,capabilities_json "
                "FROM model_catalog WHERE alias='doubao-seedance-2.0'"
            )
            connection.execute(
                "UPDATE project_model_bindings SET model_alias='seedance-2.0' "
                "WHERE project_name='relay_project' AND model_alias='doubao-seedance-2.0'"
            )
            connection.execute(
                "INSERT INTO api_key_model_permissions(api_key_id,model_alias,enabled) VALUES (?,?,1)",
                (key_id, "seedance-2.0"),
            )
            connection.execute(
                "INSERT INTO billing_model_rates"
                "(id,model_alias,metric,resolution,effective_month,unit_size,unit_price_micros,created_by) "
                "VALUES ('legacy-rate','seedance-2.0','video_second','720p','2026-09',1,1000,'test')"
            )

        database.initialize()
        database.initialize()

        with database.connect() as connection:
            assert connection.execute(
                "SELECT 1 FROM model_catalog WHERE alias='seedance-2.0'"
            ).fetchone() is None
            assert connection.execute(
                "SELECT model_alias FROM project_model_bindings WHERE project_name='relay_project'"
            ).fetchone()[0] == "doubao-seedance-2.0"
            assert connection.execute(
                "SELECT model_alias FROM api_key_model_permissions WHERE api_key_id=?", (key_id,)
            ).fetchone()[0] == "doubao-seedance-2.0"
            assert connection.execute(
                "SELECT model_alias FROM billing_model_rates WHERE id='legacy-rate'"
            ).fetchone()[0] == "doubao-seedance-2.0"

        rejected = client.post(
            "/api/v3/contents/generations/tasks",
            headers={"Authorization": f"Bearer {secret}"},
            json={"model": "seedance-2.0", "content": [{"type": "text", "text": "x"}]},
        )
        assert rejected.status_code == 403
        assert rejected.json()["error"]["code"] == "model_not_allowed"
        assert channel["provider"] == "volcengine_ark"


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
