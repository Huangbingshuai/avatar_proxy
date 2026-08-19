import asyncio
import json
import os
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .database import Database


class BackupManager:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.directory = settings.admin_backup_directory or database.path.parent / "backups"
        self._lock = asyncio.Lock()

    @staticmethod
    def _secure_file(path: Path) -> None:
        with suppress(OSError):
            path.chmod(0o600)

    def _record_run(
        self,
        *,
        status: str,
        database_file: Path | None = None,
        audit_file: Path | None = None,
        error: str | None = None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO admin_backup_runs "
                "(status,database_file,audit_file,database_bytes,audit_bytes,error,completed_at) "
                "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (
                    status,
                    str(database_file) if database_file else None,
                    str(audit_file) if audit_file else None,
                    database_file.stat().st_size if database_file and database_file.exists() else None,
                    audit_file.stat().st_size if audit_file and audit_file.exists() else None,
                    (error or "")[:1000] or None,
                ),
            )

    def _export_audits(self, database_file: Path, audit_file: Path) -> None:
        connection = sqlite3.connect(database_file)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM admin_audit_logs ORDER BY id").fetchall()
            with audit_file.open("w", encoding="utf-8", newline="\n") as output:
                for row in rows:
                    output.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
                    output.write("\n")
        finally:
            connection.close()

    def _prune(self) -> None:
        database_files = sorted(self.directory.glob("avatar_proxy-*.db"), reverse=True)
        for database_file in database_files[self.settings.admin_backup_retention :]:
            suffix = database_file.stem.removeprefix("avatar_proxy-")
            audit_file = self.directory / f"admin_audit-{suffix}.jsonl"
            with suppress(OSError):
                database_file.unlink()
            with suppress(OSError):
                audit_file.unlink()

    def run_backup(self) -> dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        database_file = self.directory / f"avatar_proxy-{stamp}.db"
        audit_file = self.directory / f"admin_audit-{stamp}.jsonl"
        database_temp = database_file.with_suffix(".db.tmp")
        audit_temp = audit_file.with_suffix(".jsonl.tmp")
        try:
            source = sqlite3.connect(self.database.path, timeout=10)
            target = sqlite3.connect(database_temp)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            integrity = sqlite3.connect(database_temp)
            try:
                result = integrity.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                integrity.close()
            if result != "ok":
                raise RuntimeError(f"SQLite完整性检查失败：{result}")
            self._export_audits(database_temp, audit_temp)
            os.replace(database_temp, database_file)
            os.replace(audit_temp, audit_file)
            self._secure_file(database_file)
            self._secure_file(audit_file)
            self._record_run(status="success", database_file=database_file, audit_file=audit_file)
            self._prune()
            return self.status()
        except Exception as error:
            with suppress(OSError):
                database_temp.unlink()
            with suppress(OSError):
                audit_temp.unlink()
            self._record_run(status="failed", error=str(error))
            raise

    def status(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id,status,database_file AS databaseFile,audit_file AS auditFile,"
                "database_bytes AS databaseBytes,audit_bytes AS auditBytes,error,"
                "started_at AS startedAt,completed_at AS completedAt "
                "FROM admin_backup_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {
            "enabled": self.settings.admin_backup_enabled,
            "intervalSeconds": self.settings.admin_backup_interval_seconds,
            "retention": self.settings.admin_backup_retention,
            "directory": str(self.directory),
            "lastRun": dict(row) if row else None,
        }

    def _is_due(self) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT completed_at FROM admin_backup_runs "
                "WHERE status='success' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None or not row["completed_at"]:
            return True
        completed = datetime.fromisoformat(str(row["completed_at"])).replace(tzinfo=UTC)
        return (datetime.now(UTC) - completed).total_seconds() >= self.settings.admin_backup_interval_seconds

    async def run_if_due(self) -> None:
        if not self.settings.admin_backup_enabled or not self._is_due():
            return
        async with self._lock:
            if self._is_due():
                await asyncio.to_thread(self.run_backup)

    async def maintenance_loop(self) -> None:
        while True:
            try:
                await self.run_if_due()
            except Exception:
                # Failure details are persisted in admin_backup_runs and surfaced to the console.
                pass
            await asyncio.sleep(min(self.settings.admin_backup_interval_seconds, 3600))
