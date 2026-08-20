import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.backup import BackupManager
from app.database import Database
from app.errors import ApiError
from app.main import create_app
from app.maintenance import MaintenanceGate
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


def test_super_admin_can_rotate_totp_and_old_credentials_stop_working(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, old_secret, old_recovery_codes = enroll_super(client, app)
        headers = {"X-CSRF-Token": session["csrfToken"]}
        with app.state.database.connect() as connection:
            user = connection.execute("SELECT id FROM admin_users WHERE username='owner'").fetchone()
            connection.execute(
                "INSERT INTO admin_sessions "
                "(id,admin_user_id,token_hash,csrf_hash,created_at,last_seen_at,absolute_expires_at,mfa_verified) "
                "VALUES ('other-session',?,'other-token-hash','other-csrf-hash',?,?,?,1)",
                (user["id"], BASE_TIME, BASE_TIME, BASE_TIME + 3600),
            )

        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        started = client.post(
            "/api/internal/auth/totp/rotate/setup",
            headers=headers,
            json={
                "currentPassword": CHANGED_PASSWORD,
                "currentTotpCode": pyotp.TOTP(old_secret).at(BASE_TIME + 30),
            },
        )
        assert started.status_code == 200, started.text
        new_secret = started.json()["secret"]
        assert new_secret != old_secret
        confirmed = client.post(
            "/api/internal/auth/totp/rotate/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(new_secret).at(BASE_TIME + 30)},
        )
        assert confirmed.status_code == 200, confirmed.text
        new_recovery_codes = confirmed.json()["recoveryCodes"]
        assert len(new_recovery_codes) == 10
        assert confirmed.json()["otherSessionsRevoked"] == 1

        with app.state.database.connect() as connection:
            updated = connection.execute("SELECT * FROM admin_users WHERE id=?", (user["id"],)).fetchone()
            other_session = connection.execute(
                "SELECT revoked_at,revoke_reason FROM admin_sessions WHERE id='other-session'"
            ).fetchone()
            recovery_hashes = {
                row["code_hash"]
                for row in connection.execute(
                    "SELECT code_hash FROM admin_recovery_codes WHERE admin_user_id=?", (user["id"],)
                ).fetchall()
            }
            audit = connection.execute(
                "SELECT action FROM admin_audit_logs WHERE action='admin.auth.totp_rotated'"
            ).fetchone()
            alert = connection.execute(
                "SELECT event_type,severity FROM admin_security_alerts "
                "WHERE event_type='totp_rotated' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            database_dump = " ".join(connection.iterdump())
        assert app.state.admin_auth._decrypt_secret(updated["totp_secret_encrypted"]) == new_secret
        assert updated["totp_pending_secret_encrypted"] is None
        assert updated["totp_pending_session_id"] is None
        assert updated["totp_pending_expires_at"] is None
        assert dict(other_session) == {"revoked_at": BASE_TIME + 30, "revoke_reason": "totp_rotated"}
        assert all(hashlib.sha256(code.upper().encode()).hexdigest() not in recovery_hashes for code in old_recovery_codes)
        assert all(hashlib.sha256(code.upper().encode()).hexdigest() in recovery_hashes for code in new_recovery_codes)
        assert old_secret not in database_dump
        assert new_secret not in database_dump
        assert all(code not in database_dump for code in new_recovery_codes)
        assert audit is not None
        assert dict(alert) == {"event_type": "totp_rotated", "severity": "critical"}

        client.post("/api/internal/auth/logout", headers=headers)
        app.state.admin_auth.clock = lambda: BASE_TIME + 60
        old_login = client.post(
            "/api/internal/auth/login",
            json={
                "username": "owner",
                "password": CHANGED_PASSWORD,
                "totpCode": pyotp.TOTP(old_secret).at(BASE_TIME + 60),
            },
        )
        assert old_login.status_code == 401
        old_recovery = client.post(
            "/api/internal/auth/login",
            json={
                "username": "owner",
                "password": CHANGED_PASSWORD,
                "recoveryCode": old_recovery_codes[0],
            },
        )
        assert old_recovery.status_code == 401
        new_login = client.post(
            "/api/internal/auth/login",
            json={
                "username": "owner",
                "password": CHANGED_PASSWORD,
                "totpCode": pyotp.TOTP(new_secret).at(BASE_TIME + 60),
            },
        )
        assert new_login.status_code == 200


def test_totp_rotation_requires_old_credentials_and_expires_without_replacing_secret(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, old_secret, _ = enroll_super(client, app)
        headers = {"X-CSRF-Token": session["csrfToken"]}
        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        wrong_password = client.post(
            "/api/internal/auth/totp/rotate/setup",
            headers=headers,
            json={
                "currentPassword": "wrong-password",
                "currentTotpCode": pyotp.TOTP(old_secret).at(BASE_TIME + 30),
            },
        )
        assert wrong_password.status_code == 401
        wrong_totp = client.post(
            "/api/internal/auth/totp/rotate/setup",
            headers=headers,
            json={"currentPassword": CHANGED_PASSWORD, "currentTotpCode": "000000"},
        )
        assert wrong_totp.status_code == 401
        with app.state.database.connect() as connection:
            unchanged = connection.execute("SELECT * FROM admin_users WHERE username='owner'").fetchone()
        assert unchanged["totp_pending_secret_encrypted"] is None
        assert app.state.admin_auth._decrypt_secret(unchanged["totp_secret_encrypted"]) == old_secret
        started = client.post(
            "/api/internal/auth/totp/rotate/setup",
            headers=headers,
            json={
                "currentPassword": CHANGED_PASSWORD,
                "currentTotpCode": pyotp.TOTP(old_secret).at(BASE_TIME + 30),
            },
        )
        new_secret = started.json()["secret"]
        with app.state.database.connect() as connection:
            pending = connection.execute("SELECT * FROM admin_users WHERE username='owner'").fetchone()
            original_session_id = pending["totp_pending_session_id"]
            connection.execute(
                "UPDATE admin_users SET totp_pending_session_id='another-session' WHERE id=?",
                (pending["id"],),
            )
        mismatch = client.post(
            "/api/internal/auth/totp/rotate/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(new_secret).at(BASE_TIME + 30)},
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "admin_totp_rotation_session_mismatch"
        with app.state.database.connect() as connection:
            connection.execute(
                "UPDATE admin_users SET totp_pending_session_id=? WHERE username='owner'",
                (original_session_id,),
            )
        app.state.admin_auth.clock = lambda: BASE_TIME + 30 + 601
        expired = client.post(
            "/api/internal/auth/totp/rotate/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(new_secret).at(BASE_TIME + 30 + 601)},
        )
        assert expired.status_code == 410
        assert expired.json()["error"]["code"] == "admin_totp_rotation_expired"
        with app.state.database.connect() as connection:
            user = connection.execute("SELECT * FROM admin_users WHERE username='owner'").fetchone()
        assert app.state.admin_auth._decrypt_secret(user["totp_secret_encrypted"]) == old_secret
        assert user["totp_pending_secret_encrypted"] is None
        assert user["totp_pending_session_id"] is None
        assert user["totp_pending_expires_at"] is None


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


def _create_restore_backup(app, project_name: str = "backup_project") -> str:
    with app.state.database.connect() as connection:
        connection.execute(
            "INSERT INTO projects(name,display_name,description) VALUES (?,?,?)",
            (project_name, "Backup project", "restore fixture"),
        )
    status = app.state.backup.run_backup()
    return status["lastRun"]["backupId"]


def test_super_admin_can_validate_and_restore_server_backup(tmp_path: Path) -> None:
    # A full retention window locks in the edge case where the pre-restore rollback
    # snapshot must not prune the selected candidate before it is consumed.
    app = create_app(build_settings(tmp_path / "admin.db", admin_backup_retention=2))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        backup_id = _create_restore_backup(app)
        with app.state.database.connect() as connection:
            connection.execute(
                "INSERT INTO projects(name,display_name,description) VALUES ('interim_project','Interim','')"
            )
        app.state.backup.run_backup()
        with app.state.database.connect() as connection:
            connection.execute(
                "INSERT INTO projects(name,display_name,description) VALUES ('new_project','New','')"
            )

        listed = client.get("/api/internal/admin/backups")
        assert listed.status_code == 200
        assert any(item["id"] == backup_id for item in listed.json()["backups"])
        validated = client.post(
            f"/api/internal/admin/backups/{backup_id}/validate",
            headers={"X-CSRF-Token": session["csrfToken"]},
        )
        assert validated.status_code == 200
        assert validated.json()["backup"]["integrity"] == "ok"
        assert validated.json()["backup"]["counts"]["projects"] == 1

        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        restored = client.post(
            f"/api/internal/admin/backups/{backup_id}/restore",
            headers={"X-CSRF-Token": session["csrfToken"]},
            json={
                "currentPassword": CHANGED_PASSWORD,
                "totpCode": pyotp.TOTP(secret).at(BASE_TIME + 30),
                "confirmation": "恢复数据库",
            },
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["restored"] is True
        assert restored.json()["rollbackBackupId"] != backup_id
        assert client.get("/api/internal/auth/me").status_code == 401

        with app.state.database.connect() as connection:
            projects = {
                row["name"] for row in connection.execute("SELECT name FROM projects").fetchall()
            }
            restore_run = connection.execute(
                "SELECT * FROM admin_restore_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            active_sessions = connection.execute(
                "SELECT COUNT(*) FROM admin_sessions WHERE revoked_at IS NULL"
            ).fetchone()[0]
            alert = connection.execute(
                "SELECT event_type,severity FROM admin_security_alerts "
                "WHERE event_type='database_restored' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        assert projects == {"backup_project"}
        assert restore_run["status"] == "success"
        assert active_sessions == 0
        assert dict(alert) == {"event_type": "database_restored", "severity": "critical"}


def test_restore_failure_rolls_back_current_database(tmp_path: Path, monkeypatch) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        backup_id = _create_restore_backup(app, "old_project")
        with app.state.database.connect() as connection:
            connection.execute(
                "INSERT INTO projects(name,display_name,description) VALUES ('current_project','Current','')"
            )
        original = app.state.backup._restore_and_initialize
        candidate = app.state.backup._resolve_backup(backup_id)

        def fail_candidate(path: Path) -> None:
            if path == candidate:
                raise RuntimeError("injected restore failure")
            original(path)

        monkeypatch.setattr(app.state.backup, "_restore_and_initialize", fail_candidate)
        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        response = client.post(
            f"/api/internal/admin/backups/{backup_id}/restore",
            headers={"X-CSRF-Token": session["csrfToken"]},
            json={
                "currentPassword": CHANGED_PASSWORD,
                "totpCode": pyotp.TOTP(secret).at(BASE_TIME + 30),
                "confirmation": "恢复数据库",
            },
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "admin_restore_failed"
        assert response.json()["error"]["rollbackFailed"] is False
        with app.state.database.connect() as connection:
            projects = {
                row["name"] for row in connection.execute("SELECT name FROM projects").fetchall()
            }
            restore_run = connection.execute(
                "SELECT status,error FROM admin_restore_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        assert projects == {"old_project", "current_project"}
        assert restore_run["status"] == "failed"
        assert "injected restore failure" in restore_run["error"]


def test_restore_rejects_invalid_id_confirmation_and_corrupt_database(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        invalid_id = client.post(
            "/api/internal/admin/backups/../secrets/validate",
            headers={"X-CSRF-Token": session["csrfToken"]},
        )
        assert invalid_id.status_code == 404
        corrupt_id = "20260819-120000-999999"
        app.state.backup.directory.mkdir(parents=True, exist_ok=True)
        (app.state.backup.directory / f"avatar_proxy-{corrupt_id}.db").write_bytes(b"not sqlite")
        corrupt = client.post(
            f"/api/internal/admin/backups/{corrupt_id}/validate",
            headers={"X-CSRF-Token": session["csrfToken"]},
        )
        assert corrupt.status_code == 422
        backup_id = _create_restore_backup(app)
        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        confirmation = client.post(
            f"/api/internal/admin/backups/{backup_id}/restore",
            headers={"X-CSRF-Token": session["csrfToken"]},
            json={
                "currentPassword": CHANGED_PASSWORD,
                "totpCode": pyotp.TOTP(secret).at(BASE_TIME + 30),
                "confirmation": "确认",
            },
        )
        assert confirmation.status_code == 422
        assert confirmation.json()["error"]["code"] == "admin_restore_confirmation_invalid"


def test_backup_validation_and_backup_write_failure_matrix(tmp_path: Path, monkeypatch) -> None:
    database = Database(tmp_path / "source.db")
    database.initialize()
    settings = build_settings(database.path, admin_backup_directory=tmp_path / "backups")
    manager = BackupManager(database, settings)
    assert manager.list_backups() == []

    manager.directory.mkdir(parents=True)
    incomplete_id = "20260819-120000-000001"
    incomplete_path = manager.directory / f"avatar_proxy-{incomplete_id}.db"
    with sqlite3.connect(incomplete_path) as connection:
        connection.execute("CREATE TABLE placeholder(id INTEGER PRIMARY KEY)")
    with pytest.raises(ApiError) as missing_schema:
        manager.validate_backup(incomplete_id)
    assert missing_schema.value.code == "admin_backup_schema_invalid"

    corrupt_id = "20260819-120000-000002"
    (manager.directory / f"avatar_proxy-{corrupt_id}.db").write_bytes(b"not sqlite")
    listed = {item["id"]: item for item in manager.list_backups()}
    assert listed[corrupt_id]["unreadable"] is True

    def fail_export(_database_file: Path, _audit_file: Path) -> None:
        raise OSError("injected audit export failure")

    monkeypatch.setattr(manager, "_export_audits", fail_export)
    with pytest.raises(OSError, match="injected audit export failure"):
        manager.run_backup()
    with database.connect() as connection:
        run = connection.execute(
            "SELECT status,error FROM admin_backup_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert run["status"] == "failed"
    assert "injected audit export failure" in run["error"]
    assert not list(manager.directory.glob("*.tmp"))


def test_backup_rejects_wrong_totp_key_and_missing_active_super(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        enroll_super(client, app)
        backup_id = _create_restore_backup(app)
        backup_path = app.state.backup._resolve_backup(backup_id)

        def wrong_key(_encrypted: str) -> None:
            raise ApiError("wrong key", 503, "admin_totp_key_unavailable")

        app.state.backup.totp_secret_validator = wrong_key
        with pytest.raises(ApiError) as mismatch:
            app.state.backup.validate_backup(backup_id)
        assert mismatch.value.code == "admin_backup_totp_key_mismatch"

        app.state.backup.totp_secret_validator = None
        with sqlite3.connect(backup_path) as connection:
            connection.execute("UPDATE admin_users SET status='disabled'")
        with pytest.raises(ApiError) as no_super:
            app.state.backup.validate_backup(backup_id)
        assert no_super.value.code == "admin_backup_super_admin_invalid"


def test_backup_schedule_manual_lock_and_restore_without_gate(tmp_path: Path) -> None:
    database = Database(tmp_path / "source.db")
    database.initialize()
    settings = build_settings(
        database.path,
        admin_backup_enabled=True,
        admin_backup_directory=tmp_path / "backups",
        admin_backup_interval_seconds=3600,
    )
    manager = BackupManager(database, settings)
    assert manager._is_due() is True
    asyncio.run(manager.run_if_due())
    assert manager._is_due() is False
    asyncio.run(manager.run_manual_backup())
    backup_id = manager.status()["lastRun"]["backupId"]
    with pytest.raises(ApiError) as unavailable:
        asyncio.run(manager.restore_backup(backup_id, actor="owner", source_ip="127.0.0.1"))
    assert unavailable.value.code == "admin_restore_unavailable"


def test_restore_reports_when_candidate_and_rollback_both_fail(tmp_path: Path, monkeypatch) -> None:
    app = create_app(build_settings(tmp_path / "admin.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        backup_id = _create_restore_backup(app)

        def fail_every_restore(_path: Path) -> None:
            raise RuntimeError("injected total restore failure")

        monkeypatch.setattr(app.state.backup, "_restore_and_initialize", fail_every_restore)
        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        response = client.post(
            f"/api/internal/admin/backups/{backup_id}/restore",
            headers={"X-CSRF-Token": session["csrfToken"]},
            json={
                "currentPassword": CHANGED_PASSWORD,
                "totpCode": pyotp.TOTP(secret).at(BASE_TIME + 30),
                "confirmation": "恢复数据库",
            },
        )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "admin_restore_failed"
    assert response.json()["error"]["rollbackFailed"] is True


def test_maintenance_gate_drains_inflight_work_and_rejects_new_requests() -> None:
    async def scenario() -> None:
        gate = MaintenanceGate()
        assert await gate.begin_request() is True  # an existing business request
        assert await gate.begin_request() is True  # the restore request
        entered = asyncio.Event()

        async def restore() -> None:
            async with gate.exclusive_restore():
                entered.set()
                assert await gate.begin_request() is False

        task = asyncio.create_task(restore())
        await asyncio.sleep(0)
        assert gate.active is True
        assert not entered.is_set()
        await gate.finish_request()
        await asyncio.wait_for(entered.wait(), timeout=1)
        await task
        await gate.finish_request()
        assert gate.active is False
        assert await gate.begin_request() is True
        await gate.finish_request()

    asyncio.run(scenario())
