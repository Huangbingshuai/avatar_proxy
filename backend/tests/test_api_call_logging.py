from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.call_logging import _response_summary
from app.main import create_app

from conftest import ADMIN_HEADERS, create_key, create_project


def _authorization(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}", "User-Agent": "relay-log-test/1.0"}


def test_known_key_requests_are_logged_with_redacted_details(
    tmp_path: Path, settings_factory
) -> None:
    app = create_app(settings_factory(tmp_path / "call-logs.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)

        successful = client.get(
            "/api/auth/me?api_key=query-secret&signature=query-signature",
            headers=_authorization(secret),
        )
        rejected = client.post(
            "/v1/images/generations",
            headers={**_authorization(secret), "Idempotency-Key": "private-idempotency-value"},
            json={
                "model": "gpt-image-2",
                "prompt": "请生成一张测试图片",
                "api_key": "nested-secret",
                "image_data": "base64-media-secret",
                "url": "https://cdn.example.com/input.png?token=signed-secret",
                "blob": "A" * 256,
                "note": f"Bearer {secret}",
            },
        )
        listed = client.get(
            "/api/internal/call-logs",
            headers=ADMIN_HEADERS,
            params={"apiKeyId": key_id, "limit": 20},
        )
        filtered = client.get(
            "/api/internal/call-logs",
            headers=ADMIN_HEADERS,
            params={
                "projectName": "drama_prod",
                "apiKeyId": key_id,
                "search": "images/generations",
                "model": "gpt-image",
                "success": "false",
                "from": "2000-01-01T00:00:00Z",
                "to": "2100-01-01T00:00:00Z",
            },
        )

    assert successful.status_code == 200
    assert rejected.status_code == 422
    assert listed.status_code == 200
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    items = listed.json()["items"]
    assert len(items) == 2

    image_log = next(item for item in items if item["path"] == "/v1/images/generations")
    assert image_log["apiKeyId"] == key_id
    assert image_log["projectName"] == "drama_prod"
    assert image_log["method"] == "POST"
    assert image_log["routeTemplate"] == "/v1/images/generations"
    assert image_log["modelAlias"] == "gpt-image-2"
    assert image_log["isModelCall"] is True
    assert image_log["success"] is False
    assert image_log["statusCode"] == 422
    assert image_log["errorCode"] == "route_override_forbidden"
    assert image_log["requestParams"]["idempotencyKey"] == "[PRESENT]"
    request_body = image_log["requestParams"]["body"]
    assert request_body["api_key"] == "[REDACTED]"
    assert request_body["image_data"] == "[REDACTED]"
    assert request_body["url"] == "https://cdn.example.com/input.png?[REDACTED]"
    assert request_body["blob"] == "[BASE64:256 chars]"
    assert request_body["note"] == "[REDACTED_SECRET]"

    auth_log = next(item for item in items if item["path"] == "/api/auth/me")
    assert auth_log["success"] is True
    assert auth_log["requestParams"]["query"]["api_key"] == "[REDACTED]"
    assert auth_log["requestParams"]["query"]["signature"] == "[REDACTED]"
    assert auth_log["userAgent"] == "relay-log-test/1.0"
    assert auth_log["requestId"]

    serialized = json.dumps(items, ensure_ascii=False)
    for private_value in (
        secret,
        "query-secret",
        "query-signature",
        "nested-secret",
        "base64-media-secret",
        "signed-secret",
        "private-idempotency-value",
    ):
        assert private_value not in serialized


def test_stream_summary_records_completion_and_redacted_error_without_content() -> None:
    summary, code, message = _response_summary(
        "text/event-stream; charset=utf-8",
        b'data: {"choices":[{"delta":{"content":"private output"}}]}\n\n'
        b'data: {"error":{"code":"upstream_error","message":"Bearer sk-private123456789"}}\n\n'
        b"data: [DONE]\n\n",
        180,
        4096,
        {},
    )

    assert code == "upstream_error"
    assert message == "[REDACTED_SECRET]"
    assert summary["stream"] is True
    assert summary["streamCompleted"] is True
    assert "private output" not in json.dumps(summary)


def test_disabled_known_key_failure_is_logged_but_unknown_key_is_not(
    tmp_path: Path, settings_factory
) -> None:
    app = create_app(settings_factory(tmp_path / "disabled-key.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        missing_route = client.get("/api/not-a-real-route", headers=_authorization(secret))
        client.put(
            "/api/internal/apikey/disable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )

        disabled = client.get("/api/auth/me", headers=_authorization(secret))
        unknown = client.get("/api/auth/me", headers=_authorization("vap_live_unknown"))
        listed = client.get("/api/internal/call-logs", headers=ADMIN_HEADERS)

    assert missing_route.status_code == 404
    assert disabled.status_code == 401
    assert unknown.status_code == 401
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    item = next(entry for entry in listed.json()["items"] if entry["statusCode"] == 401)
    assert item["apiKeyId"] == key_id
    assert item["success"] is False
    assert item["errorCode"] == "invalid_api_key"
    route_item = next(entry for entry in listed.json()["items"] if entry["statusCode"] == 404)
    assert route_item["path"] == "/api/not-a-real-route"
    assert route_item["errorMessage"] == "Not Found"


def test_key_and_project_deletion_preserve_call_log_identity(
    tmp_path: Path, settings_factory
) -> None:
    app = create_app(settings_factory(tmp_path / "delete-history.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        assert client.get("/api/auth/me", headers=_authorization(secret)).status_code == 200
        client.put(
            "/api/internal/apikey/disable",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        deleted_key = client.request(
            "DELETE",
            "/api/internal/apikey/delete",
            headers=ADMIN_HEADERS,
            json={"keyId": key_id},
        )
        deleted_project = client.request(
            "DELETE",
            "/api/internal/project/delete",
            headers=ADMIN_HEADERS,
            json={"name": "drama_prod"},
        )
        logs = client.get("/api/internal/call-logs", headers=ADMIN_HEADERS).json()

    assert deleted_key.status_code == 200
    assert deleted_project.status_code == 409
    assert deleted_project.json()["error"]["code"] == "project_has_call_history"
    assert logs["total"] == 1
    assert logs["items"][0]["apiKeyName"] == "production"


def test_overview_uses_all_time_totals_and_real_usage(
    tmp_path: Path, settings_factory
) -> None:
    app = create_app(settings_factory(tmp_path / "overview.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        assert client.get("/api/auth/me", headers=_authorization(secret)).status_code == 200
        assert client.get("/api/auth/me", headers=_authorization(secret)).status_code == 200
        with app.state.database.connect() as connection:
            connection.execute(
                "INSERT INTO provider_channels(id,project_name,name,provider) VALUES (?,?,?,?)",
                ("channel-test", "drama_prod", "测试渠道", "volcengine_ark"),
            )
            connection.execute(
                "INSERT INTO inference_usage(id,request_id,api_key_id,project_name,model_alias,"
                "channel_id,status,input_tokens,output_tokens,total_tokens) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    "usage-http-log-test",
                    "usage-request",
                    key_id,
                    "drama_prod",
                    "glm-5.2",
                    "channel-test",
                    "succeeded",
                    120,
                    30,
                    150,
                ),
            )
            connection.execute(
                "INSERT INTO video_usage(api_key_id,project_name,task_id,model,total_tokens) "
                "VALUES (?,?,?,?,?)",
                (key_id, "drama_prod", "video-task", "seedance", 9),
            )

        overview = client.get("/api/internal/overview", headers=ADMIN_HEADERS)

    assert overview.status_code == 200
    stats = overview.json()["stats"]
    assert stats["requestsTotal"] == 2
    assert stats["errorsTotal"] == 0
    assert stats["modelCalls"] == 2
    assert stats["tokenUsage"] == 159
    assert "requests24h" not in stats
    assert len(overview.json()["recent"]) == 2
    assert overview.json()["recent"][0]["apiKeyName"] == "production"


def test_legacy_request_log_schema_is_upgraded_idempotently(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                action TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO request_logs(api_key_id,project_name,action,status_code,duration_ms)
            VALUES ('legacy-key','legacy-project','ListAssets',503,15);
            """
        )

    from app.database import Database

    database = Database(database_path)
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        row = connection.execute(
            "SELECT log_type,success,request_params_json,response_summary_json "
            "FROM request_logs WHERE id=1"
        ).fetchone()

    assert dict(row) == {
        "log_type": "http_legacy",
        "success": 0,
        "request_params_json": "{}",
        "response_summary_json": "{}",
    }


def test_retention_prunes_details_but_keeps_all_time_counters(tmp_path: Path) -> None:
    from app.database import Database

    database = Database(tmp_path / "retention.db", request_log_retention_days=7)
    database.initialize()
    database.log_api_call(
        request_id="old-request",
        api_key_id="old-key",
        project_name="old-project",
        method="GET",
        path="/api/auth/me",
        route_template="/api/auth/me",
        action="current_session",
        model_alias=None,
        request_params_json="{}",
        status_code=500,
        success=False,
        response_summary_json="{}",
        error_code="old_error",
        error_message="old error",
        duration_ms=1,
        response_bytes=0,
        source_ip=None,
        user_agent=None,
        is_model_call=False,
    )
    database.log_api_call(
        request_id="old-request",
        api_key_id="old-key",
        project_name="old-project",
        method="GET",
        path="/api/auth/me",
        route_template="/api/auth/me",
        action="current_session",
        model_alias=None,
        request_params_json="{}",
        status_code=500,
        success=False,
        response_summary_json="{}",
        error_code="old_error",
        error_message="old error",
        duration_ms=1,
        response_bytes=0,
        source_ip=None,
        user_agent=None,
        is_model_call=False,
    )
    with database.connect() as connection:
        connection.execute(
            "UPDATE request_logs SET created_at='2000-01-01 00:00:00' WHERE request_id='old-request'"
        )

    database.initialize()
    with database.connect() as connection:
        detail_count = connection.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0]

    stats = database.overview()["stats"]
    assert detail_count == 0
    assert stats["requestsTotal"] == 1
    assert stats["errorsTotal"] == 1
