from contextlib import contextmanager
from pathlib import Path

from app.database import Database


def test_recent_overview_uses_bounded_reverse_rowid_scan(tmp_path: Path, monkeypatch) -> None:
    """Prevent a filter-index sort of all HTTP logs before LIMIT 8."""
    database = Database(tmp_path / "overview.db")
    database.initialize()
    with database.connect() as connection:
        connection.executemany(
            "INSERT INTO request_logs(api_key_id,project_name,action,status_code,duration_ms,log_type) "
            "VALUES ('demo-key','demo-project',?,200,1,?)",
            [(str(i), "http" if i % 2 else "http_legacy") for i in range(5000)],
        )
        connection.executemany(
            "INSERT INTO request_logs(api_key_id,project_name,action,status_code,duration_ms,log_type) "
            "VALUES ('demo-key','demo-project','internal',200,1,'upstream')", [() for _ in range(20)],
        )
    connect = database.connect

    @contextmanager
    def bounded_connect():
        with connect() as connection:
            calls = 0

            def budget():
                nonlocal calls
                calls += 1
                return int(calls > 20)

            connection.set_progress_handler(budget, 1000)
            yield connection

    monkeypatch.setattr(database, "connect", bounded_connect)
    result = database.overview()
    assert [row["action"] for row in result["recent"]] == [str(i) for i in range(4999, 4991, -1)]
    assert all(row["apiKeyName"] == "已删除 Key" for row in result["recent"])


def test_recent_overview_filters_non_http_and_handles_empty_history(tmp_path: Path) -> None:
    database = Database(tmp_path / "empty.db")
    database.initialize()
    assert database.overview()["recent"] == []
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO request_logs(api_key_id,project_name,action,status_code,duration_ms,log_type) "
            "VALUES ('demo-key','demo','upstream',200,1,'upstream')"
        )
    assert database.overview()["recent"] == []
