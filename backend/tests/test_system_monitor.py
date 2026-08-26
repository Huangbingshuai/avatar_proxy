import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.errors import ApiError
from app.main import create_app
from app.system_monitor import DiskMonitor
from conftest import ADMIN_HEADERS, build_settings
from test_admin_security_deep import CHANGED_PASSWORD, enroll_super


BASE_TIME = 1_800_100_000


class Clock:
    def __init__(self, value: int = BASE_TIME) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


def disk_stats(percent: float, blocks: int = 10_000) -> SimpleNamespace:
    used = round(blocks * percent / 100)
    free = blocks - used
    return SimpleNamespace(
        f_frsize=1,
        f_bsize=1,
        f_blocks=blocks,
        f_bfree=free,
        f_bavail=free,
    )


def build_monitor(
    tmp_path: Path,
    *,
    percent: float = 10,
    clock: Clock | None = None,
    webhook: str = "",
    transport: httpx.BaseTransport | None = None,
) -> tuple[Database, DiskMonitor, Clock, dict[str, float]]:
    database = Database(tmp_path / "monitor.db")
    database.initialize()
    current = {"percent": percent}
    timer = clock or Clock()
    settings = build_settings(
        database.path,
        system_monitor_path=tmp_path,
        system_monitor_sample_interval_seconds=60,
        system_monitor_persist_interval_seconds=300,
        wecom_robot_webhook_url=webhook or None,
    )
    client = httpx.AsyncClient(transport=transport) if transport else None
    monitor = DiskMonitor(
        database,
        settings,
        clock=timer,
        statvfs=lambda _: disk_stats(current["percent"]),
        http_client=client,
    )
    return database, monitor, timer, current


def alert_rows(database: Database) -> list[dict]:
    with database.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT event_type,severity,message,details_json FROM admin_security_alerts ORDER BY id"
            ).fetchall()
        ]


def test_database_migration_defaults_are_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy.db")
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        settings = dict(connection.execute("SELECT * FROM system_monitor_settings").fetchone())
        state = dict(connection.execute("SELECT * FROM system_monitor_state").fetchone())
    assert settings["enabled"] == 1
    assert settings["warning_percent"] == 80
    assert settings["critical_percent"] == 90
    assert settings["emergency_percent"] == 95
    assert settings["recovery_percent"] == 75
    assert state["disk_alerted_levels_json"] == "[]"
    settings = build_settings(tmp_path / "fallback" / "app.db", system_monitor_path="")
    assert settings.effective_system_monitor_path == tmp_path / "fallback"


@pytest.mark.parametrize(
    ("percent", "level"),
    [(79.99, "normal"), (80, "warning"), (90, "critical"), (95, "emergency")],
)
def test_df_compatible_disk_threshold_boundaries(tmp_path: Path, percent: float, level: str) -> None:
    _, monitor, _, _ = build_monitor(tmp_path, percent=percent)
    measured = monitor._measure(BASE_TIME)
    assert measured["level"] == level
    assert measured["usedPercent"] == pytest.approx(percent, abs=0.02)
    asyncio.run(monitor.aclose())


def test_reserved_blocks_are_excluded_from_df_percentage_denominator(tmp_path: Path) -> None:
    database, monitor, _, _ = build_monitor(tmp_path)
    monitor.statvfs = lambda _: SimpleNamespace(
        f_frsize=1, f_bsize=1, f_blocks=1000, f_bfree=300, f_bavail=200
    )
    sample = monitor._measure(BASE_TIME)
    assert sample["usedBytes"] == 700
    assert sample["reservedBytes"] == 100
    assert sample["availableBytes"] == 200
    assert sample["usedPercent"] == pytest.approx(77.78, abs=0.01)
    assert alert_rows(database) == []
    asyncio.run(monitor.aclose())


def test_incident_escalation_deduplicates_across_restart_and_recovers(tmp_path: Path) -> None:
    database, monitor, timer, current = build_monitor(tmp_path, percent=80)
    asyncio.run(monitor.run_once())
    asyncio.run(monitor.run_once())
    assert [row["event_type"] for row in alert_rows(database)] == ["disk_usage_warning"]

    restarted = DiskMonitor(
        database,
        monitor.settings,
        clock=timer,
        statvfs=lambda _: disk_stats(current["percent"]),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    timer.value += 60
    asyncio.run(restarted.run_once())
    current["percent"] = 91
    timer.value += 60
    asyncio.run(restarted.run_once())
    current["percent"] = 96
    timer.value += 60
    asyncio.run(restarted.run_once())
    current["percent"] = 70
    for _ in range(5):
        timer.value += 60
        asyncio.run(restarted.run_once())

    rows = alert_rows(database)
    assert [row["event_type"] for row in rows] == [
        "disk_usage_warning",
        "disk_usage_critical",
        "disk_usage_emergency",
        "disk_usage_recovered",
    ]
    incident_ids = [json.loads(row["details_json"])["incidentId"] for row in rows]
    assert len(set(incident_ids)) == 1
    assert restarted.status()["activeIncidentId"] is None
    asyncio.run(monitor.aclose())
    asyncio.run(restarted.aclose())


def test_direct_emergency_marks_lower_thresholds_as_already_alerted(tmp_path: Path) -> None:
    database, monitor, timer, current = build_monitor(tmp_path, percent=96)
    asyncio.run(monitor.run_once())
    current["percent"] = 85
    timer.value += 60
    asyncio.run(monitor.run_once())
    current["percent"] = 92
    timer.value += 60
    asyncio.run(monitor.run_once())
    assert [row["event_type"] for row in alert_rows(database)] == ["disk_usage_emergency"]
    asyncio.run(monitor.aclose())


def test_probe_failure_alerts_after_three_failures_then_recovers(tmp_path: Path) -> None:
    database, monitor, timer, _ = build_monitor(tmp_path)
    monitor.statvfs = lambda _: (_ for _ in ()).throw(OSError("disk unavailable"))
    for _ in range(4):
        asyncio.run(monitor.run_once())
        timer.value += 60
    assert [row["event_type"] for row in alert_rows(database)] == ["disk_probe_failed"]
    assert monitor.status()["probeFailureStreak"] == 4
    assert monitor.status()["lastError"] == "磁盘探测失败（OSError）"

    monitor.statvfs = lambda _: disk_stats(20)
    asyncio.run(monitor.run_once())
    assert [row["event_type"] for row in alert_rows(database)] == [
        "disk_probe_failed",
        "disk_probe_recovered",
    ]
    assert monitor.status()["probeFailureStreak"] == 0
    asyncio.run(monitor.aclose())


def test_samples_persist_every_five_minutes_and_old_history_is_pruned(tmp_path: Path) -> None:
    database, monitor, timer, current = build_monitor(tmp_path, percent=25)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO disk_usage_samples"
            "(path,total_bytes,used_bytes,available_bytes,reserved_bytes,used_percent,level,sampled_at) "
            "VALUES ('old',100,10,90,0,10,'normal',?)",
            (BASE_TIME - 31 * 86400,),
        )
    asyncio.run(monitor.run_once())
    current["percent"] = 30
    timer.value += 299
    asyncio.run(monitor.run_once())
    assert len(monitor.history(24)) == 1
    timer.value += 1
    asyncio.run(monitor.run_once())
    history = monitor.history(24)
    assert len(history) == 2
    assert [item["usedPercent"] for item in history] == [25, 30]
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM disk_usage_samples WHERE path='old'").fetchone()[0] == 0
    asyncio.run(monitor.aclose())


def test_wecom_delivery_retries_at_expected_schedule_without_storing_secret(tmp_path: Path) -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 4:
            return httpx.Response(500, json={"errcode": 500})
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=super-secret"
    database, monitor, timer, _ = build_monitor(
        tmp_path,
        percent=80,
        webhook=webhook,
        transport=httpx.MockTransport(handler),
    )
    asyncio.run(monitor.run_once())
    for delay in (60, 300, 900):
        timer.value += delay
        asyncio.run(monitor.deliver_pending())
    with database.connect() as connection:
        delivery = dict(connection.execute("SELECT * FROM system_monitor_webhook_deliveries").fetchone())
        dump = " ".join(connection.iterdump())
    assert len(attempts) == 4
    assert delivery["status"] == "sent"
    assert delivery["attempt_count"] == 4
    assert webhook not in dump
    assert "super-secret" not in dump
    asyncio.run(monitor.aclose())


def test_failed_wecom_delivery_stops_after_four_attempts(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"errcode": 93000}))
    database, monitor, timer, _ = build_monitor(
        tmp_path, percent=80, webhook="https://example.invalid/webhook", transport=transport
    )
    asyncio.run(monitor.run_once())
    for delay in (60, 300, 900, 3600):
        timer.value += delay
        asyncio.run(monitor.deliver_pending())
    with database.connect() as connection:
        delivery = dict(connection.execute("SELECT * FROM system_monitor_webhook_deliveries").fetchone())
    assert delivery["status"] == "failed"
    assert delivery["attempt_count"] == 4
    assert "93000" in delivery["last_error"]
    asyncio.run(monitor.aclose())


def test_disabling_monitor_clears_incident_and_cancels_pending_delivery(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500, json={"errcode": 500}))
    database, monitor, _, _ = build_monitor(
        tmp_path, percent=80, webhook="https://example.invalid/webhook", transport=transport
    )
    asyncio.run(monitor.run_once())
    updated = monitor.update_settings(
        enabled=False,
        warning_percent=80,
        critical_percent=90,
        emergency_percent=95,
        recovery_percent=75,
        actor_id="owner-id",
        actor="owner",
        source_ip="127.0.0.1",
        user_agent="pytest",
    )
    with database.connect() as connection:
        state = dict(connection.execute("SELECT * FROM system_monitor_state").fetchone())
        delivery = dict(connection.execute("SELECT * FROM system_monitor_webhook_deliveries").fetchone())
    assert updated["enabled"] is False
    assert state["active_disk_incident_id"] is None
    assert delivery["status"] == "failed"
    assert delivery["last_error"] == "monitor_disabled"
    asyncio.run(monitor.aclose())


def test_super_admin_monitor_contract_reauthentication_and_audit(tmp_path: Path, monkeypatch) -> None:
    app = create_app(
        build_settings(
            tmp_path / "admin.db",
            system_monitor_enabled=False,
            system_monitor_path=tmp_path,
            wecom_robot_webhook_url="https://example.invalid/wecom-secret",
        )
    )
    with TestClient(app) as client:
        session, _, _ = enroll_super(client, app)
        headers = {"X-CSRF-Token": session["csrfToken"]}
        status = client.get("/api/internal/admin/system-monitor/status")
        assert status.status_code == 200
        assert status.json()["settings"]["webhookConfigured"] is True
        assert "wecom-secret" not in status.text

        invalid = client.put(
            "/api/internal/admin/system-monitor/settings",
            headers=headers,
            json={
                "enabled": True,
                "warningPercent": 90,
                "criticalPercent": 80,
                "emergencyPercent": 95,
                "recoveryPercent": 75,
                "currentPassword": CHANGED_PASSWORD,
            },
        )
        assert invalid.status_code == 422

        wrong_password = client.put(
            "/api/internal/admin/system-monitor/settings",
            headers=headers,
            json={
                "enabled": True,
                "warningPercent": 82,
                "criticalPercent": 91,
                "emergencyPercent": 96,
                "recoveryPercent": 74,
                "currentPassword": "wrong-password",
            },
        )
        assert wrong_password.status_code == 401

        updated = client.put(
            "/api/internal/admin/system-monitor/settings",
            headers=headers,
            json={
                "enabled": True,
                "warningPercent": 82,
                "criticalPercent": 91,
                "emergencyPercent": 96,
                "recoveryPercent": 74,
                "currentPassword": CHANGED_PASSWORD,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["settings"]["warningPercent"] == 82

        async def fake_send(message: str) -> None:
            assert "磁盘告警通道测试成功" in message

        monkeypatch.setattr(app.state.system_monitor, "_send_webhook", fake_send)
        tested = client.post(
            "/api/internal/admin/system-monitor/webhook/test",
            headers=headers,
            json={"currentPassword": CHANGED_PASSWORD},
        )
        assert tested.status_code == 200
        assert tested.json() == {"sent": True}
        history = client.get("/api/internal/admin/system-monitor/history?hours=168")
        assert history.status_code == 200
        assert history.json()["hours"] == 168

        with app.state.database.connect() as connection:
            actions = {
                row["action"]
                for row in connection.execute(
                    "SELECT action FROM admin_audit_logs WHERE action LIKE 'admin.system_monitor.%'"
                ).fetchall()
            }
        assert actions == {
            "admin.system_monitor.settings.update",
            "admin.system_monitor.webhook.test",
        }


def test_webhook_test_rejects_missing_configuration_and_audits_failure(tmp_path: Path) -> None:
    database, monitor, _, _ = build_monitor(tmp_path)
    with pytest.raises(ApiError) as captured:
        asyncio.run(
            monitor.test_webhook(
                actor_id="owner-id",
                actor="owner",
                source_ip="127.0.0.1",
                user_agent="pytest",
            )
        )
    assert captured.value.code == "wecom_webhook_not_configured"
    with database.connect() as connection:
        audit = dict(connection.execute("SELECT action,outcome,after_json FROM admin_audit_logs").fetchone())
    assert audit["action"] == "admin.system_monitor.webhook.test"
    assert audit["outcome"] == "failure"
    assert "webhook" not in audit["after_json"].lower()
    asyncio.run(monitor.aclose())


def test_business_admin_cannot_access_system_monitor(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "admin.db", system_monitor_enabled=False))
    with TestClient(app) as client:
        response = client.get(
            "/api/internal/admin/system-monitor/status",
            headers=ADMIN_HEADERS,
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "super_admin_required"
