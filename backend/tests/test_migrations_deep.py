import sqlite3
from pathlib import Path

from app.database import Database
from app.quota import QuotaManager


LEGACY_SCHEMA = """
CREATE TABLE projects (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT
);
CREATE TABLE request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    action TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE video_usage (
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
CREATE TABLE video_tasks (
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
"""


def create_legacy_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute("INSERT INTO projects(name, display_name) VALUES ('default', 'Legacy')")
        connection.execute(
            "INSERT INTO api_keys(id,name,key_prefix,key_hash,project_name,status) "
            "VALUES ('legacy-key','Legacy key','vap_live_legacy','legacy-hash','default','revoked')"
        )
        connection.execute(
            "INSERT INTO request_logs(api_key_id,project_name,action,status_code,duration_ms) "
            "VALUES ('legacy-key','default','ListAssets',200,15)"
        )
        connection.execute(
            "INSERT INTO video_usage(api_key_id,project_name,task_id,total_tokens) "
            "VALUES ('legacy-key','default','task-1',123)"
        )
        connection.execute(
            "INSERT INTO video_tasks(api_key_id,project_name,task_id,record_json,created_at) "
            "VALUES ('legacy-key','default','task-1','{\"id\":\"task-1\"}',1)"
        )
        connection.commit()
    finally:
        connection.close()


def test_real_legacy_schema_upgrades_idempotently_and_preserves_rows(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    create_legacy_database(path)
    database = Database(path)

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        key = connection.execute("SELECT * FROM api_keys WHERE id='legacy-key'").fetchone()
        request = connection.execute("SELECT * FROM request_logs WHERE api_key_id='legacy-key'").fetchone()
        usage = connection.execute("SELECT * FROM video_usage WHERE api_key_id='legacy-key'").fetchone()
        task = connection.execute("SELECT * FROM video_tasks WHERE api_key_id='legacy-key'").fetchone()
        projects = connection.execute("SELECT name FROM projects ORDER BY name").fetchall()

    assert {
        "project_quotas",
        "api_key_quotas",
        "quota_usage_windows",
        "quota_reservations",
        "asset_records",
        "quota_events",
        "admin_audit_logs",
    } <= tables
    assert key["project_name"] == "avatar-proxy"
    assert key["status"] == "disabled"
    assert request["project_name"] == usage["project_name"] == task["project_name"] == "avatar-proxy"
    assert usage["total_tokens"] == 123
    assert [row["name"] for row in projects] == ["avatar-proxy"]


def test_new_and_upgraded_projects_default_to_unlimited(tmp_path: Path) -> None:
    path = tmp_path / "defaults.db"
    database = Database(path)
    database.initialize()
    database.create_project("new_project", "New", "")
    database.create_api_key("key-1", "Key", "prefix", "hash", "new_project")
    quota = QuotaManager(database)

    project = quota.project_quota("new_project")
    key = quota.key_quota("key-1")

    assert project["enabled"] is False
    assert all(value is None for name, value in project.items() if name not in {"projectName", "enabled"})
    assert all(value is None for name, value in key.items() if name not in {"keyId", "projectName"})
    for _ in range(20):
        quota.consume_qpm("new_project", "key-1", write=True)


def test_startup_recovers_orphan_reservations_without_negative_values(tmp_path: Path) -> None:
    path = tmp_path / "orphan.db"
    database = Database(path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO quota_usage_windows(scope_type,scope_id,metric,window_start,value,reserved) "
            "VALUES ('project','avatar-proxy','daily_upload_files','2026-08-13',3,5)"
        )
        connection.execute(
            "INSERT INTO quota_reservations(reservation_id,scope_type,scope_id,metric,window_start,amount) "
            "VALUES ('orphan-a','project','avatar-proxy','daily_upload_files','2026-08-13',2)"
        )
        connection.execute(
            "INSERT INTO quota_reservations(reservation_id,scope_type,scope_id,metric,window_start,amount) "
            "VALUES ('orphan-b','project','avatar-proxy','daily_upload_files','2026-08-13',10)"
        )

    database.initialize()

    with database.connect() as connection:
        usage = connection.execute("SELECT value,reserved FROM quota_usage_windows").fetchone()
        remaining = connection.execute("SELECT COUNT(*) FROM quota_reservations").fetchone()[0]
    assert dict(usage) == {"value": 3, "reserved": 0}
    assert remaining == 0


def test_deleted_project_recreated_with_same_name_does_not_inherit_usage_or_quota(tmp_path: Path) -> None:
    path = tmp_path / "recreate.db"
    database = Database(path)
    database.initialize()
    database.create_project("customer", "Customer", "")
    database.create_api_key("key-1", "Key", "prefix", "hash", "customer")
    quota = QuotaManager(database)
    quota.set_project_quota(
        {"project_name": "customer", "enabled": True, "daily_upload_files": 2},
        "127.0.0.1",
    )
    reservation = quota.reserve("customer", "key-1", {"daily_upload_files": 1})
    quota.finish_reservation(reservation, commit=True)

    assert database.delete_project("customer") == 1
    database.create_project("customer", "Recreated", "")

    recreated = quota.project_quota("customer")
    with database.connect() as connection:
        project_usage = connection.execute(
            "SELECT COUNT(*) FROM quota_usage_windows WHERE scope_type='project' AND scope_id='customer'"
        ).fetchone()[0]
        project_reservations = connection.execute(
            "SELECT COUNT(*) FROM quota_reservations WHERE scope_type='project' AND scope_id='customer'"
        ).fetchone()[0]
    assert recreated["enabled"] is False
    assert recreated["dailyUploadFiles"] is None
    assert project_usage == project_reservations == 0
