import pyotp
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import build_settings
from test_admin_security_deep import BASE_TIME, CHANGED_PASSWORD, enroll_super

URL = "/api/internal/admin/security/login-policy"


def change(client, app, session, secret, enabled=True, offset=30, **values):
    app.state.admin_auth.clock = lambda: BASE_TIME + offset
    return client.put(URL, headers={"X-CSRF-Token": session["csrfToken"]}, json={
        "loginTotpBypass": enabled, "currentPassword": CHANGED_PASSWORD,
        "totpCode": pyotp.TOTP(secret).at(BASE_TIME + offset), **values,
    })


def test_bypass_login_restore_and_credential_preservation(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, codes = enroll_super(client, app)
        assert client.get(URL).json()["policy"] == {"loginTotpBypass": False, "totpEnabled": True}
        with app.state.database.connect() as connection:
            before = dict(connection.execute("SELECT * FROM admin_users WHERE username='owner'").fetchone())
            recovery_before = [tuple(row) for row in connection.execute("SELECT * FROM admin_recovery_codes")]
        enabled = change(client, app, session, secret)
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["user"]["loginTotpBypass"] is True
        client.post("/api/internal/auth/logout", headers={"X-CSRF-Token": session["csrfToken"]})
        login = client.post("/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD})
        assert login.status_code == 200, login.text
        session = login.json()
        assert session["user"]["loginTotpBypass"] is True
        assert session["session"]["mfaVerified"] is False
        me = client.get("/api/internal/auth/me").json()["user"]
        assert me["mfaVerified"] is False and me["totpEnabled"] is True and me["loginTotpBypass"] is True
        assert client.get("/api/internal/admin/users").status_code == 200
        with app.state.database.connect() as connection:
            after = dict(connection.execute("SELECT * FROM admin_users WHERE username='owner'").fetchone())
            recovery_after = [tuple(row) for row in connection.execute("SELECT * FROM admin_recovery_codes")]
        assert after["totp_secret_encrypted"] == before["totp_secret_encrypted"]
        assert recovery_before == recovery_after
        # Sensitive writes still demand a fresh TOTP, even in a password-only session.
        denied = change(client, app, session, secret, False, 60, totpCode="not-a-code")
        assert denied.status_code == 422
        restored = change(client, app, session, secret, False, 60)
        assert restored.status_code == 200, restored.text
        assert restored.json()["user"]["mfaVerified"] is True
        assert client.get("/api/internal/auth/me").json()["user"]["mfaVerified"] is True
        client.post("/api/internal/auth/logout", headers={"X-CSRF-Token": session["csrfToken"]})
        missing = client.post("/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD})
        assert missing.status_code == 401 and missing.json()["error"]["code"] == "admin_totp_required"
        app.state.admin_auth.clock = lambda: BASE_TIME + 90
        assert client.post("/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD,
            "totpCode": pyotp.TOTP(secret).at(BASE_TIME + 90)}).status_code == 200
        with app.state.database.connect() as connection:
            records = " ".join(str(tuple(row)) for row in connection.execute(
                "SELECT before_json,after_json FROM admin_audit_logs WHERE action='admin.auth.login_policy.update'"))
            alerts = connection.execute("SELECT COUNT(*) FROM admin_security_alerts WHERE event_type='super_admin_login_policy_changed'").fetchone()[0]
        assert CHANGED_PASSWORD not in records and secret not in records
        assert all(code not in records for code in codes)
        assert alerts == 2


def test_switch_revokes_other_sessions_but_current_session_remains_valid(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        other = TestClient(app)
        app.state.admin_auth.clock = lambda: BASE_TIME + 30
        other_login = other.post("/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD,
            "totpCode": pyotp.TOTP(secret).at(BASE_TIME + 30)})
        assert other_login.status_code == 200
        result = change(client, app, session, secret, offset=60)
        assert result.json()["otherSessionsRevoked"] == 1
        assert other.get("/api/internal/admin/users").status_code == 401
        assert client.get("/api/internal/admin/users").status_code == 200


def test_policy_write_requires_csrf_password_fresh_totp_and_redacts_validation(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        assert change(client, app, session, secret, currentPassword="wrong").status_code == 401
        assert client.get(URL).json()["policy"]["loginTotpBypass"] is False
        wrong = next(str(i).zfill(6) for i in range(10) if str(i).zfill(6) not in
                     {pyotp.TOTP(secret).at(BASE_TIME + offset) for offset in (0,30,60)})
        assert change(client, app, session, secret, totpCode=wrong).status_code == 401
        assert change(client, app, session, secret, offset=0).json()["error"]["code"] == "admin_totp_replayed"
        payload = {"loginTotpBypass": True, "currentPassword": CHANGED_PASSWORD, "totpCode": pyotp.TOTP(secret).at(BASE_TIME+30)}
        assert client.put(URL, json=payload).status_code == 403
        invalid = client.put(URL, headers={"X-CSRF-Token": session["csrfToken"]}, json=payload | {"totpCode": "１２３４５６"})
        assert invalid.status_code == 422
        assert CHANGED_PASSWORD not in invalid.text and "１２３４５６" not in invalid.text
        assert client.get(URL).json()["policy"]["loginTotpBypass"] is False


def test_ordinary_admin_and_business_key_cannot_change_policy(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        assert client.get(URL).status_code == 401
        assert client.put(URL, headers={"Authorization": "Bearer vap_live_fake"}, json={
            "loginTotpBypass": True, "currentPassword": CHANGED_PASSWORD, "totpCode": "123456"}).status_code == 401
        enroll_super(client, app)
        with app.state.database.connect() as connection:
            connection.execute("INSERT INTO admin_users(id,username,username_normalized,display_name,password_hash,role,must_change_password,login_totp_bypass) "
                "VALUES('ordinary','ordinary','ordinary','Ordinary',?,'admin',0,1)", (app.state.admin_auth.password_hasher.hash(CHANGED_PASSWORD),))
        ordinary = TestClient(app)
        logged = ordinary.post("/api/internal/auth/login", json={"username": "ordinary", "password": CHANGED_PASSWORD})
        assert logged.status_code == 200 and logged.json()["user"]["loginTotpBypass"] is False
        assert ordinary.get(URL).status_code == 403
        response = ordinary.put(URL, headers={"X-CSRF-Token": logged.json()["csrfToken"]}, json={
            "loginTotpBypass": True, "currentPassword": CHANGED_PASSWORD, "totpCode": "123456"})
        assert response.status_code == 403 and response.json()["error"]["code"] == "super_admin_required"


def test_old_database_migration_is_idempotent_and_default_requires_totp(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        with app.state.database.connect() as connection:
            connection.execute("ALTER TABLE admin_users DROP COLUMN login_totp_bypass")
        app.state.database.initialize()
        app.state.database.initialize()
        assert client.get(URL).json()["policy"]["loginTotpBypass"] is False
        assert change(client, app, session, secret).status_code == 200
        app.state.database.initialize()
        assert client.get(URL).json()["policy"]["loginTotpBypass"] is True


def test_cli_totp_reset_turns_off_bypass_and_requires_enrollment_again(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        assert change(client, app, session, secret).status_code == 200
        app.state.admin_auth.reset_totp_from_cli("owner")
        login = client.post("/api/internal/auth/login", json={"username": "owner", "password": CHANGED_PASSWORD})
        assert login.json()["user"]["loginTotpBypass"] is False
        assert login.json()["user"]["mfaSetupRequired"] is True
        assert client.get(URL).json()["error"]["code"] == "totp_setup_required"


def test_bypass_never_skips_password_lockout_or_sensitive_totp(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        assert change(client, app, session, secret).status_code == 200
        client.post("/api/internal/auth/logout", headers={"X-CSRF-Token": session["csrfToken"]})
        for _ in range(app.state.settings.admin_login_max_failures):
            response = client.post("/api/internal/auth/login", json={"username":"owner","password":"wrong"})
        assert response.status_code == 429
        assert client.post("/api/internal/auth/login", json={"username":"owner","password":CHANGED_PASSWORD}).status_code == 429


def test_concurrent_policy_change_cannot_complete_password_only_login(tmp_path, monkeypatch):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        assert change(client, app, session, secret).status_code == 200
        service = app.state.admin_auth
        original = type(service.password_hasher).verify
        def raced(hasher, *args, **kwargs):
            result = original(hasher, *args, **kwargs)
            with app.state.database.connect() as connection:
                connection.execute("UPDATE admin_users SET login_totp_bypass=0 WHERE username='owner'")
            return result
        monkeypatch.setattr(type(service.password_hasher), "verify", raced)
        response = client.post("/api/internal/auth/login", json={"username":"owner","password":CHANGED_PASSWORD})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "admin_login_state_changed"


@pytest.mark.parametrize("mutation", ["session", "password", "totp"])
def test_concurrent_credentials_or_session_change_prevents_policy_write(tmp_path, monkeypatch, mutation):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, _ = enroll_super(client, app)
        service = app.state.admin_auth
        original = service.verify_sensitive_totp
        def raced(actor, *args, **kwargs):
            original(actor, *args, **kwargs)
            with app.state.database.connect() as connection:
                if mutation == "session": connection.execute("UPDATE admin_sessions SET revoked_at=? WHERE id=?", (BASE_TIME+30,actor.session_id))
                elif mutation == "password": connection.execute("UPDATE admin_users SET password_hash='changed' WHERE id=?", (actor.id,))
                else: connection.execute("UPDATE admin_users SET totp_secret_encrypted=? WHERE id=?", (service._encrypt_secret(pyotp.random_base32()),actor.id))
        monkeypatch.setattr(service, "verify_sensitive_totp", raced)
        response = change(client, app, session, secret)
        assert response.status_code == 401 and response.json()["error"]["code"] == "admin_login_state_changed"
        with app.state.database.connect() as connection:
            assert connection.execute("SELECT login_totp_bypass FROM admin_users WHERE username='owner'").fetchone()[0] == 0


def test_bypass_login_can_still_explicitly_verify_totp_or_recovery(tmp_path):
    app = create_app(build_settings(tmp_path / "app.db"))
    with TestClient(app) as client:
        session, secret, codes = enroll_super(client, app)
        assert change(client, app, session, secret).status_code == 200
        app.state.admin_auth.clock = lambda: BASE_TIME+60
        for extra in ({"totpCode": pyotp.TOTP(secret).at(BASE_TIME+60)}, {"recoveryCode": codes[0]}):
            result=client.post("/api/internal/auth/login",json={"username":"owner","password":CHANGED_PASSWORD,**extra})
            assert result.status_code == 200 and result.json()["session"]["mfaVerified"] is True
