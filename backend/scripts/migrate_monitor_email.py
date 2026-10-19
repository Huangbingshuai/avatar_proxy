"""Import legacy SMTP settings and optionally remove only those dotenv assignments.

Never prints configuration values and never sends mail. Back up the environment
file before running with --remove-legacy. Run from the backend directory.
"""

import argparse
import os
import stat
import tempfile
from pathlib import Path

from dotenv.parser import parse_stream

from app.config import Settings
from app.database import Database
from app.mail_settings import LEGACY_MAIL_ENV_KEYS, MailSettingsStore


def remove_legacy_values(path: Path) -> int:
    """Preserve unrelated settings/comments, including multiline dotenv values."""
    path = path.resolve(strict=True)
    with path.open(encoding="utf-8", newline="") as source:
        bindings = list(parse_stream(source))
    if any(item.error for item in bindings):
        raise RuntimeError("Environment file contains invalid assignments; no values removed")
    removed = sum(item.key in LEGACY_MAIL_ENV_KEYS for item in bindings)
    if not removed:
        return 0
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            os.chmod(temporary, mode)
            for item in bindings:
                if item.key not in LEGACY_MAIL_ENV_KEYS:
                    output.write(item.original.string)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--remove-legacy", action="store_true")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)
    database = Database(settings.database_path)
    database.initialize()
    store = MailSettingsStore(database, settings)
    # Verify decryption before deleting any legacy credentials. Do not send mail.
    config = store.load()
    with database.connect() as connection:
        row = connection.execute("SELECT source FROM system_monitor_email_settings WHERE id=1").fetchone()
    has_legacy = any((settings.smtp_host, settings.smtp_username, settings.smtp_password,
                      settings.smtp_from_email, settings.alert_email_recipients))
    if has_legacy and not row:
        raise RuntimeError("Mail settings were not imported; legacy values preserved")
    if row and row["source"] == "legacy_env" and has_legacy:
        expected = (
            settings.smtp_host.strip(), settings.smtp_port, settings.smtp_username.strip(),
            settings.smtp_password.get_secret_value() if settings.smtp_password else "",
            settings.smtp_from_email.strip(), settings.alert_email_recipient_list,
            settings.smtp_security, settings.smtp_timeout_seconds,
        )
        actual = (config.host, config.port, config.username, config.password.get_secret_value(),
                  config.from_email, config.recipients, config.security, config.timeout_seconds)
        if expected != actual:
            raise RuntimeError("Imported values differ; legacy values preserved")
    removed = remove_legacy_values(args.env_file) if args.remove_legacy else 0
    print(f"mail_settings_present={bool(row)} configured={config.configured} legacy_assignments_removed={removed}")


if __name__ == "__main__":
    main()
