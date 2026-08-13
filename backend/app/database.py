import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT,
    FOREIGN KEY(project_name) REFERENCES projects(name)
);
CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    action TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS video_usage (
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    task_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(api_key_id, task_id)
);
CREATE TABLE IF NOT EXISTS video_tasks (
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    task_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hidden INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(api_key_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_api_keys_project_status ON api_keys(project_name, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name_nocase ON projects(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_video_usage_api_key_created_at ON video_usage(api_key_id, created_at);
CREATE INDEX IF NOT EXISTS idx_video_tasks_api_key_created_at ON video_tasks(api_key_id, created_at DESC);
CREATE TABLE IF NOT EXISTS project_quotas (
    project_name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    read_qpm INTEGER,
    write_qpm INTEGER,
    max_concurrency INTEGER,
    daily_asset_creates INTEGER,
    daily_upload_files INTEGER,
    daily_upload_bytes INTEGER,
    total_assets INTEGER,
    total_storage_bytes INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS api_key_quotas (
    api_key_id TEXT PRIMARY KEY,
    read_qpm INTEGER,
    write_qpm INTEGER,
    max_concurrency INTEGER,
    daily_asset_creates INTEGER,
    daily_upload_files INTEGER,
    daily_upload_bytes INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS quota_usage_windows (
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    window_start TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    reserved INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(scope_type, scope_id, metric, window_start)
);
CREATE TABLE IF NOT EXISTS quota_reservations (
    reservation_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    window_start TEXT NOT NULL,
    amount INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(reservation_id, scope_type, scope_id, metric)
);
CREATE TABLE IF NOT EXISTS asset_records (
    record_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    api_key_id TEXT NOT NULL,
    group_id TEXT,
    asset_id TEXT,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    bucket TEXT,
    object_key TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    cleanup_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS quota_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    api_key_id TEXT,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    threshold INTEGER NOT NULL,
    limit_value INTEGER NOT NULL,
    used_value INTEGER NOT NULL,
    window_start TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TEXT,
    UNIQUE(scope_type, scope_id, metric, threshold, window_start)
);
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    source_ip TEXT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quota_events_open ON quota_events(acknowledged, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_asset_records_project_status ON asset_records(project_name, status);
CREATE INDEX IF NOT EXISTS idx_asset_records_asset_id ON asset_records(project_name, asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_records_cleanup ON asset_records(status, updated_at);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("UPDATE api_keys SET status = 'disabled' WHERE status = 'revoked'")
            # A process can stop after reserving quota but before committing or rolling it
            # back. No requests are in flight during startup, so all persisted reservations
            # are orphaned and can be released safely.
            reservations = connection.execute(
                "SELECT scope_type, scope_id, metric, window_start, amount FROM quota_reservations"
            ).fetchall()
            for reservation in reservations:
                connection.execute(
                    "UPDATE quota_usage_windows SET reserved=MAX(0,reserved-?) "
                    "WHERE scope_type=? AND scope_id=? AND metric=? AND window_start=?",
                    (
                        reservation["amount"], reservation["scope_type"], reservation["scope_id"],
                        reservation["metric"], reservation["window_start"],
                    ),
                )
            connection.execute("DELETE FROM quota_reservations")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT p.name, p.display_name AS displayName, p.description, p.created_at AS createdAt,
                    COUNT(k.id) AS keyCount,
                    SUM(CASE WHEN k.status = 'active' THEN 1 ELSE 0 END) AS activeKeyCount,
                    (SELECT COUNT(*) FROM asset_records a
                     WHERE a.project_name = p.name AND a.status != 'deleted') AS activeAssetCount
                FROM projects p LEFT JOIN api_keys k ON k.project_name = p.name
                GROUP BY p.name ORDER BY p.created_at DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def create_project(self, name: str, display_name: str, description: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO projects (name, display_name, description) VALUES (?, ?, ?)",
                (name, display_name, description),
            )
        return {"name": name, "displayName": display_name, "description": description}

    def resolve_project_name(self, name: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name FROM projects WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
        return row["name"] if row else None

    def delete_project(self, name: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name FROM projects WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            if row is None:
                return None
            canonical_name = row["name"]
            key_count = connection.execute(
                "SELECT COUNT(*) FROM api_keys WHERE project_name = ?",
                (canonical_name,),
            ).fetchone()[0]
            asset_count = connection.execute(
                "SELECT COUNT(*) FROM asset_records WHERE project_name = ? AND status != 'deleted'",
                (canonical_name,),
            ).fetchone()[0]
            if key_count or asset_count:
                return {
                    "deleted": False,
                    "projectName": canonical_name,
                    "keyCount": key_count,
                    "assetCount": asset_count,
                }
            connection.execute(
                "DELETE FROM quota_reservations WHERE scope_type='project' AND scope_id=?",
                (canonical_name,),
            )
            connection.execute(
                "DELETE FROM quota_usage_windows WHERE scope_type='project' AND scope_id=?",
                (canonical_name,),
            )
            connection.execute("DELETE FROM projects WHERE name = ?", (canonical_name,))
        return {"deleted": True, "projectName": canonical_name, "keyCount": 0, "assetCount": 0}

    def project_exists(self, name: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM projects WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone() is not None

    def list_api_keys(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT id, name, key_prefix AS keyPrefix, project_name AS projectName, status,
                    created_at AS createdAt, last_used_at AS lastUsedAt
                FROM api_keys ORDER BY created_at DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def create_api_key(self, key_id: str, name: str, prefix: str, key_hash: str, project_name: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO api_keys (id, name, key_prefix, key_hash, project_name) VALUES (?, ?, ?, ?, ?)",
                (key_id, name, prefix, key_hash, project_name),
            )

    def disable_api_key(self, key_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET status = 'disabled' WHERE id = ? AND status = 'active'", (key_id,)
            )
        return cursor.rowcount > 0

    def enable_api_key(self, key_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM api_keys WHERE id = ?",
                (key_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "disabled":
                return "active"
            connection.execute(
                "UPDATE api_keys SET status = 'active' WHERE id = ?",
                (key_id,),
            )
        return "enabled"

    def delete_api_key(self, key_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM api_keys WHERE id = ?",
                (key_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "disabled":
                return "active"
            connection.execute("DELETE FROM request_logs WHERE api_key_id = ?", (key_id,))
            connection.execute("DELETE FROM video_usage WHERE api_key_id = ?", (key_id,))
            connection.execute("DELETE FROM video_tasks WHERE api_key_id = ?", (key_id,))
            connection.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        return "deleted"

    def bind_api_key_project(self, key_id: str, project_name: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET project_name = ? WHERE id = ?",
                (project_name, key_id),
            )
        return cursor.rowcount > 0

    def find_api_key(self, key_hash: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, project_name AS projectName FROM api_keys WHERE key_hash = ? AND status = 'active' LIMIT 1",
                (key_hash,),
            ).fetchone()
        return self._dict(row)

    def touch_api_key(self, key_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (key_id,))

    def log_request(self, key_id: str, project_name: str, action: str, status_code: int, duration_ms: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO request_logs (api_key_id, project_name, action, status_code, duration_ms) VALUES (?, ?, ?, ?, ?)",
                (key_id, project_name, action, status_code, duration_ms),
            )

    def upsert_video_usage(
        self,
        key_id: str,
        project_name: str,
        task_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        created_at: str | None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO video_usage (
                    api_key_id, project_name, task_id, model,
                    input_tokens, output_tokens, total_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(api_key_id, task_id) DO UPDATE SET
                    model = CASE WHEN excluded.model != '' THEN excluded.model ELSE video_usage.model END,
                    input_tokens = MAX(video_usage.input_tokens, excluded.input_tokens),
                    output_tokens = MAX(video_usage.output_tokens, excluded.output_tokens),
                    total_tokens = MAX(video_usage.total_tokens, excluded.total_tokens),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    key_id, project_name, task_id, model,
                    input_tokens, output_tokens, total_tokens, created_at,
                ),
            )

    def video_usage(self, key_id: str, days: int) -> dict[str, Any]:
        with self.connect() as connection:
            summary = connection.execute(
                """
                SELECT
                    COALESCE(SUM(input_tokens), 0) AS inputTokens,
                    COALESCE(SUM(output_tokens), 0) AS outputTokens,
                    COALESCE(SUM(total_tokens), 0) AS totalTokens,
                    COUNT(*) AS requestCount
                FROM video_usage
                WHERE api_key_id = ? AND date(created_at) >= date('now', ?)
                """,
                (key_id, f"-{days - 1} days"),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT date(created_at) AS date,
                    COALESCE(SUM(input_tokens), 0) AS inputTokens,
                    COALESCE(SUM(output_tokens), 0) AS outputTokens,
                    COALESCE(SUM(total_tokens), 0) AS totalTokens,
                    COUNT(*) AS requestCount
                FROM video_usage
                WHERE api_key_id = ? AND date(created_at) >= date('now', ?)
                GROUP BY date(created_at)
                ORDER BY date(created_at)
                """,
                (key_id, f"-{days - 1} days"),
            ).fetchall()
            start = connection.execute(
                "SELECT date('now', ?) AS date", (f"-{days - 1} days",)
            ).fetchone()["date"]

        by_date = {row["date"]: dict(row) for row in rows}
        cursor = date.fromisoformat(start)
        daily = []
        for offset in range(days):
            day = (cursor + timedelta(days=offset)).isoformat()
            daily.append(by_date.get(day, {
                "date": day, "inputTokens": 0, "outputTokens": 0,
                "totalTokens": 0, "requestCount": 0,
            }))
        return {"summary": dict(summary), "daily": daily}

    def save_video_task(
        self,
        key_id: str,
        project_name: str,
        task_id: str,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT record_json FROM video_tasks WHERE api_key_id = ? AND task_id = ?",
                (key_id, task_id),
            ).fetchone()
            current: dict[str, Any] = {}
            if existing:
                try:
                    decoded = json.loads(existing["record_json"])
                    if isinstance(decoded, dict):
                        current = decoded
                except (TypeError, ValueError):
                    current = {}
            merged = {**current, **{key: value for key, value in record.items() if value is not None}}
            merged["id"] = task_id
            created_at = int(merged.get("createdAt") or current.get("createdAt") or 0)
            status = str(merged.get("status") or "queued")
            connection.execute(
                """
                INSERT INTO video_tasks (
                    api_key_id, project_name, task_id, record_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(api_key_id, task_id) DO UPDATE SET
                    project_name = excluded.project_name,
                    record_json = excluded.record_json,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    key_id, project_name, task_id,
                    json.dumps(merged, ensure_ascii=False, separators=(",", ":")),
                    status, created_at,
                ),
            )
        return merged

    def list_video_tasks(self, key_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json FROM video_tasks
                WHERE api_key_id = ? AND hidden = 0
                ORDER BY created_at DESC, updated_at DESC
                LIMIT ?
                """,
                (key_id, limit),
            ).fetchall()
        tasks: list[dict[str, Any]] = []
        for row in rows:
            try:
                record = json.loads(row["record_json"])
            except (TypeError, ValueError):
                continue
            if isinstance(record, dict) and record.get("id"):
                tasks.append(record)
        return tasks

    def hide_video_task(self, key_id: str, task_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE video_tasks SET hidden = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE api_key_id = ? AND task_id = ? AND hidden = 0",
                (key_id, task_id),
            )
        return cursor.rowcount > 0

    def hide_all_video_tasks(self, key_id: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE video_tasks SET hidden = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE api_key_id = ? AND hidden = 0",
                (key_id,),
            )
        return cursor.rowcount

    def create_asset_record(
        self,
        record_id: str,
        project_name: str,
        key_id: str,
        source_type: str,
        source_url: str,
        *,
        bucket: str | None = None,
        object_key: str | None = None,
        size_bytes: int = 0,
        status: str = "uploaded_pending",
        group_id: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO asset_records "
                "(record_id, project_name, api_key_id, group_id, source_type, source_url, bucket, object_key, size_bytes, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, project_name, key_id, group_id, source_type, source_url, bucket, object_key, size_bytes, status),
            )
        return self.get_asset_record(record_id) or {}

    def get_asset_record(self, record_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM asset_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        return self._dict(row)

    def find_upload_record(
        self, project_name: str, key_id: str, *, upload_id: str | None = None, source_url: str | None = None,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            if upload_id:
                row = connection.execute(
                    "SELECT * FROM asset_records WHERE record_id=? AND project_name=? AND api_key_id=? "
                    "AND source_type='tos' AND status IN ('uploaded_pending','registration_failed')",
                    (upload_id, project_name, key_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM asset_records WHERE project_name=? AND api_key_id=? AND source_url=? "
                    "AND source_type='tos' AND status IN ('uploaded_pending','registration_failed') "
                    "ORDER BY created_at DESC LIMIT 1",
                    (project_name, key_id, source_url),
                ).fetchone()
        return self._dict(row)

    def update_asset_record(
        self,
        record_id: str,
        status: str,
        *,
        group_id: str | None = None,
        asset_id: str | None = None,
        last_error: str | None = None,
        deleted: bool = False,
        increment_cleanup: bool = False,
    ) -> None:
        assignments = ["status=?", "updated_at=CURRENT_TIMESTAMP", "last_error=?"]
        values: list[Any] = [status, last_error]
        if group_id is not None:
            assignments.append("group_id=?")
            values.append(group_id)
        if asset_id is not None:
            assignments.append("asset_id=?")
            values.append(asset_id)
        if deleted:
            assignments.append("deleted_at=CURRENT_TIMESTAMP")
        if increment_cleanup:
            assignments.append("cleanup_attempts=cleanup_attempts+1")
        values.append(record_id)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE asset_records SET {', '.join(assignments)} WHERE record_id=?", values
            )

    def find_asset_by_asset_id(self, project_name: str, asset_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM asset_records WHERE project_name=? AND asset_id=? AND status!='deleted' LIMIT 1",
                (project_name, asset_id),
            ).fetchone()
        return self._dict(row)

    def cleanup_candidates(self, hours: int = 48, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM asset_records WHERE source_type='tos' AND ("
                "status='cleanup_pending' OR (status IN ('uploaded_pending','registration_failed') "
                "AND created_at <= datetime('now', ?))) ORDER BY updated_at LIMIT ?",
                (f"-{hours} hours", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_cleanup_objects(self, project_name: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT record_id AS recordId, object_key AS objectKey, size_bytes AS sizeBytes, "
                "status, cleanup_attempts AS cleanupAttempts, last_error AS lastError, "
                "created_at AS createdAt, updated_at AS updatedAt "
                "FROM asset_records WHERE project_name=? AND source_type='tos' "
                "AND status IN ('uploaded_pending','registration_failed','cleanup_pending') "
                "ORDER BY updated_at LIMIT ?",
                (project_name, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            stats = connection.execute("""
                SELECT
                    (SELECT COUNT(*) FROM projects) AS projects,
                    (SELECT COUNT(*) FROM api_keys WHERE status = 'active') AS activeKeys,
                    (SELECT COUNT(*) FROM request_logs WHERE created_at >= datetime('now', '-24 hours')) AS requests24h,
                    (SELECT COUNT(*) FROM request_logs WHERE status_code >= 400 AND created_at >= datetime('now', '-24 hours')) AS errors24h,
                    (SELECT COUNT(*) FROM asset_records WHERE status IN ('registering','active') AND date(created_at, '+8 hours')=date('now', '+8 hours')) AS assetsToday,
                    (SELECT COUNT(*) FROM asset_records WHERE source_type='tos' AND date(created_at, '+8 hours')=date('now', '+8 hours')) AS uploadsToday,
                    (SELECT COALESCE(SUM(size_bytes),0) FROM asset_records WHERE source_type='tos' AND date(created_at, '+8 hours')=date('now', '+8 hours')) AS uploadBytesToday,
                    (SELECT COUNT(DISTINCT project_name) FROM project_quotas WHERE enabled=1) AS limitedProjects,
                    (SELECT COUNT(*) FROM quota_events WHERE acknowledged=0) AS openQuotaEvents,
                    (SELECT COUNT(*) FROM asset_records WHERE status='cleanup_pending') AS cleanupPending
            """).fetchone()
            recent = connection.execute("""
                SELECT action, project_name AS projectName, status_code AS statusCode,
                    duration_ms AS durationMs, created_at AS createdAt
                FROM request_logs ORDER BY id DESC LIMIT 8
            """).fetchall()
        return {"stats": dict(stats), "recent": [dict(row) for row in recent]}
