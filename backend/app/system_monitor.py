import asyncio
import json
import logging
import os
import shutil
import smtplib
import ssl
import time
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Callable

from .config import Settings
from .database import Database
from .errors import ApiError
from .maintenance import MaintenanceGate


LEVELS = ("warning", "critical", "emergency")
LEVEL_LABELS = {
    "normal": "正常",
    "warning": "预警",
    "critical": "严重",
    "emergency": "紧急",
    "recovered": "恢复",
    "probe_failed": "探测失败",
    "info": "测试",
}
RETRY_DELAYS = (60, 5 * 60, 15 * 60)
logger = logging.getLogger(__name__)


class DiskMonitor:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        clock: Callable[[], float] | None = None,
        statvfs: Callable[[str], Any] | None = None,
        maintenance_gate: MaintenanceGate | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.path = settings.effective_system_monitor_path.resolve()
        self.clock = clock or time.time
        self.statvfs = statvfs or self._platform_disk_stats
        self.maintenance_gate = maintenance_gate
        self._latest_sample: dict[str, Any] | None = None

    @staticmethod
    def _platform_disk_stats(path: str) -> Any:
        native = getattr(os, "statvfs", None)
        if native is not None:
            return native(path)
        usage = shutil.disk_usage(path)
        return type(
            "DiskStats",
            (),
            {
                "f_frsize": 1,
                "f_bsize": 1,
                "f_blocks": usage.total,
                "f_bfree": usage.free,
                "f_bavail": usage.free,
            },
        )()

    @property
    def email_configured(self) -> bool:
        username = self.settings.smtp_username.strip()
        password = self.settings.smtp_password
        password_configured = bool(password and password.get_secret_value().strip())
        authentication_valid = bool(username) == password_configured
        recipients = self.settings.alert_email_recipient_list
        return bool(
            self.settings.smtp_host.strip()
            and self._valid_email_address(self.settings.smtp_from_email.strip())
            and recipients
            and all(self._valid_email_address(address) for address in recipients)
            and authentication_valid
        )

    @staticmethod
    def _valid_email_address(value: str) -> bool:
        if "\r" in value or "\n" in value:
            return False
        _, address = parseaddr(value)
        local, separator, domain = address.rpartition("@")
        return bool(separator and local and "." in domain and not any(char.isspace() for char in address))

    def _database_settings(self, connection=None) -> dict[str, Any]:
        if connection is not None:
            row = connection.execute(
                "SELECT enabled,warning_percent,critical_percent,emergency_percent,"
                "recovery_percent,updated_by,updated_at FROM system_monitor_settings WHERE id=1"
            ).fetchone()
            return dict(row)
        with self.database.connect() as owned:
            return self._database_settings(owned)

    def settings_payload(self) -> dict[str, Any]:
        row = self._database_settings()
        configured_enabled = bool(row["enabled"])
        return {
            "enabled": configured_enabled and self.settings.system_monitor_enabled,
            "configuredEnabled": configured_enabled,
            "runtimeEnabled": self.settings.system_monitor_enabled,
            "path": str(self.path),
            "warningPercent": float(row["warning_percent"]),
            "criticalPercent": float(row["critical_percent"]),
            "emergencyPercent": float(row["emergency_percent"]),
            "recoveryPercent": float(row["recovery_percent"]),
            "sampleIntervalSeconds": self.settings.system_monitor_sample_interval_seconds,
            "persistIntervalSeconds": self.settings.system_monitor_persist_interval_seconds,
            "retentionDays": self.settings.system_monitor_retention_days,
            "emailConfigured": self.email_configured,
            "emailRecipientCount": len(self.settings.alert_email_recipient_list),
            "updatedBy": row["updated_by"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _sample_payload(row: Any | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        return {
            "path": value["path"],
            "totalBytes": int(value["total_bytes"]),
            "usedBytes": int(value["used_bytes"]),
            "availableBytes": int(value["available_bytes"]),
            "reservedBytes": int(value["reserved_bytes"]),
            "usedPercent": float(value["used_percent"]),
            "level": value["level"],
            "sampledAt": int(value["sampled_at"]),
        }

    def status(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            state = connection.execute("SELECT * FROM system_monitor_state WHERE id=1").fetchone()
            latest = connection.execute(
                "SELECT path,total_bytes,used_bytes,available_bytes,reserved_bytes,"
                "used_percent,level,sampled_at FROM disk_usage_samples ORDER BY sampled_at DESC,id DESC LIMIT 1"
            ).fetchone()
            pending = connection.execute(
                "SELECT COUNT(*) FROM system_monitor_email_deliveries WHERE status='pending'"
            ).fetchone()[0]
        sample = self._latest_sample or self._sample_payload(latest)
        state_value = dict(state) if state else {}
        enabled = self.settings_payload()["enabled"]
        health = "disabled" if not enabled else "probe_failed" if state_value.get("last_error") else "ok"
        return {
            "health": health,
            "sample": sample,
            "activeIncidentId": state_value.get("active_disk_incident_id"),
            "recoveryStreak": int(state_value.get("recovery_streak") or 0),
            "probeFailureStreak": int(state_value.get("probe_failure_streak") or 0),
            "probeAlertActive": bool(state_value.get("probe_alert_active")),
            "lastSampledAt": state_value.get("last_sampled_at"),
            "lastError": state_value.get("last_error"),
            "pendingEmailDeliveries": int(pending),
            "settings": self.settings_payload(),
        }

    def history(self, hours: int) -> list[dict[str, Any]]:
        cutoff = int(self.clock()) - hours * 3600
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT path,total_bytes,used_bytes,available_bytes,reserved_bytes,"
                "used_percent,level,sampled_at FROM disk_usage_samples "
                "WHERE sampled_at>=? ORDER BY sampled_at,id",
                (cutoff,),
            ).fetchall()
        return [self._sample_payload(row) for row in rows]

    def update_settings(
        self,
        *,
        enabled: bool,
        warning_percent: float,
        critical_percent: float,
        emergency_percent: float,
        recovery_percent: float,
        actor_id: str,
        actor: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            before = self._database_settings(connection)
            connection.execute(
                "UPDATE system_monitor_settings SET enabled=?,warning_percent=?,critical_percent=?,"
                "emergency_percent=?,recovery_percent=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (
                    int(enabled), warning_percent, critical_percent, emergency_percent,
                    recovery_percent, actor,
                ),
            )
            if not enabled:
                connection.execute(
                    "UPDATE system_monitor_state SET active_disk_incident_id=NULL,"
                    "disk_alerted_levels_json='[]',recovery_streak=0,probe_failure_streak=0,"
                    "probe_alert_active=0,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=1"
                )
                connection.execute(
                    "UPDATE system_monitor_email_deliveries SET status='failed',"
                    "last_error='monitor_disabled' WHERE status='pending'"
                )
            after = self._database_settings(connection)
            self.database.write_admin_audit(
                actor=actor,
                actor_id=actor_id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.system_monitor.settings.update",
                target_type="system_monitor",
                target_id="disk",
                before={
                    "enabled": bool(before["enabled"]),
                    "warningPercent": before["warning_percent"],
                    "criticalPercent": before["critical_percent"],
                    "emergencyPercent": before["emergency_percent"],
                    "recoveryPercent": before["recovery_percent"],
                },
                after={
                    "enabled": bool(after["enabled"]),
                    "warningPercent": after["warning_percent"],
                    "criticalPercent": after["critical_percent"],
                    "emergencyPercent": after["emergency_percent"],
                    "recoveryPercent": after["recovery_percent"],
                },
                connection=connection,
            )
        return self.settings_payload()

    def _measure(self, now: int) -> dict[str, Any]:
        stats = self.statvfs(str(self.path))
        block_size = int(stats.f_frsize or stats.f_bsize)
        total = int(stats.f_blocks) * block_size
        free = int(stats.f_bfree) * block_size
        available = int(stats.f_bavail) * block_size
        used = max(0, total - free)
        reserved = max(0, free - available)
        denominator = used + available
        used_percent = (used / denominator * 100) if denominator > 0 else 0.0
        thresholds = self._database_settings()
        level = "normal"
        if used_percent >= float(thresholds["emergency_percent"]):
            level = "emergency"
        elif used_percent >= float(thresholds["critical_percent"]):
            level = "critical"
        elif used_percent >= float(thresholds["warning_percent"]):
            level = "warning"
        return {
            "path": str(self.path),
            "totalBytes": total,
            "usedBytes": used,
            "availableBytes": available,
            "reservedBytes": reserved,
            "usedPercent": round(used_percent, 2),
            "level": level,
            "sampledAt": now,
        }

    @staticmethod
    def _alert_message(level: str, sample: dict[str, Any]) -> str:
        available_gib = sample["availableBytes"] / 1024**3
        if level == "recovered":
            return f"磁盘空间已恢复，当前占用 {sample['usedPercent']:.2f}%，可用 {available_gib:.2f} GiB"
        return (
            f"磁盘空间达到{LEVEL_LABELS[level]}阈值：占用 {sample['usedPercent']:.2f}%，"
            f"可用 {available_gib:.2f} GiB"
        )

    def _record_alert(
        self,
        connection,
        *,
        event_type: str,
        severity: str,
        message: str,
        details: dict[str, Any],
        now: int,
    ) -> int:
        cursor = connection.execute(
            "INSERT INTO admin_security_alerts "
            "(event_type,severity,message,actor,target_type,target_id,details_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                event_type,
                severity,
                message,
                "system",
                "filesystem",
                str(self.path),
                json.dumps(details, ensure_ascii=False, separators=(",", ":")),
                datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        alert_id = int(cursor.lastrowid)
        self._enqueue_email(connection, alert_id, message, details, now)
        return alert_id

    def _enqueue_email(
        self,
        connection,
        alert_id: int,
        message: str,
        details: dict[str, Any],
        now: int,
    ) -> None:
        if not self.email_configured:
            return
        subject, body = self._email_content(message, details, now)
        connection.execute(
            "INSERT OR IGNORE INTO system_monitor_email_deliveries"
            "(alert_id,subject,body,next_attempt_at) VALUES (?,?,?,?)",
            (alert_id, subject, body, now),
        )

    def _ensure_active_incident_email(
        self,
        connection,
        incident_id: str | None,
        now: int,
    ) -> None:
        if not self.email_configured or not incident_id:
            return
        rows = connection.execute(
            "SELECT id,message,details_json FROM admin_security_alerts "
            "WHERE target_type='filesystem' AND target_id=? "
            "AND event_type IN ('disk_usage_warning','disk_usage_critical','disk_usage_emergency') "
            "ORDER BY id DESC LIMIT 20",
            (str(self.path),),
        ).fetchall()
        for row in rows:
            try:
                details = json.loads(row["details_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if details.get("incidentId") == incident_id:
                self._enqueue_email(connection, int(row["id"]), row["message"], details, now)
                return

    def _email_content(
        self,
        message: str,
        details: dict[str, Any],
        now: int,
    ) -> tuple[str, str]:
        level = str(details.get("level") or "info")
        label = LEVEL_LABELS.get(level, "通知")
        timestamp = datetime.fromtimestamp(now, UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        subject = f"[Star Proxy][{label}] 磁盘空间监控"
        body = (
            "Star Proxy 系统监控\n\n"
            f"告警状态：{label}\n"
            f"告警内容：{message}\n"
            f"监控路径：{self.path}\n"
            f"发生时间：{timestamp}\n\n"
            "此邮件由系统自动发送，请勿直接回复。"
        )
        return subject[:200], body

    def _persist_sample(self, connection, sample: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO disk_usage_samples"
            "(path,total_bytes,used_bytes,available_bytes,reserved_bytes,used_percent,level,sampled_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                sample["path"], sample["totalBytes"], sample["usedBytes"],
                sample["availableBytes"], sample["reservedBytes"], sample["usedPercent"],
                sample["level"], sample["sampledAt"],
            ),
        )

    def _handle_success(self, sample: dict[str, Any]) -> None:
        now = int(sample["sampledAt"])
        thresholds = self._database_settings()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute("SELECT * FROM system_monitor_state WHERE id=1").fetchone()
            alerted = set(json.loads(state["disk_alerted_levels_json"] or "[]"))
            incident_id = state["active_disk_incident_id"]
            recovery_streak = int(state["recovery_streak"] or 0)

            if bool(state["probe_alert_active"]):
                self._record_alert(
                    connection,
                    event_type="disk_probe_recovered",
                    severity="info",
                    message="磁盘空间探测已恢复",
                    details={"level": "recovered", "failureCount": int(state["probe_failure_streak"] or 0)},
                    now=now,
                )

            level = sample["level"]
            if level in LEVELS:
                if not incident_id:
                    incident_id = str(uuid.uuid4())
                    alerted.clear()
                crossed = LEVELS[: LEVELS.index(level) + 1]
                if level not in alerted:
                    alerted.update(crossed)
                    self._record_alert(
                        connection,
                        event_type=f"disk_usage_{level}",
                        severity="warning" if level == "warning" else "critical",
                        message=self._alert_message(level, sample),
                        details={
                            "level": level,
                            "incidentId": incident_id,
                            "usedPercent": sample["usedPercent"],
                            "availableBytes": sample["availableBytes"],
                        },
                        now=now,
                    )
                recovery_streak = 0
            elif incident_id:
                if sample["usedPercent"] < float(thresholds["recovery_percent"]):
                    recovery_streak += 1
                else:
                    recovery_streak = 0
                if recovery_streak >= 5:
                    self._record_alert(
                        connection,
                        event_type="disk_usage_recovered",
                        severity="info",
                        message=self._alert_message("recovered", sample),
                        details={
                            "level": "recovered",
                            "incidentId": incident_id,
                            "usedPercent": sample["usedPercent"],
                            "availableBytes": sample["availableBytes"],
                        },
                        now=now,
                    )
                    incident_id = None
                    alerted.clear()
                    recovery_streak = 0

            self._ensure_active_incident_email(connection, incident_id, now)

            last_persisted = int(state["last_persisted_at"] or 0)
            if now - last_persisted >= self.settings.system_monitor_persist_interval_seconds:
                self._persist_sample(connection, sample)
                last_persisted = now
                cutoff = now - self.settings.system_monitor_retention_days * 86400
                connection.execute("DELETE FROM disk_usage_samples WHERE sampled_at<?", (cutoff,))

            connection.execute(
                "UPDATE system_monitor_state SET active_disk_incident_id=?,"
                "disk_alerted_levels_json=?,recovery_streak=?,probe_failure_streak=0,"
                "probe_alert_active=0,last_sampled_at=?,last_persisted_at=?,last_error=NULL,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (
                    incident_id,
                    json.dumps(sorted(alerted), separators=(",", ":")),
                    recovery_streak,
                    now,
                    last_persisted or None,
                ),
            )
        self._latest_sample = sample

    def _handle_probe_failure(self, error: Exception, now: int) -> None:
        error_name = type(error).__name__
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute("SELECT * FROM system_monitor_state WHERE id=1").fetchone()
            failures = int(state["probe_failure_streak"] or 0) + 1
            alert_active = bool(state["probe_alert_active"])
            if failures >= 3 and not alert_active:
                self._record_alert(
                    connection,
                    event_type="disk_probe_failed",
                    severity="critical",
                    message="磁盘空间连续三次探测失败",
                    details={"level": "probe_failed", "failureCount": failures, "errorType": error_name},
                    now=now,
                )
                alert_active = True
            connection.execute(
                "UPDATE system_monitor_state SET probe_failure_streak=?,probe_alert_active=?,"
                "last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (failures, int(alert_active), f"磁盘探测失败（{error_name}）"),
            )

    def _send_email_sync(self, subject: str, body: str) -> None:
        if not self.email_configured:
            raise ApiError("SMTP邮件告警尚未完整配置", 409, "alert_email_not_configured")
        recipients = [parseaddr(value)[1] for value in self.settings.alert_email_recipient_list]
        sender = parseaddr(self.settings.smtp_from_email.strip())[1]
        message = EmailMessage()
        message["Subject"] = subject[:200]
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        context = ssl.create_default_context()
        try:
            if self.settings.smtp_security == "ssl":
                client = smtplib.SMTP_SSL(
                    self.settings.smtp_host.strip(),
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                    context=context,
                )
            else:
                client = smtplib.SMTP(
                    self.settings.smtp_host.strip(),
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                )
            with client:
                if self.settings.smtp_security == "starttls":
                    client.ehlo()
                    client.starttls(context=context)
                    client.ehlo()
                username = self.settings.smtp_username.strip()
                password = self.settings.smtp_password
                if username and password:
                    client.login(username, password.get_secret_value())
                refused = client.send_message(message, from_addr=sender, to_addrs=recipients)
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
        except (OSError, smtplib.SMTPException) as error:
            raise ApiError(
                f"SMTP邮件发送失败（{type(error).__name__}）",
                502,
                "alert_email_send_failed",
            ) from error

    async def _send_email(self, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_email_sync, subject, body)

    async def deliver_pending(self, now: int | None = None) -> None:
        if not self.email_configured:
            return
        current = int(self.clock()) if now is None else now
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id,subject,body,attempt_count FROM system_monitor_email_deliveries "
                "WHERE status='pending' AND next_attempt_at<=? ORDER BY id LIMIT 20",
                (current,),
            ).fetchall()
        for row in rows:
            try:
                await self._send_email(row["subject"], row["body"])
            except ApiError as error:
                attempts = int(row["attempt_count"]) + 1
                with self.database.connect() as connection:
                    if attempts >= 4:
                        connection.execute(
                            "UPDATE system_monitor_email_deliveries SET status='failed',"
                            "attempt_count=?,last_error=? WHERE id=?",
                            (attempts, error.message[:300], row["id"]),
                        )
                    else:
                        connection.execute(
                            "UPDATE system_monitor_email_deliveries SET attempt_count=?,"
                            "next_attempt_at=?,last_error=? WHERE id=?",
                            (attempts, current + RETRY_DELAYS[attempts - 1], error.message[:300], row["id"]),
                        )
            else:
                with self.database.connect() as connection:
                    connection.execute(
                        "UPDATE system_monitor_email_deliveries SET status='sent',"
                        "attempt_count=attempt_count+1,last_error=NULL,sent_at=CURRENT_TIMESTAMP WHERE id=?",
                        (row["id"],),
                    )

    async def test_email(
        self,
        *,
        actor_id: str,
        actor: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, bool]:
        now = int(self.clock())
        try:
            subject, body = self._email_content("磁盘告警邮件通道测试成功", {"level": "info"}, now)
            await self._send_email(subject, body)
        except ApiError:
            self.database.write_admin_audit(
                actor=actor,
                actor_id=actor_id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.system_monitor.email.test",
                target_type="system_monitor",
                target_id="email",
                after={"result": "failed"},
                outcome="failure",
            )
            raise
        self.database.write_admin_audit(
            actor=actor,
            actor_id=actor_id,
            source_ip=source_ip,
            user_agent=user_agent,
            action="admin.system_monitor.email.test",
            target_type="system_monitor",
            target_id="email",
            after={"result": "success"},
        )
        return {"sent": True}

    async def run_once(self) -> dict[str, Any]:
        now = int(self.clock())
        settings = self._database_settings()
        enabled = self.settings.system_monitor_enabled and bool(settings["enabled"])
        if enabled:
            try:
                sample = self._measure(now)
            except Exception as error:  # pragma: no cover - exact OS errors vary by platform
                self._handle_probe_failure(error, now)
            else:
                self._handle_success(sample)
            await self.deliver_pending(now)
        return self.status()

    async def maintenance_loop(self) -> None:
        while True:
            if self.maintenance_gate is None or not self.maintenance_gate.active:
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # keep the monitor alive after transient SQLite/OS failures
                    logger.warning("磁盘监控本轮执行失败（%s）", type(error).__name__)
            await asyncio.sleep(self.settings.system_monitor_sample_interval_seconds)

    async def aclose(self) -> None:
        return None
