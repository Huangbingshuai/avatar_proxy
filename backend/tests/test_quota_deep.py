import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.database import Database
from app.errors import ApiError
from app.main import create_app
from app.quota import QuotaManager, SHANGHAI

from conftest import ADMIN_HEADERS, FakeVolcengine, build_settings, create_key, create_project


def direct_quota(path: Path, *, project_limit: dict | None = None, key_limits: list[dict] | None = None):
    database = Database(path)
    database.initialize()
    database.create_project("drama_prod", "Drama", "")
    key_ids = ["key-a", "key-b"]
    for key_id in key_ids:
        database.create_api_key(key_id, key_id, f"{key_id}…", f"hash-{key_id}", "drama_prod")
    quota = QuotaManager(database)
    quota.set_project_quota(
        {"project_name": "drama_prod", "enabled": True, **(project_limit or {})},
        "127.0.0.1",
    )
    for index, limits in enumerate(key_limits or []):
        quota.set_key_quota({"key_id": key_ids[index], **limits}, "127.0.0.1")
    return database, quota, key_ids


def test_project_and_key_use_the_stricter_limit_and_disable_means_unlimited(tmp_path: Path) -> None:
    _, quota, (key_id, _) = direct_quota(
        tmp_path / "quota.db",
        project_limit={"write_qpm": 5},
        key_limits=[{"write_qpm": 2}],
    )

    quota.consume_qpm("drama_prod", key_id, write=True)
    quota.consume_qpm("drama_prod", key_id, write=True)
    with pytest.raises(ApiError) as caught:
        quota.consume_qpm("drama_prod", key_id, write=True)
    assert caught.value.details["scope"] == "api_key"

    quota.set_project_quota(
        {"project_name": "drama_prod", "enabled": False, "write_qpm": 1},
        "127.0.0.1",
    )
    for _ in range(10):
        quota.consume_qpm("drama_prod", key_id, write=True)


def test_dynamic_quota_changes_take_effect_without_restart(tmp_path: Path) -> None:
    _, quota, (key_id, _) = direct_quota(tmp_path / "quota.db", project_limit={"write_qpm": 10})
    for _ in range(3):
        quota.consume_qpm("drama_prod", key_id, write=True)

    quota.set_project_quota(
        {"project_name": "drama_prod", "enabled": True, "write_qpm": 3},
        "127.0.0.1",
    )
    with pytest.raises(ApiError):
        quota.consume_qpm("drama_prod", key_id, write=True)


def test_minute_and_beijing_day_windows_reset_independently(tmp_path: Path, monkeypatch) -> None:
    _, quota, (key_id, _) = direct_quota(
        tmp_path / "quota.db",
        project_limit={"write_qpm": 1, "daily_upload_files": 1},
    )
    now = datetime.now(SHANGHAI)
    windows = [
        ("2026-08-13T23:59:00+08:00", "2026-08-13", now + timedelta(seconds=15), now + timedelta(seconds=15)),
        ("2026-08-14T00:00:00+08:00", "2026-08-14", now + timedelta(minutes=1), now + timedelta(days=1)),
    ]
    monkeypatch.setattr(quota, "_windows", lambda: windows[0])
    quota.consume_qpm("drama_prod", key_id, write=True)
    reservation = quota.reserve("drama_prod", key_id, {"daily_upload_files": 1})
    quota.finish_reservation(reservation, commit=True)
    with pytest.raises(ApiError):
        quota.consume_qpm("drama_prod", key_id, write=True)
    with pytest.raises(ApiError):
        quota.reserve("drama_prod", key_id, {"daily_upload_files": 1})

    monkeypatch.setattr(quota, "_windows", lambda: windows[1])
    quota.consume_qpm("drama_prod", key_id, write=True)
    reservation = quota.reserve("drama_prod", key_id, {"daily_upload_files": 1})
    quota.finish_reservation(reservation, commit=True)


def test_429_contract_retry_after_and_cors_exposure(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "quota.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.volcengine = FakeVolcengine()
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "writeQpm": 1},
        )
        headers = {"Authorization": f"Bearer {secret}", "Origin": "http://localhost:3000"}
        assert client.post("/api/asset-group/create", headers=headers, json={"name": "one"}).status_code == 200
        response = client.post("/api/asset-group/create", headers=headers, json={"name": "two"})

    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "quota_exceeded"
    assert {"metric", "scope", "limit", "used", "resetAt", "requestId"} <= error.keys()
    assert error["metric"] == "writeQpm"
    assert error["scope"] == "project"
    assert error["limit"] == error["used"] == 1
    assert error["resetAt"].endswith("+08:00")
    assert error["requestId"].startswith("req_")
    assert int(response.headers["retry-after"]) >= 1
    assert "Retry-After" in response.headers["access-control-expose-headers"]


def test_total_limit_has_no_reset_or_retry_after(tmp_path: Path) -> None:
    _, quota, (key_id, _) = direct_quota(
        tmp_path / "quota.db",
        project_limit={"total_storage_bytes": 1},
    )
    with pytest.raises(ApiError) as caught:
        quota.reserve("drama_prod", key_id, {"total_storage_bytes": 2})

    assert caught.value.details["resetAt"] is None
    assert caught.value.headers == {}


def test_alert_thresholds_are_deduplicated_and_acknowledged(tmp_path: Path) -> None:
    _, quota, (key_id, _) = direct_quota(tmp_path / "quota.db", project_limit={"read_qpm": 10})
    for _ in range(25):
        quota.consume_qpm("drama_prod", key_id, write=False)
    events = [event for event in quota.events() if event["metric"] == "read_qpm"]
    assert {event["threshold"] for event in events} == {70, 90, 100}
    assert len(events) == 3

    event_id = events[0]["id"]
    assert quota.acknowledge(event_id) is True
    assert quota.acknowledge(event_id) is False
    assert quota.acknowledge(999999) is False


def test_internal_quota_endpoints_report_missing_targets_and_invalid_ack(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "internal-errors.db"))
    with TestClient(app) as client:
        missing_project = client.get(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            params={"projectName": "missing"},
        )
        missing_key = client.get(
            "/api/internal/apikey/quota",
            headers=ADMIN_HEADERS,
            params={"keyId": "missing"},
        )
        invalid_ack = client.post(
            "/api/internal/quota/event/ack",
            headers=ADMIN_HEADERS,
            json={"eventId": 999999},
        )

    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"
    assert missing_key.status_code == 404
    assert missing_key.json()["error"]["code"] == "api_key_not_found"
    assert invalid_ack.status_code == 404
    assert invalid_ack.json()["error"]["code"] == "quota_event_not_found"


@pytest.mark.asyncio
async def test_write_concurrency_rejects_then_releases_after_exception_and_cancel(tmp_path: Path) -> None:
    _, quota, (key_id, _) = direct_quota(
        tmp_path / "quota.db",
        project_limit={"write_qpm": 100, "max_concurrency": 2},
        key_limits=[{"max_concurrency": 1}],
    )
    async with quota.request_slot("drama_prod", key_id, write=True):
        with pytest.raises(ApiError) as caught:
            async with quota.request_slot("drama_prod", key_id, write=True):
                pass
        assert caught.value.details["metric"] == "maxConcurrency"
        assert caught.value.details["scope"] == "api_key"

    with pytest.raises(RuntimeError):
        async with quota.request_slot("drama_prod", key_id, write=True):
            raise RuntimeError("boom")

    entered = asyncio.Event()

    async def holder() -> None:
        async with quota.request_slot("drama_prod", key_id, write=True):
            entered.set()
            await asyncio.sleep(30)

    task = asyncio.create_task(holder())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with quota.request_slot("drama_prod", key_id, write=True):
        pass
    assert all(value == 0 for value in quota._concurrency.values())


def test_hundreds_of_concurrent_qpm_requests_do_not_cross_hard_limit(tmp_path: Path, monkeypatch) -> None:
    database, quota, (key_id, _) = direct_quota(
        tmp_path / "qpm-concurrent.db",
        project_limit={"write_qpm": 75},
    )
    now = datetime.now(SHANGHAI)
    monkeypatch.setattr(
        quota,
        "_windows",
        lambda: ("2026-08-13T12:00:00+08:00", "2026-08-13", now + timedelta(minutes=1), now + timedelta(days=1)),
    )
    barrier = Barrier(32)

    def attempt(_: int) -> bool:
        barrier.wait(timeout=10)
        try:
            quota.consume_qpm("drama_prod", key_id, write=True)
            return True
        except ApiError as error:
            assert error.status_code == 429
            return False

    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = list(executor.map(attempt, range(256)))

    assert sum(outcomes) == 75
    with database.connect() as connection:
        row = connection.execute(
            "SELECT value, reserved FROM quota_usage_windows WHERE scope_type='project' AND scope_id='drama_prod' "
            "AND metric='write_qpm'"
        ).fetchone()
    assert dict(row) == {"value": 75, "reserved": 0}


def test_concurrent_multi_key_reservations_share_project_limit_without_residue(tmp_path: Path) -> None:
    database, quota, key_ids = direct_quota(
        tmp_path / "reserve-concurrent.db",
        project_limit={"daily_upload_files": 40},
        key_limits=[{"daily_upload_files": 30}, {"daily_upload_files": 30}],
    )
    barrier = Barrier(32)
    successes = {key_ids[0]: 0, key_ids[1]: 0}
    result_lock = Lock()

    def attempt(index: int) -> bool:
        barrier.wait(timeout=10)
        key_id = key_ids[index % 2]
        try:
            reservation = quota.reserve("drama_prod", key_id, {"daily_upload_files": 1})
        except ApiError:
            return False
        quota.finish_reservation(reservation, commit=True)
        with result_lock:
            successes[key_id] += 1
        return True

    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = list(executor.map(attempt, range(256)))

    assert sum(outcomes) == 40
    assert all(value <= 30 for value in successes.values())
    with database.connect() as connection:
        rows = connection.execute("SELECT value, reserved FROM quota_usage_windows").fetchall()
        reservations = connection.execute("SELECT COUNT(*) FROM quota_reservations").fetchone()[0]
    assert reservations == 0
    assert rows
    assert all(row["value"] >= 0 and row["reserved"] == 0 for row in rows)


def test_concurrent_read_overage_is_allowed_without_duplicate_events(tmp_path: Path, monkeypatch) -> None:
    _, quota, (key_id, _) = direct_quota(
        tmp_path / "read-concurrent.db",
        project_limit={"read_qpm": 20},
    )
    now = datetime.now(SHANGHAI)
    monkeypatch.setattr(
        quota,
        "_windows",
        lambda: ("2026-08-13T12:00:00+08:00", "2026-08-13", now + timedelta(minutes=1), now + timedelta(days=1)),
    )
    barrier = Barrier(20)

    def read(_: int) -> None:
        barrier.wait(timeout=10)
        quota.consume_qpm("drama_prod", key_id, write=False)

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(read, range(200)))

    events = [event for event in quota.events(500) if event["metric"] == "read_qpm"]
    assert len(events) == 3
    assert {event["threshold"] for event in events} == {70, 90, 100}


def test_delete_is_not_blocked_by_asset_or_storage_total_limits(tmp_path: Path) -> None:
    class DeletingVolcengine:
        async def call(self, action, payload, principal):
            return JSONResponse({"ok": True, "action": action})

    app = create_app(build_settings(tmp_path / "delete.db"))
    with TestClient(app) as client:
        create_project(client)
        key_id, secret = create_key(client)
        app.state.volcengine = DeletingVolcengine()
        app.state.database.create_asset_record(
            "external-1",
            "drama_prod",
            key_id,
            "external_url",
            "https://example.com/image.png",
            status="active",
            group_id="group-1",
        )
        app.state.database.update_asset_record("external-1", "active", asset_id="asset-1")
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={"projectName": "drama_prod", "enabled": True, "totalAssets": 1, "totalStorageBytes": 1},
        )
        response = client.delete(
            "/api/asset/delete",
            headers={"Authorization": f"Bearer {secret}"},
            params={"assetId": "asset-1"},
        )

    assert response.status_code == 200
