import json
import sqlite3
from pathlib import Path

import pyotp
from fastapi.testclient import TestClient

from app.backup import BackupManager
from app.database import Database
from app.main import create_app
from conftest import build_settings


INITIAL_PASSWORD = "Initial-admin-password!2026"
CHANGED_PASSWORD = "Changed-admin-password!2026"
BASE_TIME = 1_800_000_000


def enroll_super(client: TestClient, app) -> tuple[dict, str, list[str]]:
    app.state.admin_auth.clock = lambda: BASE_TIME
    app.state.admin_auth.create_initial_super_admin("owner", "Owner", password=INITIAL_PASSWORD)
    initial = client.post(
        "/api/internal/auth/login", json={"username": "owner", "password": INITIAL_PASSWORD}
    ).json()
    changed = client.post(
        "/api/internal/auth/change-password",
        headers={"X-CSRF-Token": initial["csrfToken"]},
        json={"currentPassword": INITIAL_PASSWORD, "newPassword": CHANGED_PASSWORD},
    )
    assert changed.status_code == 200
    setup_login = client.post(
        "/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD}
    ).json()
    setup = client.post(
        "/api/internal/auth/totp/setup",
        headers={"X-CSRF-Token": setup_login["csrfToken"]},
    )
    assert setup.status_code == 200
    setup_body = setup.json()
    confirmed = client.post(
        "/api/internal/auth/totp/confirm",
        headers={"X-CSRF-Token": setup_login["csrfToken"]},
        json={"code": pyotp.TOTP(setup_body["secret"]).at(BASE_TIME)},
    )
    assert confirmed.status_code == 200
    return setup_login, setup_body["secret"], confirmed.json()["recoveryCodes"]


def test_totp_enrollment_encryption_login_replay_and_recovery_codes(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, secret, recovery_codes = enroll_super(client, app)
        assert len(recovery_codes) == 10
        assert session["user"]["mfaSetupRequired"] is True

        with app.state.database.connect() as connection:
            user = connection.execute("SELECT * FROM admin_users WHERE username='owner'").fetchone()
            stored_codes = connection.execute(
                "SELECT code_hash FROM admin_recovery_codes WHERE admin_user_id=?", (user["id"],)
            ).fetchall()
            dump = " ".join(connection.iterdump())
        assert user["totp_enabled_at"]
        assert user["totp_secret_encrypted"] != secret
        assert secret not in dump
        assert all(code not in dump for code in recovery_codes)
        assert len(stored_codes) == 10

        client.post(
            "/api/internal/auth/logout", headers={"X-CSRF-Token": session["csrfToken"]}
        )
        missing = client.post(
            "/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD}
        )
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "admin_totp_required"

        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        current_code = pyotp.TOTP(secret).at(BASE_TIME + 30)
        verified = client.post(
            "/api/internal/auth/login",
            json={"username": "owner", "password": CHANGED_PASSWORD, "totpCode": current_code},
        )
        assert verified.status_code == 200
        assert verified.json()["session"]["mfaVerified"] is True
        csrf = verified.json()["csrfToken"]
        client.post("/api/internal/auth/logout", headers={"X-CSRF-Token": csrf})

        replay = client.post(
            "/api/internal/auth/login",
            json={"username": "owner", "password": CHANGED_PASSWORD, "totpCode": current_code},
        )
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "admin_totp_replayed"

        recovered = client.post(
            "/api/internal/auth/login",
            json={
                "username": "owner",
                "password": CHANGED_PASSWORD,
                "recoveryCode": recovery_codes[0],
            },
        )
        assert recovered.status_code == 200
        recovered_csrf = recovered.json()["csrfToken"]
        client.post("/api/internal/auth/logout", headers={"X-CSRF-Token": recovered_csrf})
        reused = client.post(
            "/api/internal/auth/login",
            json={
                "username": "owner",
                "password": CHANGED_PASSWORD,
                "recoveryCode": recovery_codes[0],
            },
        )
        assert reused.status_code == 401


def test_super_admin_is_security_only_sensitive_actions_reauthenticate_and_alert(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, _, _ = enroll_super(client, app)
        headers = {"X-CSRF-Token": session["csrfToken"]}
        blocked = client.get("/api/internal/project/list")
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "super_admin_security_only"

        wrong = client.post(
            "/api/internal/admin/users",
            headers=headers,
            json={"username": "worker", "displayName": "Worker", "currentPassword": "wrong"},
        )
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "admin_reauthentication_failed"

        created = client.post(
            "/api/internal/admin/users",
            headers=headers,
            json={
                "username": "worker",
                "displayName": "Worker",
                "currentPassword": CHANGED_PASSWORD,
            },
        )
        assert created.status_code == 201
        worker_id = created.json()["user"]["id"]
        client.put(
            f"/api/internal/admin/users/{worker_id}/disable",
            headers=headers,
            json={"currentPassword": CHANGED_PASSWORD},
        )
        deleted = client.request(
            "DELETE",
            f"/api/internal/admin/users/{worker_id}",
            headers=headers,
            json={"currentPassword": CHANGED_PASSWORD},
        )
        assert deleted.status_code == 200
        alerts = client.get("/api/internal/admin/security-alerts").json()["alerts"]
        alert_types = {item["eventType"] for item in alerts}
        assert {
            "super_admin_login",
            "admin_password_changed",
            "totp_enabled",
            "admin_deleted",
        } <= alert_types
        delete_alert = next(item for item in alerts if item["eventType"] == "admin_deleted")
        acknowledged = client.post(
            "/api/internal/admin/security-alerts/ack",
            headers=headers,
            json={"alertId": delete_alert["id"]},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["alert"]["acknowledged_at"]


def test_cli_totp_reset_revokes_sessions_and_requires_reenrollment(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, _, _ = enroll_super(client, app)
        reset = app.state.admin_auth.reset_totp_from_cli("owner")
        assert reset["totpEnabled"] is False
        assert client.get("/api/internal/auth/me").status_code == 401
        relogin = client.post(
            "/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD}
        )
        assert relogin.status_code == 200
        assert relogin.json()["user"]["mfaSetupRequired"] is True
        with app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM admin_recovery_codes").fetchone()[0] == 0
        assert session["user"]["role"] == "super_admin"


def test_sqlite_and_audit_backup_is_consistent_and_pruned(tmp_path: Path) -> None:
    database = Database(tmp_path / "source.db")
    database.initialize()
    database.write_admin_audit(
        actor="owner",
        actor_id=None,
        source_ip="127.0.0.1",
        user_agent="pytest",
        action="admin.test",
        target_type="test",
        target_id="one",
    )
    settings = build_settings(
        database.path,
        admin_backup_enabled=True,
        admin_backup_directory=tmp_path / "backups",
        admin_backup_retention=2,
    )
    manager = BackupManager(database, settings)
    manager.run_backup()
    manager.run_backup()
    status = manager.run_backup()
    assert status["lastRun"]["status"] == "success"
    database_files = sorted((tmp_path / "backups").glob("avatar_proxy-*.db"))
    audit_files = sorted((tmp_path / "backups").glob("admin_audit-*.jsonl"))
    assert len(database_files) == len(audit_files) == 2
    with sqlite3.connect(database_files[-1]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT COUNT(*) FROM admin_audit_logs").fetchone()[0] == 1
    exported = [json.loads(line) for line in audit_files[-1].read_text(encoding="utf-8").splitlines()]
    assert exported[0]["action"] == "admin.test"
