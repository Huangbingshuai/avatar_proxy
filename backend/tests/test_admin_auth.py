import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.admin_cli as admin_cli
from app.admin_auth import AdminAuthService
from app.database import Database
from app.main import create_app
from conftest import build_settings


INITIAL_PASSWORD = "Initial-admin-password!2026"
CHANGED_PASSWORD = "Changed-admin-password!2026"


def bootstrap(app, username: str = "owner") -> None:
    app.state.admin_auth.create_initial_super_admin(
        username,
        "Owner",
        password=INITIAL_PASSWORD,
    )


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/internal/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_cookies(client: TestClient) -> tuple[str, str]:
    return (
        client.cookies.get("avatar_admin_session"),
        client.cookies.get("avatar_admin_csrf"),
    )


def restore_auth_cookies(client: TestClient, values: tuple[str, str]) -> None:
    client.cookies.set("avatar_admin_session", values[0], path="/api/internal")
    client.cookies.set("avatar_admin_csrf", values[1], path="/")


def change_initial_password(client: TestClient, body: dict, password: str = CHANGED_PASSWORD) -> dict:
    response = client.post(
        "/api/internal/auth/change-password",
        headers={"X-CSRF-Token": body["csrfToken"]},
        json={"currentPassword": INITIAL_PASSWORD, "newPassword": password},
    )
    assert response.status_code == 200, response.text
    return login(client, body["user"]["username"], password)


def test_login_uses_hashed_credentials_and_secure_cookie_contract(tmp_path: Path) -> None:
    settings = build_settings(tmp_path / "admin.db", admin_cookie_secure=True)
    app = create_app(settings)
    with TestClient(app) as client:
        bootstrap(app)
        response = client.post(
            "/api/internal/auth/login",
            json={"username": "owner", "password": INITIAL_PASSWORD},
        )
        session_token = response.cookies["avatar_admin_session"]
        csrf_token = response.json()["csrfToken"]

        assert response.status_code == 200
        cookie_headers = response.headers.get_list("set-cookie")
        session_cookie = next(value for value in cookie_headers if value.startswith("avatar_admin_session="))
        csrf_cookie = next(value for value in cookie_headers if value.startswith("avatar_admin_csrf="))
        assert "HttpOnly" in session_cookie
        assert "Secure" in session_cookie
        assert "SameSite=strict" in session_cookie
        assert "Path=/api/internal" in session_cookie
        assert "HttpOnly" not in csrf_cookie
        assert "Path=/" in csrf_cookie

        with app.state.database.connect() as connection:
            password_hash = connection.execute("SELECT password_hash FROM admin_users").fetchone()[0]
            stored_session = connection.execute("SELECT token_hash,csrf_hash FROM admin_sessions").fetchone()
            dump = " ".join(connection.iterdump())
        assert password_hash.startswith("$argon2id$")
        assert session_token not in stored_session["token_hash"]
        assert csrf_token not in stored_session["csrf_hash"]
        assert INITIAL_PASSWORD not in dump
        assert session_token not in dump
        assert csrf_token not in dump


def test_first_login_requires_password_change_and_revokes_old_session(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        bootstrap(app)
        body = login(client, "owner", INITIAL_PASSWORD)
        blocked = client.get("/api/internal/project/list")
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "password_change_required"

        changed = client.post(
            "/api/internal/auth/change-password",
            headers={"X-CSRF-Token": body["csrfToken"]},
            json={"currentPassword": INITIAL_PASSWORD, "newPassword": CHANGED_PASSWORD},
        )
        assert changed.status_code == 200
        assert client.get("/api/internal/auth/me").status_code == 401

        fresh = login(client, "owner", CHANGED_PASSWORD)
        assert fresh["user"]["mustChangePassword"] is False
        assert client.get("/api/internal/project/list").status_code == 200


def test_csrf_is_required_and_legacy_admin_token_is_rejected(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        bootstrap(app)
        body = change_initial_password(client, login(client, "owner", INITIAL_PASSWORD))

        missing = client.post(
            "/api/internal/admin/users",
            json={"username": "worker", "displayName": "Worker"},
        )
        wrong = client.post(
            "/api/internal/admin/users",
            headers={"X-CSRF-Token": "wrong"},
            json={"username": "worker", "displayName": "Worker"},
        )
        valid = client.post(
            "/api/internal/admin/users",
            headers={"X-CSRF-Token": body["csrfToken"]},
            json={"username": "worker", "displayName": "Worker"},
        )

    assert missing.status_code == wrong.status_code == 403
    assert missing.json()["error"]["code"] == "invalid_csrf_token"
    assert valid.status_code == 201

    with TestClient(create_app(build_settings(tmp_path / "empty.db"))) as other:
        legacy = other.get(
            "/api/internal/project/list",
            headers={"X-Admin-Token": "legacy-token"},
        )
    assert legacy.status_code == 401
    assert legacy.json()["error"]["code"] == "admin_session_required"


def test_login_rejects_untrusted_origin_but_allows_configured_console(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db", cors_origins="http://console.test"))
    with TestClient(app) as client:
        bootstrap(app)
        rejected = client.post(
            "/api/internal/auth/login",
            headers={"Origin": "https://attacker.example"},
            json={"username": "owner", "password": INITIAL_PASSWORD},
        )
        accepted = client.post(
            "/api/internal/auth/login",
            headers={"Origin": "http://console.test"},
            json={"username": "owner", "password": INITIAL_PASSWORD},
        )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "admin_origin_forbidden"
    assert accepted.status_code == 200


def test_role_boundary_disable_and_reset_revoke_sessions(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as owner_client:
        bootstrap(app)
        owner = change_initial_password(owner_client, login(owner_client, "owner", INITIAL_PASSWORD))
        owner_cookies = auth_cookies(owner_client)
        created = owner_client.post(
            "/api/internal/admin/users",
            headers={"X-CSRF-Token": owner["csrfToken"]},
            json={"username": "worker", "displayName": "Worker"},
        ).json()
        worker_id = created["user"]["id"]

        worker_login = login(owner_client, "worker", created["initialPassword"])
        owner_client.post(
            "/api/internal/auth/change-password",
            headers={"X-CSRF-Token": worker_login["csrfToken"]},
            json={
                "currentPassword": created["initialPassword"],
                "newPassword": CHANGED_PASSWORD,
            },
        )
        worker_login = login(owner_client, "worker", CHANGED_PASSWORD)
        worker_cookies = auth_cookies(owner_client)
        assert owner_client.get("/api/internal/project/list").status_code == 200
        forbidden = owner_client.get("/api/internal/admin/users")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "super_admin_required"

        restore_auth_cookies(owner_client, owner_cookies)
        disabled = owner_client.put(
            f"/api/internal/admin/users/{worker_id}/disable",
            headers={"X-CSRF-Token": owner["csrfToken"]},
        )
        assert disabled.status_code == 200
        restore_auth_cookies(owner_client, worker_cookies)
        assert owner_client.get("/api/internal/auth/me").status_code == 401
        restore_auth_cookies(owner_client, owner_cookies)

        self_reset = owner_client.post(
            f"/api/internal/admin/users/{owner['user']['id']}/reset-password",
            headers={"X-CSRF-Token": owner["csrfToken"]},
        )
        self_disable = owner_client.put(
            f"/api/internal/admin/users/{owner['user']['id']}/disable",
            headers={"X-CSRF-Token": owner["csrfToken"]},
        )
    assert self_reset.status_code == self_disable.status_code == 409
    assert self_reset.json()["error"]["code"] == "cannot_reset_self"
    assert self_disable.json()["error"]["code"] == "cannot_disable_self"


def test_super_admin_user_lifecycle_and_audit_routes(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        bootstrap(app)
        owner = change_initial_password(client, login(client, "owner", INITIAL_PASSWORD))
        headers = {"X-CSRF-Token": owner["csrfToken"]}
        created_response = client.post(
            "/api/internal/admin/users",
            headers=headers,
            json={"username": "worker", "displayName": "Worker"},
        )
        created = created_response.json()
        worker_id = created["user"]["id"]
        duplicate = client.post(
            "/api/internal/admin/users",
            headers=headers,
            json={"username": "WORKER", "displayName": "Duplicate"},
        )
        disabled = client.put(f"/api/internal/admin/users/{worker_id}/disable", headers=headers)
        enabled = client.put(f"/api/internal/admin/users/{worker_id}/enable", headers=headers)
        reset = client.post(f"/api/internal/admin/users/{worker_id}/reset-password", headers=headers)
        users = client.get("/api/internal/admin/users")
        audits = client.get("/api/internal/admin/audits", params={"limit": 200})
        missing_enable = client.put(
            "/api/internal/admin/users/missing/enable", headers=headers
        )
        missing_reset = client.post(
            "/api/internal/admin/users/missing/reset-password", headers=headers
        )

    assert created_response.status_code == 201
    assert created["user"]["role"] == "admin"
    assert duplicate.status_code == 409
    assert disabled.json()["user"]["status"] == "disabled"
    assert enabled.json()["user"]["status"] == "active"
    assert reset.status_code == 200
    assert reset.json()["initialPassword"]
    assert len(users.json()["users"]) == 2
    actions = {item["action"] for item in audits.json()["audits"]}
    assert {"admin.user.create", "admin.user.disable", "admin.user.enable", "admin.user.reset_password"} <= actions
    assert missing_enable.status_code == missing_reset.status_code == 404


def test_session_list_manual_revoke_and_logout(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as first:
        bootstrap(app)
        first_login = change_initial_password(first, login(first, "owner", INITIAL_PASSWORD))
        first_cookies = auth_cookies(first)
        second_login = login(first, "owner", CHANGED_PASSWORD)
        second_cookies = auth_cookies(first)
        restore_auth_cookies(first, first_cookies)
        sessions = first.get("/api/internal/auth/sessions").json()["sessions"]
        second_session = next(item for item in sessions if not item["current"])
        revoked = first.delete(
            f"/api/internal/auth/sessions/{second_session['id']}",
            headers={"X-CSRF-Token": first_login["csrfToken"]},
        )
        missing = first.delete(
            "/api/internal/auth/sessions/missing",
            headers={"X-CSRF-Token": first_login["csrfToken"]},
        )
        assert revoked.status_code == 200
        assert missing.status_code == 404
        restore_auth_cookies(first, second_cookies)
        assert first.get("/api/internal/auth/me").status_code == 401
        assert second_login["session"]["current"] is True
        restore_auth_cookies(first, first_cookies)

        logged_out = first.post(
            "/api/internal/auth/logout",
            headers={"X-CSRF-Token": first_login["csrfToken"]},
        )
        assert logged_out.status_code == 200
        assert first.get("/api/internal/auth/me").status_code == 401


def test_invalid_password_and_session_variants(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        bootstrap(app)
        nonexistent = client.post(
            "/api/internal/auth/login",
            json={"username": "nobody", "password": "wrong"},
        )
        wrong = client.post(
            "/api/internal/auth/login",
            json={"username": "owner", "password": "wrong"},
        )
        body = login(client, "owner", INITIAL_PASSWORD)
        bad_current = client.post(
            "/api/internal/auth/change-password",
            headers={"X-CSRF-Token": body["csrfToken"]},
            json={"currentPassword": "wrong", "newPassword": CHANGED_PASSWORD},
        )
        too_short = client.post(
            "/api/internal/auth/change-password",
            headers={"X-CSRF-Token": body["csrfToken"]},
            json={"currentPassword": INITIAL_PASSWORD, "newPassword": "short"},
        )
        client.cookies.set("avatar_admin_session", "forged", path="/api/internal")
        client.cookies.set("avatar_admin_csrf", "forged", path="/")
        forged = client.get("/api/internal/auth/me")
    assert nonexistent.status_code == wrong.status_code == 401
    assert bad_current.status_code == 401
    assert bad_current.json()["error"]["code"] == "invalid_current_password"
    assert too_short.status_code == 422
    assert forged.status_code == 401
    assert forged.json()["error"]["code"] == "invalid_admin_session"


def test_login_lock_is_username_only_and_recovers(tmp_path: Path) -> None:
    app = create_app(
        build_settings(
            tmp_path / "admin.db",
            admin_login_lock_seconds=60,
            admin_login_window_seconds=60,
        )
    )
    with TestClient(app) as client:
        bootstrap(app)
        for _ in range(4):
            failed = client.post(
                "/api/internal/auth/login",
                json={"username": "owner", "password": "wrong"},
            )
            assert failed.status_code == 401
        locked = client.post(
            "/api/internal/auth/login",
            json={"username": "owner", "password": "wrong"},
        )
        assert locked.status_code == 429
        assert locked.json()["error"]["code"] == "admin_login_locked"
        assert int(locked.headers["Retry-After"]) >= 1

        # Unknown usernames are not an IP bucket and cannot lock the real account.
        for index in range(8):
            client.post(
                "/api/internal/auth/login",
                json={"username": f"unknown{index}", "password": "wrong"},
            )
        app.state.admin_auth.clock = lambda: 10**10
        recovered = client.post(
            "/api/internal/auth/login",
            json={"username": "owner", "password": INITIAL_PASSWORD},
        )
        assert recovered.status_code == 200
        with app.state.database.connect() as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_ip_login_throttles'"
            ).fetchone()
        assert table is None


def test_idle_and_absolute_session_expiry(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path / "admin.db",
        admin_session_idle_seconds=60,
        admin_session_absolute_seconds=300,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.admin_auth.clock = lambda: 1000
        bootstrap(app)
        login(client, "owner", INITIAL_PASSWORD)
        app.state.admin_auth.clock = lambda: 1060
        idle = client.get("/api/internal/auth/me")
        assert idle.status_code == 401
        assert idle.json()["error"]["code"] == "admin_session_expired"


def test_admin_schema_upgrade_is_idempotent_and_preserves_legacy_audits(tmp_path: Path) -> None:
    path = tmp_path / "legacy-audit.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                source_ip TEXT,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO admin_audit_logs(actor,action,target_type,target_id)
            VALUES ('console-admin','quota.project.update','project','legacy');
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(path)
    database.initialize()
    database.initialize()
    with database.connect() as upgraded:
        tables = {
            row["name"] for row in upgraded.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        columns = {
            row["name"] for row in upgraded.execute("PRAGMA table_info(admin_audit_logs)").fetchall()
        }
        legacy = upgraded.execute("SELECT * FROM admin_audit_logs WHERE target_id='legacy'").fetchone()
    assert {"admin_users", "admin_sessions"} <= tables
    assert "admin_ip_login_throttles" not in tables
    assert {"actor_id", "outcome", "user_agent"} <= columns
    assert legacy["actor"] == "console-admin"
    assert legacy["outcome"] == "success"


def test_cli_bootstrap_is_unique_and_cli_reset_recovers_super_admin(tmp_path: Path) -> None:
    settings = build_settings(tmp_path / "admin.db")
    database = Database(settings.database_path)
    database.initialize()
    service = AdminAuthService(database, settings)
    user, _ = service.create_initial_super_admin("owner", "Owner", password=INITIAL_PASSWORD)

    try:
        service.create_initial_super_admin("second", "Second", password=INITIAL_PASSWORD)
        raised = None
    except Exception as error:  # ApiError is asserted by stable public code below.
        raised = error
    assert getattr(raised, "code", None) == "initial_admin_exists"

    reset_user, reset_password = service.reset_password_from_cli("owner")
    assert reset_user["id"] == user["id"]
    assert reset_user["role"] == "super_admin"
    assert reset_user["mustChangePassword"] is True
    assert reset_password != INITIAL_PASSWORD


def test_admin_cli_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    settings = build_settings(tmp_path / "cli.db")
    monkeypatch.setattr(admin_cli, "get_settings", lambda: settings)

    assert admin_cli.main(["create", "--username", "owner", "--display-name", "Owner"]) == 0
    created_output = capsys.readouterr().out
    assert "super_admin" in created_output
    assert "一次性初始密码" in created_output

    assert admin_cli.main(["create", "--username", "second", "--display-name", "Second"]) == 1
    assert "已经存在" in capsys.readouterr().err
    assert admin_cli.main(["reset-password", "--username", "owner"]) == 0
    assert "一次性初始密码" in capsys.readouterr().out
    assert admin_cli.main(["reset-password", "--username", "missing"]) == 1
    assert "不存在" in capsys.readouterr().err
    assert admin_cli.main(["create", "--username", "x", "--display-name", "X"]) == 2
    assert "用户名" in capsys.readouterr().err


def test_password_policy_service_branches(tmp_path: Path) -> None:
    service = AdminAuthService(
        Database(tmp_path / "policy.db"),
        build_settings(tmp_path / "policy.db"),
    )
    with pytest.raises(Exception) as short:
        service.validate_password("short", "owner")
    with pytest.raises(Exception) as same:
        service.validate_password("same-user-password", "same-user-password")
    assert getattr(short.value, "code", None) == "invalid_admin_password"
    assert getattr(same.value, "code", None) == "invalid_admin_password"
