import sqlite3
from contextlib import contextmanager
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
CREATE INDEX IF NOT EXISTS idx_api_keys_project_status ON api_keys(project_name, status);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

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
                    SUM(CASE WHEN k.status = 'active' THEN 1 ELSE 0 END) AS activeKeyCount
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

    def project_exists(self, name: str) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM projects WHERE name = ?", (name,)).fetchone() is not None

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

    def revoke_api_key(self, key_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET status = 'revoked' WHERE id = ? AND status = 'active'", (key_id,)
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

    def overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            stats = connection.execute("""
                SELECT
                    (SELECT COUNT(*) FROM projects) AS projects,
                    (SELECT COUNT(*) FROM api_keys WHERE status = 'active') AS activeKeys,
                    (SELECT COUNT(*) FROM request_logs WHERE created_at >= datetime('now', '-24 hours')) AS requests24h,
                    (SELECT COUNT(*) FROM request_logs WHERE status_code >= 400 AND created_at >= datetime('now', '-24 hours')) AS errors24h
            """).fetchone()
            recent = connection.execute("""
                SELECT action, project_name AS projectName, status_code AS statusCode,
                    duration_ms AS durationMs, created_at AS createdAt
                FROM request_logs ORDER BY id DESC LIMIT 8
            """).fetchall()
        return {"stats": dict(stats), "recent": [dict(row) for row in recent]}
