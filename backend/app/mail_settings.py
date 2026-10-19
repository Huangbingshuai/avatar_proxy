"""Disk alert mail settings. Only ciphertext is persisted; the key stays on disk."""

import ipaddress
import json
import os
from email.utils import parseaddr
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field, SecretStr

from .config import Settings
from .database import Database
from .errors import ApiError


LEGACY_MAIL_ENV_KEYS = frozenset({
    "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL",
    "ALERT_EMAIL_RECIPIENTS", "SMTP_SECURITY", "SMTP_TIMEOUT_SECONDS",
})

# Fixed TLS presets. Custom/enterprise domains remain available in advanced mode.
MAIL_PROVIDERS = {
    "qq": {"label": "QQ 邮箱", "host": "smtp.qq.com", "domains": ["qq.com", "foxmail.com"],
           "helpUrl": "https://service.mail.qq.com/detail/0/75"},
    "163": {"label": "网易 163", "host": "smtp.163.com", "domains": ["163.com"],
            "helpUrl": "https://help.mail.126.com/"},
    "126": {"label": "网易 126", "host": "smtp.126.com", "domains": ["126.com"],
            "helpUrl": "https://help.mail.126.com/"},
    "yeah": {"label": "网易 Yeah", "host": "smtp.yeah.net", "domains": ["yeah.net"],
             "helpUrl": "https://help.mail.126.com/"},
}


def valid_email(value: str) -> bool:
    if not value or any(char in value for char in "\r\n"):
        return False
    _, address = parseaddr(value)
    local, separator, domain = address.rpartition("@")
    return bool(address == value and separator and local and "." in domain
                and not any(char.isspace() for char in address))


class MailServer(BaseModel):
    host: str = ""
    port: int = Field(default=465, ge=1, le=65535)
    username: str = ""
    password: SecretStr = Field(default_factory=lambda: SecretStr(""))
    from_email: str = ""
    security: Literal["ssl", "starttls"] = "ssl"
    timeout_seconds: float = Field(default=10, gt=0, le=30)


class MailConfiguration(MailServer):
    enabled: bool = False
    recipients: list[str] = Field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.host and valid_email(self.from_email)
                    and self.recipients and all(valid_email(item) for item in self.recipients)
                    and bool(self.username) == bool(self.password.get_secret_value()))


class MailAccount(MailServer):
    id: str
    provider: Literal["qq", "163", "126", "yeah", "custom"] = "custom"


class MailSettingsDocument(BaseModel):
    version: Literal[2] = 2
    enabled: bool = False
    recipients: list[str] = Field(default_factory=list)
    active_account_id: str | None = None
    accounts: list[MailAccount] = Field(default_factory=list)

    def active(self) -> MailConfiguration:
        account = next((item for item in self.accounts if item.id == self.active_account_id), None)
        server = account.model_dump(exclude={"id", "provider"}) if account else {}
        return MailConfiguration(**server, enabled=self.enabled and account is not None, recipients=self.recipients)


class MailSettingsStore:
    KEY_FILE_NAME = "smtp_settings.key"

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.key_path = database.path.parent / self.KEY_FILE_NAME
        self._migrate_legacy(settings)

    def _cipher(self) -> Fernet:
        try:
            if self.key_path.is_symlink():
                raise ValueError("symlink")
            if not self.key_path.exists():
                with self.database.connect() as connection:
                    if connection.execute("SELECT 1 FROM system_monitor_email_settings").fetchone():
                        raise ValueError("missing key for existing settings")
                self.key_path.parent.mkdir(parents=True, exist_ok=True)
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                try:
                    descriptor = os.open(self.key_path, flags, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(Fernet.generate_key())
                        output.flush()
                        os.fsync(output.fileno())
            return Fernet(self.key_path.read_bytes().strip())
        except (OSError, ValueError, TypeError) as error:
            raise ApiError("邮件配置密钥不可用，请恢复 smtp_settings.key", 503,
                           "mail_encryption_key_unavailable") from error

    def _encrypt(self, config: MailConfiguration | MailSettingsDocument) -> str:
        data = config.model_dump(mode="json")
        if isinstance(config, MailSettingsDocument):
            for item, account in zip(data["accounts"], config.accounts):
                item["password"] = account.password.get_secret_value()
        else:
            data["password"] = config.password.get_secret_value()
        return self._cipher().encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()

    def load(self, connection=None) -> MailConfiguration:
        return self.document(connection).active()

    @staticmethod
    def _from_single(config: MailConfiguration) -> MailSettingsDocument:
        server = config.model_dump(exclude={"enabled", "recipients"})
        provider = next((key for key, value in MAIL_PROVIDERS.items()
                         if config.host == value["host"] and config.port == 465 and config.security == "ssl"
                         and config.username == config.from_email
                         and config.from_email.rpartition("@")[2].lower() in value["domains"]), "custom")
        return MailSettingsDocument(enabled=config.enabled, recipients=config.recipients,
            active_account_id="mail_legacy", accounts=[MailAccount(id="mail_legacy", provider=provider, **server)])

    def document(self, connection=None) -> MailSettingsDocument:
        if connection is None:
            with self.database.connect() as owned:
                return self.document(owned)
        row = connection.execute("SELECT config_ciphertext FROM system_monitor_email_settings WHERE id=1").fetchone()
        if row is None:
            return MailSettingsDocument()
        try:
            data = json.loads(self._cipher().decrypt(row[0].encode()))
            if not isinstance(data, dict) or ("version" in data and data["version"] != 2):
                raise ValueError("unsupported mail settings format")
            if data.get("version") == 2:
                return MailSettingsDocument.model_validate(data)
            return self._from_single(MailConfiguration.model_validate(data))
        except (InvalidToken, ValueError, TypeError) as error:
            raise ApiError("邮件配置无法解密，请恢复原密钥", 503, "mail_settings_decrypt_failed") from error

    def _migrate_legacy(self, settings: Settings) -> None:
        with self.database.connect() as connection:
            if connection.execute("SELECT 1 FROM system_monitor_email_settings WHERE id=1").fetchone():
                return
        if not any((settings.smtp_host, settings.smtp_username, settings.smtp_password,
                    settings.smtp_from_email, settings.alert_email_recipients)):
            return
        config = MailConfiguration(
            enabled=True, host=settings.smtp_host.strip(), port=settings.smtp_port,
            username=settings.smtp_username.strip(), password=settings.smtp_password or SecretStr(""),
            from_email=settings.smtp_from_email.strip(), recipients=settings.alert_email_recipient_list,
            security=settings.smtp_security, timeout_seconds=settings.smtp_timeout_seconds,
        )
        ciphertext = self._encrypt(config)
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO system_monitor_email_settings(id,config_ciphertext,source) VALUES(1,?,'legacy_env')",
                (ciphertext,),
            )

    def public(self) -> dict:
        document = self.document()
        config = document.active()
        with self.database.connect() as connection:
            row = connection.execute("SELECT source,updated_at FROM system_monitor_email_settings WHERE id=1").fetchone()
        return {
            "enabled": config.enabled, "host": config.host, "port": config.port,
            "username": config.username, "fromEmail": config.from_email,
            "recipients": config.recipients, "security": config.security,
            "timeoutSeconds": config.timeout_seconds,
            "passwordConfigured": bool(config.password.get_secret_value()),
            "configured": config.configured, "source": row["source"] if row else "unconfigured",
            "updatedAt": row["updated_at"] if row else None,
            "activeAccountId": document.active_account_id,
            "accounts": [{"id": item.id, "provider": item.provider, "host": item.host,
                "port": item.port, "username": item.username, "fromEmail": item.from_email,
                "security": item.security, "timeoutSeconds": item.timeout_seconds,
                "passwordConfigured": bool(item.password.get_secret_value())} for item in document.accounts],
            "providers": [{"id": key, **value, "port": 465, "security": "ssl"}
                          for key, value in MAIL_PROVIDERS.items()],
        }

    def update(self, payload, *, actor_id: str, actor: str,
               source_ip: str | None, user_agent: str | None) -> dict:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            document = self.document(connection)
            previous = document.active()
            if payload.accounts is not None:
                updated = self._update_accounts(document, payload)
                password_changed = any(item.password or item.clear_password for item in payload.accounts)
            else:
                # Compatibility with the first single-account panel/API. Do not
                # discard additional saved accounts when an older client saves.
                if document.accounts and not document.active_account_id:
                    previous = MailConfiguration(**document.accounts[0].model_dump(exclude={"id", "provider"}),
                        enabled=document.enabled, recipients=document.recipients)
                config = self._updated_server(previous, payload)
                config = MailConfiguration(**config, enabled=payload.enabled,
                    recipients=self._recipients(payload.recipients))
                self._validate(config)
                account_id = document.active_account_id or (document.accounts[0].id if document.accounts else "mail_legacy")
                account = MailAccount(id=account_id, **config.model_dump(exclude={"enabled", "recipients"}))
                accounts = [item for item in document.accounts if item.id != account_id] + [account]
                updated = MailSettingsDocument(enabled=config.enabled, recipients=config.recipients,
                    active_account_id=account_id, accounts=accounts)
                password_changed = bool(payload.password or payload.clear_password)
            ciphertext = self._encrypt(updated)
            connection.execute(
                "INSERT INTO system_monitor_email_settings(id,config_ciphertext,source) VALUES(1,?,'panel') "
                "ON CONFLICT(id) DO UPDATE SET config_ciphertext=excluded.config_ciphertext,"
                "source='panel',updated_at=CURRENT_TIMESTAMP", (ciphertext,),
            )
            self.database.write_admin_audit(
                actor_id=actor_id, actor=actor, source_ip=source_ip, user_agent=user_agent,
                action="admin.system_monitor.email.settings.update", target_type="system_monitor", target_id="email",
                before={"enabled": previous.enabled, "recipientCount": len(previous.recipients)},
                after={"enabled": updated.enabled, "recipientCount": len(updated.recipients),
                       "accountCount": len(updated.accounts), "passwordChanged": password_changed}, connection=connection,
            )
        return self.public()

    @staticmethod
    def _recipients(values: list[str]) -> list[str]:
        # Email local parts may be case-sensitive. Normalize only the domain.
        cleaned = (value.strip() for value in values if value.strip())
        return list(dict.fromkeys(local + "@" + domain.lower() if separator else local
                    for local, separator, domain in (value.rpartition("@") for value in cleaned)))

    @staticmethod
    def _updated_server(previous: MailServer, payload) -> dict:
        supplied_password = payload.password.get_secret_value() if payload.password else ""
        if payload.clear_password and supplied_password:
            raise ApiError("不能同时清除和设置授权码", 422, "mail_password_conflict")
        if (previous.password.get_secret_value() and not supplied_password and not payload.clear_password
                and (payload.host.strip() != previous.host or payload.username.strip() != previous.username)):
            raise ApiError("修改SMTP服务器或登录账号时，请重新填写授权码", 422, "mail_password_required")
        password = (SecretStr("") if payload.clear_password else
                    payload.password if supplied_password else previous.password)
        return MailServer(host=payload.host.strip(), port=payload.port,
            username=payload.username.strip(), password=password,
            from_email=payload.from_email.strip(),
            security=payload.security, timeout_seconds=payload.timeout_seconds,
        ).model_dump()

    def _update_accounts(self, previous: MailSettingsDocument, payload) -> MailSettingsDocument:
        recipients = self._recipients(payload.recipients)
        if any(not valid_email(item) for item in recipients):
            raise ApiError("收件邮箱格式无效", 422, "mail_recipients_invalid")
        old_accounts = {item.id: item for item in previous.accounts}
        accounts = []
        ids = set()
        identities = set()
        for item in payload.accounts:
            if item.id in ids:
                raise ApiError("发件账号标识不能重复", 422, "mail_account_duplicate")
            ids.add(item.id)
            if item.provider != "custom":
                preset = MAIL_PROVIDERS[item.provider]
                address = item.from_email.strip()
                if not valid_email(address) or address.rpartition("@")[2].lower() not in preset["domains"]:
                    raise ApiError("邮箱地址与所选服务不匹配，请选择对应服务或自定义SMTP", 422, "mail_provider_mismatch")
                # Never trust client-provided hosts/ports for named presets.
                item = item.model_copy(update={"host": preset["host"], "port": 465,
                    "security": "ssl", "username": address, "from_email": address, "timeout_seconds": 10})
            server = self._updated_server(old_accounts.get(item.id, MailServer()), item)
            config = MailConfiguration(**server, enabled=True, recipients=recipients or ["validation@example.test"])
            self._validate(config)
            identity = (config.host.lower(), config.username, config.from_email)
            if identity in identities:
                raise ApiError("该发件邮箱已添加，无需重复配置", 422, "mail_account_duplicate")
            identities.add(identity)
            accounts.append(MailAccount(id=item.id, provider=item.provider, **server))
        if payload.active_account_id is not None and payload.active_account_id not in ids:
            raise ApiError("请选择已保存的发件邮箱", 422, "mail_active_account_invalid")
        updated = MailSettingsDocument(enabled=payload.enabled, recipients=recipients,
            active_account_id=payload.active_account_id, accounts=accounts)
        if payload.enabled:
            self._validate(updated.active())
            if not updated.active().configured:
                raise ApiError("请添加发件邮箱、选择当前发件账号并设置收件人", 422, "mail_settings_incomplete")
        return updated

    @staticmethod
    def _validate(config: MailConfiguration) -> None:
        if config.host:
            try:
                ipaddress.ip_address(config.host)
            except ValueError:
                import re
                if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", config.host):
                    raise ApiError("SMTP服务器请填写主机名或IP，不包含协议和端口", 422, "mail_host_invalid")
        if any(char in config.username for char in "\r\n"):
            raise ApiError("SMTP登录账号格式无效", 422, "mail_username_invalid")
        if config.from_email and not valid_email(config.from_email):
            raise ApiError("发件邮箱格式无效", 422, "mail_sender_invalid")
        if any(not valid_email(item) for item in config.recipients):
            raise ApiError("收件邮箱格式无效", 422, "mail_recipients_invalid")
        if config.enabled and not config.configured:
            raise ApiError("请完整填写SMTP服务器、发件邮箱、收件人及匹配的账号授权码", 422, "mail_settings_incomplete")
