import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.errors import ApiError
from app.mail_settings import MailSettingsStore
from app.main import create_app
from app.schemas import AdminMonitorEmailSettingsUpdate
from app.system_monitor import DiskMonitor
from conftest import ADMIN_HEADERS, build_settings
from scripts.migrate_monitor_email import remove_legacy_values
from test_admin_security_deep import CHANGED_PASSWORD, enroll_super


MAIL = {"enabled": True, "host": "smtp.example.test", "port": 465,
        "username": "alerts@example.test", "password": "mail-test-secret",
        "fromEmail": "alerts@example.test", "recipients": ["ops@example.test"],
        "security": "ssl", "currentPassword": CHANGED_PASSWORD}


def make_store(tmp_path: Path, **overrides):
    settings = build_settings(tmp_path / "app.db", **overrides)
    database = Database(settings.database_path)
    database.initialize()
    return database, MailSettingsStore(database, settings)


def update(store, **changes):
    return store.update(AdminMonitorEmailSettingsUpdate(**(MAIL | changes)), actor_id="owner",
                        actor="owner", source_ip=None, user_agent="pytest")


def test_legacy_import_is_encrypted_idempotent_and_survives_without_environment(tmp_path):
    database, store = make_store(tmp_path, smtp_host="smtp.example.test",
        smtp_username="alerts@example.test", smtp_password="legacy-secret",
        smtp_from_email="alerts@example.test", alert_email_recipients="ops@example.test; owner@example.test")
    assert store.public()["source"] == "legacy_env"
    assert store.public()["configured"] is True
    assert store.public()["passwordConfigured"] is True
    assert "legacy-secret" not in json.dumps(store.public())
    raw = database.path.read_bytes()
    for value in (b"legacy-secret", b"smtp.example.test", b"alerts@example.test", b"ops@example.test"):
        assert value not in raw
    if os.name != "nt":
        assert store.key_path.stat().st_mode & 0o777 == 0o600
    settings = build_settings(database.path)
    restarted = MailSettingsStore(database, settings)
    assert restarted.load().password.get_secret_value() == "legacy-secret"
    assert restarted.public()["recipients"] == ["ops@example.test", "owner@example.test"]
    update(restarted)
    MailSettingsStore(database, build_settings(database.path, smtp_password="do-not-import"))
    assert restarted.load().password.get_secret_value() == "mail-test-secret"
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM system_monitor_email_settings").fetchone()[0] == 1
        assert "mail-test-secret" not in str(connection.execute("SELECT * FROM admin_audit_logs").fetchall())


def test_password_keep_replace_clear_and_credentials_never_follow_changed_host(tmp_path):
    _, store = make_store(tmp_path)
    update(store)
    update(store, password=None, recipients=[" ops@example.test ", "ops@example.test"])
    assert store.load().password.get_secret_value() == MAIL["password"]
    assert store.public()["recipients"] == ["ops@example.test"]
    with pytest.raises(ApiError, match="重新填写"):
        update(store, password=None, host="other.example.test")
    update(store, password="new-secret", host="other.example.test")
    assert store.load().password.get_secret_value() == "new-secret"
    update(store, enabled=False, password=None, clearPassword=True, host="", username="")
    assert store.public()["passwordConfigured"] is False
    assert store.public()["configured"] is False


@pytest.mark.parametrize("changes", [
    {"host": "https://smtp.example.test"}, {"host": "smtp.example.test\nattack"},
    {"username": "account\nattack"}, {"fromEmail": "bad"},
    {"recipients": ["ops@example.test\r\nBcc:evil@example.test"]},
    {"host": ""}, {"password": None}, {"clearPassword": True},
])
def test_invalid_settings_leave_saved_configuration_unchanged(tmp_path, changes):
    _, store = make_store(tmp_path)
    with pytest.raises(ApiError):
        update(store, **changes)
    assert store.public()["source"] == "unconfigured"


def test_missing_or_invalid_key_preserves_ciphertext_and_fails_closed(tmp_path):
    database, store = make_store(tmp_path)
    update(store)
    original_key = store.key_path.read_bytes()
    store.key_path.unlink()
    with pytest.raises(ApiError) as error:
        store.load()
    assert error.value.code == "mail_encryption_key_unavailable"
    assert not store.key_path.exists()
    store.key_path.write_bytes(b"invalid")
    with pytest.raises(ApiError):
        store.load()
    from cryptography.fernet import Fernet
    store.key_path.write_bytes(Fernet.generate_key())
    with pytest.raises(ApiError) as error:
        store.load()
    assert error.value.code == "mail_settings_decrypt_failed"
    store.key_path.write_bytes(original_key)
    assert MailSettingsStore(database, build_settings(database.path)).load().configured


def test_api_requires_super_admin_csrf_and_password_and_redacts_validation(tmp_path):
    app = create_app(build_settings(tmp_path / "api.db"))
    url = "/api/internal/admin/system-monitor/email/settings"
    with TestClient(app) as client:
        session, _, _ = enroll_super(client, app)
        headers = {"X-CSRF-Token": session["csrfToken"]}
        assert client.put(url, json=MAIL).status_code == 403
        assert client.put(url, headers=headers, json=MAIL | {"currentPassword": "wrong"}).status_code == 401
        invalid = client.put(url, headers=headers, json=MAIL | {"port": -1})
        assert invalid.status_code == 422
        assert MAIL["password"] not in invalid.text
        assert CHANGED_PASSWORD not in invalid.text
        saved = client.put(url, headers=headers, json=MAIL)
        assert saved.status_code == 200
        assert saved.json()["email"]["configured"] is True
        assert "password" not in saved.json()["email"]
        assert MAIL["password"] not in saved.text
        status = client.get("/api/internal/admin/system-monitor/status")
        assert status.json()["settings"]["email"]["host"] == MAIL["host"]
        with app.state.database.connect() as connection:
            audit = connection.execute("SELECT after_json FROM admin_audit_logs "
                "WHERE action='admin.system_monitor.email.settings.update'").fetchone()[0]
            assert MAIL["password"] not in audit
        assert app.state.system_monitor.email_configured
        client.put(url, headers=headers, json=MAIL | {"enabled": False, "password": None})
        assert app.state.system_monitor.email_configured is False
    ordinary_app = create_app(build_settings(tmp_path / "ordinary.db"))
    with TestClient(ordinary_app) as client:
        assert client.put(url, headers=ADMIN_HEADERS, json=MAIL).status_code == 403


def test_dotenv_cleanup_preserves_unrelated_values_and_handles_multiline(tmp_path):
    path = tmp_path / "legacy.env"
    path.write_text('# keep\nDATABASE_PATH=./app.db\nSMTP_HOST=smtp.example.test\n'
                    'export SMTP_PASSWORD="first\nsecond"\nOTHER="untouched"\n', encoding="utf-8")
    assert remove_legacy_values(path) == 2
    assert path.read_text() == '# keep\nDATABASE_PATH=./app.db\nOTHER="untouched"\n'
    assert remove_legacy_values(path) == 0
    path.write_text('SMTP_PASSWORD="unterminated', encoding="utf-8")
    with pytest.raises(RuntimeError):
        remove_legacy_values(path)
    assert path.read_text() == 'SMTP_PASSWORD="unterminated'


def test_migration_command_removes_legacy_values_only_after_verified_import(tmp_path, monkeypatch, capsys):
    import sys
    from app.mail_settings import LEGACY_MAIL_ENV_KEYS
    from scripts.migrate_monitor_email import main
    for key in LEGACY_MAIL_ENV_KEYS | {"DATABASE_PATH"}:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "legacy.env"
    database_path = tmp_path / "migration.db"
    path.write_text(f'DATABASE_PATH={database_path.as_posix()}\n'
        'SMTP_HOST=smtp.example.test\nSMTP_USERNAME=alerts@example.test\n'
        'SMTP_PASSWORD=migration-secret\nSMTP_FROM_EMAIL=alerts@example.test\n'
        'ALERT_EMAIL_RECIPIENTS=ops@example.test\nSYSTEM_MONITOR_ENABLED=false\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["migrate", "--env-file", str(path), "--remove-legacy"])
    main()
    assert path.read_text() == f'DATABASE_PATH={database_path.as_posix()}\nSYSTEM_MONITOR_ENABLED=false\n'
    main()
    output = capsys.readouterr().out
    assert "configured=True" in output
    assert "migration-secret" not in output
    assert "alerts@example.test" not in output
    store = MailSettingsStore(Database(database_path), build_settings(database_path))
    assert store.load().password.get_secret_value() == "migration-secret"


def test_saved_settings_apply_to_smtp_without_restarting_monitor(tmp_path, monkeypatch):
    import smtplib
    database, store = make_store(tmp_path)
    monitor = DiskMonitor(database, build_settings(database.path))
    events = []
    class FakeSmtp:
        def __init__(self, host, port, **kwargs):
            events.append((host, port))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def login(self, username, password):
            events.append((username, password))
        def send_message(self, message, **kwargs):
            events.append(kwargs["to_addrs"])
            return {}
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    update(store)
    monitor._send_email_sync("test", "test")
    update(store, host="new.example.test", password="rotated-secret", recipients=["new@example.test"])
    monitor._send_email_sync("test", "test")
    assert events[-3:] == [("new.example.test", 465), (MAIL["username"], "rotated-secret"), ["new@example.test"]]
    update(store, enabled=False, password=None, host="new.example.test")
    with pytest.raises(ApiError) as error:
        monitor._send_email_sync("test", "test")
    assert error.value.code == "alert_email_not_configured"


def multi_update(store, accounts, **changes):
    payload = {"enabled": True, "recipients": ["ops@qq.com", "owner@163.com"],
               "accounts": accounts, "activeAccountId": accounts[0]["id"] if accounts else None,
               "currentPassword": CHANGED_PASSWORD} | changes
    return store.update(AdminMonitorEmailSettingsUpdate(**payload), actor_id="owner",
        actor="owner", source_ip=None, user_agent="pytest")


def account(identifier="qq_1", provider="qq", address="sender@qq.com", **extra):
    return {"id": identifier, "provider": provider, "fromEmail": address, "password": "secret-" + identifier} | extra


@pytest.mark.parametrize("provider,domain,host", [
    ("qq", "qq.com", "smtp.qq.com"), ("qq", "foxmail.com", "smtp.qq.com"),
    ("163", "163.com", "smtp.163.com"), ("126", "126.com", "smtp.126.com"),
    ("yeah", "yeah.net", "smtp.yeah.net"),
])
def test_named_providers_set_server_and_credentials_safely(tmp_path, provider, domain, host):
    database, store = make_store(tmp_path)
    response = multi_update(store, [account(provider=provider, address="sender@" + domain,
        host="attacker.example.test", port=587, security="starttls", username="attacker", timeoutSeconds=29)])
    assert store.load().host == host
    assert store.load().port == 465
    assert store.load().security == "ssl"
    assert store.load().timeout_seconds == 10
    assert store.load().username == "sender@" + domain
    assert response["activeAccountId"] == "qq_1"
    assert response["accounts"][0]["passwordConfigured"] is True
    assert "secret-qq_1" not in json.dumps(response)
    assert b"secret-qq_1" not in database.path.read_bytes()


def test_accounts_migrate_preserve_independent_secrets_and_only_selected_sends(tmp_path, monkeypatch):
    import smtplib
    database, store = make_store(tmp_path, smtp_host="smtp.qq.com", smtp_username="legacy@qq.com",
        smtp_from_email="legacy@qq.com", smtp_password="legacy-secret", alert_email_recipients="ops@example.test")
    assert store.public()["accounts"][0]["provider"] == "qq"
    legacy = {key: value for key, value in store.public()["accounts"][0].items() if key != "passwordConfigured"}
    multi_update(store, [legacy, account("netease", "163", "alerts@163.com")], activeAccountId="netease")
    restarted = MailSettingsStore(database, build_settings(database.path, smtp_password="ignored-legacy"))
    assert restarted.document().accounts[0].password.get_secret_value() == "legacy-secret"
    assert restarted.load().password.get_secret_value() == "secret-netease"
    assert len(restarted.public()["accounts"]) == 2
    sent = []
    class Smtp:
        def __init__(self, host, port, **kwargs): sent.append(host)
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def login(self, username, password): sent.append((username, password))
        def send_message(self, message, **kwargs): sent.append(kwargs["to_addrs"]); return {}
    monkeypatch.setattr(smtplib, "SMTP_SSL", Smtp)
    monitor = DiskMonitor(database, build_settings(database.path))
    monitor._send_email_sync("one", "one")
    assert sent == ["smtp.163.com", ("alerts@163.com", "secret-netease"), ["ops@qq.com", "owner@163.com"]]
    accounts = [{key: value for key, value in item.items() if key != "passwordConfigured"}
                for item in restarted.public()["accounts"]]
    multi_update(store, accounts, activeAccountId="mail_legacy")
    monitor._send_email_sync("two", "two")
    assert sent[-3:-1] == ["smtp.qq.com", ("legacy@qq.com", "legacy-secret")]
    # Legacy client saves still preserve all other saved accounts.
    update(store, host="smtp.qq.com", username="legacy@qq.com", fromEmail="legacy@qq.com", password=None)
    assert len(store.public()["accounts"]) == 2
    assert store.document().accounts[0].password.get_secret_value() == "secret-netease"


@pytest.mark.parametrize("accounts,changes,code", [
    ([account(address="wrong@163.com")], {}, "mail_provider_mismatch"),
    ([account(), account()], {}, "mail_account_duplicate"),
    ([account(), account("second")], {}, "mail_account_duplicate"),
    ([account(password=None)], {}, "mail_settings_incomplete"),
    ([account()], {"activeAccountId": "missing"}, "mail_active_account_invalid"),
    ([account()], {"activeAccountId": None}, "mail_settings_incomplete"),
    ([account()], {"recipients": []}, "mail_settings_incomplete"),
    ([account()], {"recipients": ["invalid\r\nBcc: evil@example.test"]}, "mail_recipients_invalid"),
    ([account(password="new", clearPassword=True)], {}, "mail_password_conflict"),
])
def test_invalid_account_changes_are_atomic(tmp_path, accounts, changes, code):
    _, store = make_store(tmp_path)
    update(store)
    before = store.public()
    with pytest.raises(ApiError) as error:
        multi_update(store, accounts, **changes)
    assert error.value.code == code
    assert store.public() == before


def test_account_identity_change_never_reuses_secret_and_removed_secret_is_gone(tmp_path):
    database, store = make_store(tmp_path)
    multi_update(store, [account(), account("netease", "163", "alerts@163.com")])
    with pytest.raises(ApiError) as error:
        multi_update(store, [account(address="new@qq.com", password=None)])
    assert error.value.code == "mail_password_required"
    multi_update(store, [account(address="new@qq.com", password="rotated"),
                         account("netease", "163", "alerts@163.com", password=None)])
    assert store.document().accounts[1].password.get_secret_value() == "secret-netease"
    multi_update(store, [account("netease", "163", "alerts@163.com", password=None)],
                 recipients=[" ops@QQ.COM ", "ops@qq.com", "owner@163.com"])
    assert store.public()["recipients"] == ["ops@qq.com", "owner@163.com"]
    assert [item.id for item in store.document().accounts] == ["netease"]
    assert "rotated" not in json.dumps(store.public())
    multi_update(store, [], enabled=False, recipients=[])
    assert store.public()["accounts"] == []
    assert not store.load().configured
    database.initialize()
    assert not store.public()["enabled"]


def test_custom_servers_and_disabled_saved_accounts_remain_available(tmp_path):
    _, store = make_store(tmp_path)
    custom = account("custom", "custom", "sender@example.test", host="smtp.example.test",
        username="sender@example.test", port=587, security="starttls", timeoutSeconds=15)
    multi_update(store, [custom], enabled=False)
    assert not store.load().configured
    assert store.public()["accounts"][0]["port"] == 587
    multi_update(store, [custom | {"password": None}])
    assert store.load().configured
    multi_update(store, [custom | {"password": None, "clearPassword": True, "username": ""}])
    assert not store.public()["passwordConfigured"]
    assert store.load().configured


def test_legacy_client_cannot_erase_inactive_account_secret(tmp_path):
    _, store = make_store(tmp_path)
    multi_update(store, [account()], enabled=False, activeAccountId=None)
    with pytest.raises(ApiError) as error:
        update(store, enabled=False, host="", username="", fromEmail="", password=None)
    assert error.value.code == "mail_password_required"
    assert store.document().accounts[0].password.get_secret_value() == "secret-qq_1"
    update(store, host="smtp.qq.com", username="sender@qq.com", fromEmail="sender@qq.com", password=None)
    assert len(store.public()["accounts"]) == 1
    assert store.load().password.get_secret_value() == "secret-qq_1"


@pytest.mark.parametrize("document", [{"version": 3}, ["invalid"]])
def test_unsupported_encrypted_document_fails_closed(tmp_path, document):
    database, store = make_store(tmp_path)
    update(store)
    encrypted = store._cipher().encrypt(json.dumps(document).encode()).decode()
    with database.connect() as connection:
        connection.execute("UPDATE system_monitor_email_settings SET config_ciphertext=?", (encrypted,))
    with pytest.raises(ApiError) as error:
        store.load()
    assert error.value.code == "mail_settings_decrypt_failed"


def test_multi_account_api_redacts_nested_secrets_and_enforces_limits(tmp_path):
    app = create_app(build_settings(tmp_path / "api.db"))
    url = "/api/internal/admin/system-monitor/email/settings"
    with TestClient(app) as client:
        session, _, _ = enroll_super(client, app)
        headers = {"X-CSRF-Token": session["csrfToken"]}
        payload = {"enabled": True, "accounts": [account()], "activeAccountId": "qq_1",
            "recipients": ["ops@163.com"], "currentPassword": CHANGED_PASSWORD}
        response = client.put(url, headers=headers, json=payload)
        assert response.status_code == 200
        assert "secret-qq_1" not in response.text
        invalid = client.put(url, headers=headers, json=payload | {"accounts": [account(port=-1)]})
        assert invalid.status_code == 422
        assert "secret-qq_1" not in invalid.text
        assert CHANGED_PASSWORD not in invalid.text
        assert client.put(url, headers=headers, json=payload | {"accounts": [account(str(i)) for i in range(11)]}).status_code == 422
        assert client.put(url, headers=headers, json=payload | {"recipients": [f"a{i}@qq.com" for i in range(51)]}).status_code == 422
        assert client.put(url, json=payload).status_code == 403
