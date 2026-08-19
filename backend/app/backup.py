import asyncio
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .database import Database
from .errors import ApiError
from .maintenance import MaintenanceGate


BACKUP_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-\d{6}$")
RESTORE_CONFIRMATION = "恢复数据库"
REQUIRED_RESTORE_TABLES = {
    "projects",
    "api_keys",
    "admin_users",
    "admin_audit_logs",
}


class BackupManager:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        maintenance_gate: MaintenanceGate | None = None,
        totp_secret_validator: Callable[[str], None] | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.directory = settings.admin_backup_directory or database.path.parent / "backups"
        self.maintenance_gate = maintenance_gate
        self.totp_secret_validator = totp_secret_validator
        self._lock = asyncio.Lock()

    @staticmethod
    def _backup_id(path: Path) -> str:
        return path.stem.removeprefix("avatar_proxy-")

    def _resolve_backup(self, backup_id: str) -> Path:
        if not BACKUP_ID_PATTERN.fullmatch(backup_id):
            raise ApiError("备份标识无效", 404, "admin_backup_not_found")
        directory = self.directory.resolve()
        candidate = (directory / f"avatar_proxy-{backup_id}.db").resolve()
        if candidate.parent != directory or not candidate.is_file():
            raise ApiError("备份不存在", 404, "admin_backup_not_found")
        return candidate

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _read_only_connection(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _inspect_backup(self, path: Path, *, check_integrity: bool) -> dict[str, Any]:
        backup_id = self._backup_id(path)
        audit_file = self.directory / f"admin_audit-{backup_id}.jsonl"
        connection = self._read_only_connection(path)
        try:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = sorted(REQUIRED_RESTORE_TABLES - tables)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0] if check_integrity else None
            counts = {
                "projects": connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                if "projects" in tables else 0,
                "apiKeys": connection.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                if "api_keys" in tables else 0,
                "adminUsers": connection.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]
                if "admin_users" in tables else 0,
                "adminAudits": connection.execute("SELECT COUNT(*) FROM admin_audit_logs").fetchone()[0]
                if "admin_audit_logs" in tables else 0,
            }
            super_count = connection.execute(
                "SELECT COUNT(*) FROM admin_users WHERE role='super_admin' AND status='active'"
            ).fetchone()[0] if "admin_users" in tables else 0
            if check_integrity and not missing and self.totp_secret_validator:
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(admin_users)").fetchall()
                }
                if "totp_secret_encrypted" in columns:
                    secrets = connection.execute(
                        "SELECT totp_secret_encrypted FROM admin_users "
                        "WHERE totp_secret_encrypted IS NOT NULL"
                    ).fetchall()
                    for row in secrets:
                        self.totp_secret_validator(row["totp_secret_encrypted"])
        finally:
            connection.close()
        valid = (integrity in {None, "ok"}) and not missing and super_count == 1
        return {
            "id": backup_id,
            "databaseFile": path.name,
            "auditFile": audit_file.name if audit_file.is_file() else None,
            "databaseBytes": path.stat().st_size,
            "auditBytes": audit_file.stat().st_size if audit_file.is_file() else None,
            "createdAt": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            "integrity": integrity,
            "missingTables": missing,
            "activeSuperAdmins": super_count,
            "counts": counts,
            "sha256": self._sha256_file(path) if check_integrity else None,
            "valid": valid,
        }

    def list_backups(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        backups = []
        for path in sorted(self.directory.glob("avatar_proxy-*.db"), reverse=True):
            backup_id = self._backup_id(path)
            if BACKUP_ID_PATTERN.fullmatch(backup_id):
                try:
                    backups.append(self._inspect_backup(path, check_integrity=False))
                except (OSError, sqlite3.Error):
                    backups.append({
                        "id": backup_id,
                        "databaseFile": path.name,
                        "databaseBytes": path.stat().st_size if path.exists() else None,
                        "createdAt": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
                        if path.exists() else None,
                        "valid": False,
                        "unreadable": True,
                    })
        return backups

    def validate_backup(self, backup_id: str) -> dict[str, Any]:
        path = self._resolve_backup(backup_id)
        try:
            result = self._inspect_backup(path, check_integrity=True)
        except ApiError as error:
            if error.code == "admin_totp_key_unavailable":
                raise ApiError(
                    "备份中的TOTP密钥与当前服务器加密主密钥不匹配",
                    409,
                    "admin_backup_totp_key_mismatch",
                ) from error
            raise
        except (OSError, sqlite3.DatabaseError) as error:
            raise ApiError("备份文件无法读取或不是有效SQLite数据库", 422, "admin_backup_invalid") from error
        if result["integrity"] != "ok":
            raise ApiError(
                "备份数据库完整性检查失败",
                422,
                "admin_backup_integrity_failed",
                details={"integrity": str(result["integrity"])[:300]},
            )
        if result["missingTables"]:
            raise ApiError(
                "备份缺少系统所需数据表",
                422,
                "admin_backup_schema_invalid",
                details={"missingTables": result["missingTables"]},
            )
        if result["activeSuperAdmins"] != 1:
            raise ApiError(
                "备份必须包含唯一且启用的超级管理员",
                422,
                "admin_backup_super_admin_invalid",
            )
        return result

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

    def run_backup(self, *, prune: bool = True) -> dict[str, Any]:
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
            if prune:
                self._prune()
            return self.status()
        except Exception as error:
            with suppress(OSError):
                database_temp.unlink()
            with suppress(OSError):
                audit_temp.unlink()
            self._record_run(status="failed", error=str(error))
            raise

    async def run_manual_backup(self) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self.run_backup)

    @staticmethod
    def _restore_copy(source_path: Path, destination_path: Path) -> None:
        source = sqlite3.connect(
            f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True, timeout=30
        )
        destination = sqlite3.connect(destination_path, timeout=30)
        try:
            destination.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            source.backup(destination)
        finally:
            destination.close()
            source.close()

    def _last_restore(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id,backup_id AS backupId,status,actor,source_ip AS sourceIp,"
                "rollback_backup_id AS rollbackBackupId,summary_json AS summaryJson,error,"
                "started_at AS startedAt,completed_at AS completedAt "
                "FROM admin_restore_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("summaryJson"):
            with suppress(json.JSONDecodeError):
                result["summary"] = json.loads(result.pop("summaryJson"))
        return result

    def _record_restore(
        self,
        *,
        restore_id: str,
        backup_id: str,
        status: str,
        actor: str,
        source_ip: str | None,
        rollback_backup_id: str | None,
        summary: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        now = int(time.time())
        with self.database.connect() as connection:
            actor_row = connection.execute(
                "SELECT id FROM admin_users WHERE username_normalized=?",
                (actor.strip().lower(),),
            ).fetchone()
            actor_id = actor_row["id"] if actor_row else None
            connection.execute(
                "INSERT INTO admin_restore_runs "
                "(id,backup_id,status,actor,source_ip,rollback_backup_id,summary_json,error) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    restore_id,
                    backup_id,
                    status,
                    actor,
                    source_ip,
                    rollback_backup_id,
                    json.dumps(summary, ensure_ascii=False, separators=(",", ":")) if summary else None,
                    (error or "")[:1000] or None,
                ),
            )
            connection.execute(
                "UPDATE admin_sessions SET revoked_at=?,revoke_reason='database_restored' "
                "WHERE revoked_at IS NULL",
                (now,),
            )
            self.database.write_admin_audit(
                actor=actor,
                actor_id=actor_id,
                source_ip=source_ip,
                user_agent="database-restore",
                action="admin.database.restore",
                target_type="database_backup",
                target_id=backup_id,
                after={
                    "status": status,
                    "rollbackBackupId": rollback_backup_id,
                    "counts": (summary or {}).get("counts"),
                },
                outcome=status,
                connection=connection,
            )
            connection.execute(
                "INSERT INTO admin_security_alerts "
                "(event_type,severity,message,actor_id,actor,source_ip,target_type,target_id,details_json) "
                "VALUES ('database_restored','critical',?,?,?,?,?,?,?)",
                (
                    "数据库恢复成功，全部管理员会话已撤销"
                    if status == "success" else "数据库恢复失败，系统已尝试回滚",
                    actor_id,
                    actor,
                    source_ip,
                    "database_backup",
                    backup_id,
                    json.dumps(
                        {"status": status, "rollbackBackupId": rollback_backup_id},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )

    def _restore_and_initialize(self, source_path: Path) -> None:
        self._restore_copy(source_path, self.database.path)
        self.database.initialize()
        with self.database.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"恢复后SQLite完整性检查失败：{integrity}")
            if self.totp_secret_validator:
                rows = connection.execute(
                    "SELECT totp_secret_encrypted FROM admin_users "
                    "WHERE totp_secret_encrypted IS NOT NULL"
                ).fetchall()
                for row in rows:
                    self.totp_secret_validator(row["totp_secret_encrypted"])

    async def restore_backup(
        self,
        backup_id: str,
        *,
        actor: str,
        source_ip: str | None,
    ) -> dict[str, Any]:
        if self.maintenance_gate is None:
            raise ApiError("数据库恢复维护器未初始化", 503, "admin_restore_unavailable")
        async with self._lock:
            validated = await asyncio.to_thread(self.validate_backup, backup_id)
            candidate = self._resolve_backup(backup_id)
            async with self.maintenance_gate.exclusive_restore():
                # Keep every existing backup until the selected candidate has been
                # consumed. Otherwise a full retention window could prune the very
                # backup that is about to be restored.
                rollback_status = await asyncio.to_thread(self.run_backup, prune=False)
                rollback_run = rollback_status.get("lastRun") or {}
                rollback_id = str(rollback_run.get("backupId") or "")
                if not rollback_id:
                    raise ApiError("恢复前回滚快照创建失败", 500, "admin_restore_rollback_failed")
                rollback_path = self._resolve_backup(rollback_id)
                restore_id = str(uuid.uuid4())
                try:
                    await asyncio.to_thread(self._restore_and_initialize, candidate)
                    await asyncio.to_thread(
                        self._record_restore,
                        restore_id=restore_id,
                        backup_id=backup_id,
                        status="success",
                        actor=actor,
                        source_ip=source_ip,
                        rollback_backup_id=rollback_id,
                        summary=validated,
                        error=None,
                    )
                    await asyncio.to_thread(self._prune)
                except Exception as restore_error:
                    rollback_error: Exception | None = None
                    try:
                        await asyncio.to_thread(self._restore_and_initialize, rollback_path)
                    except Exception as caught:
                        rollback_error = caught
                    if rollback_error is None:
                        await asyncio.to_thread(
                            self._record_restore,
                            restore_id=restore_id,
                            backup_id=backup_id,
                            status="failed",
                            actor=actor,
                            source_ip=source_ip,
                            rollback_backup_id=rollback_id,
                            summary=validated,
                            error=str(restore_error),
                        )
                        await asyncio.to_thread(self._prune)
                    message = "数据库恢复失败，已自动回滚到恢复前状态"
                    if rollback_error is not None:
                        message = "数据库恢复及自动回滚均失败，请立即停止服务并使用服务器备份恢复"
                    raise ApiError(
                        message,
                        500,
                        "admin_restore_failed",
                        details={"restoreId": restore_id, "rollbackFailed": rollback_error is not None},
                    ) from restore_error
        return {
            "restored": True,
            "restoreId": restore_id,
            "backup": validated,
            "rollbackBackupId": rollback_id,
            "requiresLogin": True,
        }

    def status(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id,status,database_file AS databaseFile,audit_file AS auditFile,"
                "database_bytes AS databaseBytes,audit_bytes AS auditBytes,error,"
                "started_at AS startedAt,completed_at AS completedAt "
                "FROM admin_backup_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        last_run = dict(row) if row else None
        if last_run and last_run.get("databaseFile"):
            last_run["backupId"] = self._backup_id(Path(str(last_run["databaseFile"])))
        return {
            "enabled": self.settings.admin_backup_enabled,
            "intervalSeconds": self.settings.admin_backup_interval_seconds,
            "retention": self.settings.admin_backup_retention,
            "directory": str(self.directory),
            "lastRun": last_run,
            "lastRestore": self._last_restore(),
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
                if self.maintenance_gate:
                    async with self.maintenance_gate.background_activity():
                        await self.run_if_due()
                else:
                    await self.run_if_due()
            except Exception:
                # Failure details are persisted in admin_backup_runs and surfaced to the console.
                pass
            await asyncio.sleep(min(self.settings.admin_backup_interval_seconds, 3600))
