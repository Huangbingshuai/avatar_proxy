import asyncio
import math
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import Request

from .database import Database
from .errors import ApiError


SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
PROJECT_METRICS = (
    "read_qpm",
    "write_qpm",
    "max_concurrency",
    "daily_asset_creates",
    "daily_upload_files",
    "daily_upload_bytes",
    "total_assets",
    "total_storage_bytes",
)
KEY_METRICS = PROJECT_METRICS[:6]
DAILY_METRICS = {"daily_asset_creates", "daily_upload_files", "daily_upload_bytes"}
TOTAL_METRICS = {"total_assets", "total_storage_bytes"}


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _quota_row(row: Any, metrics: tuple[str, ...], *, enabled: bool | None = None) -> dict[str, Any]:
    result = {_camel(metric): row[metric] if row else None for metric in metrics}
    if enabled is not None:
        result["enabled"] = enabled
    return result


class QuotaManager:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._concurrency: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _windows() -> tuple[str, str, datetime, datetime]:
        now = datetime.now(SHANGHAI)
        minute = now.replace(second=0, microsecond=0)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return minute.isoformat(), day.date().isoformat(), minute + timedelta(minutes=1), day + timedelta(days=1)

    def project_quota(self, project_name: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM project_quotas WHERE project_name = ?", (project_name,)
            ).fetchone()
            if connection.execute("SELECT 1 FROM projects WHERE name = ?", (project_name,)).fetchone() is None:
                raise ApiError("项目不存在", 404, "project_not_found")
        return {"projectName": project_name, **_quota_row(row, PROJECT_METRICS, enabled=bool(row["enabled"]) if row else False)}

    def key_quota(self, key_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            key = connection.execute(
                "SELECT id, project_name FROM api_keys WHERE id = ?", (key_id,)
            ).fetchone()
            if key is None:
                raise ApiError("API Key 不存在", 404, "api_key_not_found")
            row = connection.execute("SELECT * FROM api_key_quotas WHERE api_key_id = ?", (key_id,)).fetchone()
        return {"keyId": key_id, "projectName": key["project_name"], **_quota_row(row, KEY_METRICS)}

    def set_project_quota(
        self,
        values: dict[str, Any],
        source_ip: str | None,
        *,
        actor_id: str | None = None,
        actor: str = "system",
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        project_name = values["project_name"]
        before = self.project_quota(project_name)
        columns = ["enabled", *PROJECT_METRICS]
        payload = [int(values["enabled"]), *(values.get(metric) for metric in PROJECT_METRICS)]
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns)
        with self.database.connect() as connection:
            connection.execute(
                f"INSERT INTO project_quotas (project_name, {', '.join(columns)}) VALUES (?, {placeholders}) "
                f"ON CONFLICT(project_name) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP",
                (project_name, *payload),
            )
        after = self.project_quota(project_name)
        self._audit(
            "quota.project.update", "project", project_name, before, after, source_ip,
            actor_id=actor_id, actor=actor, user_agent=user_agent,
        )
        return after

    def set_key_quota(
        self,
        values: dict[str, Any],
        source_ip: str | None,
        *,
        actor_id: str | None = None,
        actor: str = "system",
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        key_id = values["key_id"]
        before = self.key_quota(key_id)
        project = self.project_quota(before["projectName"])
        for metric in KEY_METRICS:
            key_value = values.get(metric)
            project_value = project[_camel(metric)]
            if key_value is not None and project_value is not None and key_value > project_value:
                raise ApiError("API Key 子额度不能高于项目额度", 400, "key_quota_exceeds_project")
        placeholders = ", ".join("?" for _ in KEY_METRICS)
        updates = ", ".join(f"{metric}=excluded.{metric}" for metric in KEY_METRICS)
        with self.database.connect() as connection:
            connection.execute(
                f"INSERT INTO api_key_quotas (api_key_id, {', '.join(KEY_METRICS)}) VALUES (?, {placeholders}) "
                f"ON CONFLICT(api_key_id) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP",
                (key_id, *(values.get(metric) for metric in KEY_METRICS)),
            )
        after = self.key_quota(key_id)
        self._audit(
            "quota.apikey.update", "api_key", key_id, before, after, source_ip,
            actor_id=actor_id, actor=actor, user_agent=user_agent,
        )
        return after

    def _audit(
        self, action: str, target_type: str, target_id: str,
        before: dict[str, Any], after: dict[str, Any], source_ip: str | None,
        *, actor_id: str | None, actor: str, user_agent: str | None,
    ) -> None:
        self.database.write_admin_audit(
            actor=actor,
            actor_id=actor_id,
            source_ip=source_ip,
            user_agent=user_agent,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
        )

    def _configs(self, connection: Any, project_name: str, key_id: str) -> tuple[Any, Any]:
        project = connection.execute(
            "SELECT * FROM project_quotas WHERE project_name = ? AND enabled = 1", (project_name,)
        ).fetchone()
        key = connection.execute("SELECT * FROM api_key_quotas WHERE api_key_id = ?", (key_id,)).fetchone()
        return project, key

    @staticmethod
    def _scope_limits(project: Any, key: Any, metric: str) -> list[tuple[str, str, int]]:
        if project is None:
            return []
        limits: list[tuple[str, str, int]] = []
        if project[metric] is not None:
            limits.append(("project", project["project_name"], int(project[metric])))
        if metric in KEY_METRICS and key is not None and key[metric] is not None:
            limits.append(("api_key", key["api_key_id"], int(key[metric])))
        return limits

    def _event(
        self, connection: Any, project_name: str, key_id: str, scope_type: str,
        scope_id: str, metric: str, threshold: int, limit: int, used: int, window: str,
    ) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO quota_events "
            "(project_name, api_key_id, scope_type, scope_id, metric, threshold, limit_value, used_value, window_start) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_name, key_id, scope_type, scope_id, metric, threshold, limit, used, window),
        )

    def consume_qpm(self, project_name: str, key_id: str, *, write: bool) -> None:
        metric = "write_qpm" if write else "read_qpm"
        minute, _, minute_reset, _ = self._windows()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project, key = self._configs(connection, project_name, key_id)
            for scope_type, scope_id, limit in self._scope_limits(project, key, metric):
                row = connection.execute(
                    "SELECT value FROM quota_usage_windows WHERE scope_type=? AND scope_id=? AND metric=? AND window_start=?",
                    (scope_type, scope_id, metric, minute),
                ).fetchone()
                used = int(row["value"]) if row else 0
                if write and used >= limit:
                    self._event(connection, project_name, key_id, scope_type, scope_id, metric, 100, limit, used, minute)
                    retry = max(1, math.ceil((minute_reset - datetime.now(SHANGHAI)).total_seconds()))
                    raise self._quota_error(metric, scope_type, limit, used, minute_reset.isoformat(), retry)
            for scope_type, scope_id, limit in self._scope_limits(project, key, metric):
                connection.execute(
                    "INSERT INTO quota_usage_windows (scope_type, scope_id, metric, window_start, value) VALUES (?, ?, ?, ?, 1) "
                    "ON CONFLICT(scope_type, scope_id, metric, window_start) DO UPDATE SET value=value+1, updated_at=CURRENT_TIMESTAMP",
                    (scope_type, scope_id, metric, minute),
                )
                used = connection.execute(
                    "SELECT value FROM quota_usage_windows WHERE scope_type=? AND scope_id=? AND metric=? AND window_start=?",
                    (scope_type, scope_id, metric, minute),
                ).fetchone()["value"]
                for threshold in (70, 90, 100):
                    if used * 100 >= limit * threshold:
                        self._event(connection, project_name, key_id, scope_type, scope_id, metric, threshold, limit, used, minute)

    @asynccontextmanager
    async def request_slot(self, project_name: str, key_id: str, *, write: bool) -> AsyncIterator[None]:
        self.consume_qpm(project_name, key_id, write=write)
        acquired: list[tuple[str, str]] = []
        if write:
            with self.database.connect() as connection:
                project, key = self._configs(connection, project_name, key_id)
                limits = self._scope_limits(project, key, "max_concurrency")
            async with self._lock:
                for scope_type, scope_id, limit in limits:
                    scope = (scope_type, scope_id)
                    used = self._concurrency.get(scope, 0)
                    if used >= limit:
                        for held in acquired:
                            self._concurrency[held] -= 1
                        raise self._quota_error("max_concurrency", scope_type, limit, used, None, 1)
                    self._concurrency[scope] = used + 1
                    acquired.append(scope)
        try:
            yield
        finally:
            if acquired:
                async with self._lock:
                    for scope in acquired:
                        self._concurrency[scope] = max(0, self._concurrency.get(scope, 1) - 1)

    def reserve(self, project_name: str, key_id: str, amounts: dict[str, int]) -> str:
        reservation_id = str(uuid.uuid4())
        _, day, _, day_reset = self._windows()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project, key = self._configs(connection, project_name, key_id)
            for metric, amount in amounts.items():
                window = day if metric in DAILY_METRICS else "total"
                for scope_type, scope_id, limit in self._scope_limits(project, key, metric):
                    row = connection.execute(
                        "SELECT value, reserved FROM quota_usage_windows WHERE scope_type=? AND scope_id=? AND metric=? AND window_start=?",
                        (scope_type, scope_id, metric, window),
                    ).fetchone()
                    used = int(row["value"]) if row else 0
                    reserved = int(row["reserved"]) if row else 0
                    if metric == "total_assets":
                        used = connection.execute(
                            "SELECT COUNT(*) FROM asset_records WHERE project_name=? AND status IN ('registering','active')",
                            (project_name,),
                        ).fetchone()[0]
                    elif metric == "total_storage_bytes":
                        used = connection.execute(
                            "SELECT COALESCE(SUM(size_bytes),0) FROM asset_records WHERE project_name=? AND source_type='tos' AND status!='deleted'",
                            (project_name,),
                        ).fetchone()[0]
                    if used + reserved + amount > limit:
                        reset = day_reset.isoformat() if metric in DAILY_METRICS else None
                        retry = math.ceil((day_reset - datetime.now(SHANGHAI)).total_seconds()) if reset else None
                        raise self._quota_error(metric, scope_type, limit, used + reserved, reset, retry)
            for metric, amount in amounts.items():
                window = day if metric in DAILY_METRICS else "total"
                for scope_type, scope_id, _ in self._scope_limits(project, key, metric):
                    connection.execute(
                        "INSERT INTO quota_usage_windows (scope_type, scope_id, metric, window_start, reserved) VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(scope_type, scope_id, metric, window_start) DO UPDATE SET reserved=reserved+excluded.reserved, updated_at=CURRENT_TIMESTAMP",
                        (scope_type, scope_id, metric, window, amount),
                    )
                    connection.execute(
                        "INSERT INTO quota_reservations (reservation_id, scope_type, scope_id, metric, window_start, amount) VALUES (?, ?, ?, ?, ?, ?)",
                        (reservation_id, scope_type, scope_id, metric, window, amount),
                    )
        return reservation_id

    def finish_reservation(self, reservation_id: str, *, commit: bool) -> None:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?", (reservation_id,)
            ).fetchall()
            for row in rows:
                add_value = row["amount"] if commit and row["metric"] in DAILY_METRICS else 0
                connection.execute(
                    "UPDATE quota_usage_windows SET reserved=MAX(0,reserved-?), value=value+?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE scope_type=? AND scope_id=? AND metric=? AND window_start=?",
                    (row["amount"], add_value, row["scope_type"], row["scope_id"], row["metric"], row["window_start"]),
                )
            connection.execute("DELETE FROM quota_reservations WHERE reservation_id = ?", (reservation_id,))

    @staticmethod
    def _quota_error(
        metric: str, scope: str, limit: int, used: int, reset_at: str | None, retry_after: int | None,
    ) -> ApiError:
        details: dict[str, Any] = {
            "metric": _camel(metric), "scope": scope, "limit": limit, "used": used,
            "resetAt": reset_at, "requestId": f"req_{uuid.uuid4().hex}",
        }
        headers = {"Retry-After": str(max(1, retry_after))} if retry_after else {}
        return ApiError("额度已用尽", 429, "quota_exceeded", details=details, headers=headers)

    def usage(self, project_name: str) -> dict[str, Any]:
        minute, day, _, _ = self._windows()
        quota = self.project_quota(project_name)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT metric, window_start, value, reserved FROM quota_usage_windows "
                "WHERE scope_type='project' AND scope_id=? AND window_start IN (?, ?, 'total')",
                (project_name, minute, day),
            ).fetchall()
            assets = connection.execute(
                "SELECT COUNT(*) FROM asset_records WHERE project_name=? AND status IN ('registering','active')",
                (project_name,),
            ).fetchone()[0]
            storage = connection.execute(
                "SELECT COALESCE(SUM(size_bytes),0) FROM asset_records WHERE project_name=? AND source_type='tos' AND status!='deleted'",
                (project_name,),
            ).fetchone()[0]
            cleanup = connection.execute(
                "SELECT COUNT(*) FROM asset_records WHERE project_name=? AND status='cleanup_pending'", (project_name,)
            ).fetchone()[0]
        values = {_camel(row["metric"]): row["value"] + row["reserved"] for row in rows}
        values.update({"totalAssets": assets, "totalStorageBytes": storage, "cleanupPending": cleanup})
        return {
            "projectName": project_name,
            "quota": quota,
            "usage": values,
            "cleanupObjects": self.database.pending_cleanup_objects(project_name),
            "minuteWindow": minute,
            "dayWindow": day,
        }

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, project_name AS projectName, api_key_id AS apiKeyId, scope_type AS scopeType, "
                "scope_id AS scopeId, metric, threshold, limit_value AS limitValue, used_value AS usedValue, "
                "window_start AS windowStart, acknowledged, created_at AS createdAt "
                "FROM quota_events ORDER BY acknowledged, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{**dict(row), "acknowledged": bool(row["acknowledged"])} for row in rows]

    def acknowledge(self, event_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE quota_events SET acknowledged=1, acknowledged_at=CURRENT_TIMESTAMP WHERE id=? AND acknowledged=0",
                (event_id,),
            )
        return cursor.rowcount > 0

    def audits(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, actor, actor_id AS actorId, source_ip AS sourceIp, user_agent AS userAgent, "
                "action, target_type AS targetType, "
                "target_id AS targetId, before_json AS beforeJson, after_json AS afterJson, "
                "outcome, created_at AS createdAt FROM admin_audit_logs "
                "WHERE action IN ('quota.project.update','quota.apikey.update') "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def is_write_request(request: Request) -> bool:
        return request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
