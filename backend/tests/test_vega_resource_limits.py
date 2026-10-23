import asyncio
import json

import httpx
import pytest

from test_provider_relay import relay_client
from test_vega import setup
from app.security import ApiPrincipal
from app.vega_resources import VegaResources


@pytest.mark.parametrize("action,field,value", [
    ("CreateAigcMaterial", "GroupName", "a" * 65),
    ("ModifyAigcMaterialGroup", "GroupName", "a" * 65),
    ("ModifyAigcMaterialGroup", "GroupName", "组" * 65),
    ("ModifyAigcMaterialGroup", "GroupName", None),
    ("ModifyAigcMaterialGroup", "GroupName", 123),
    ("CreateAigcMaterial", "GroupDescription", "a" * 1025),
    ("CreateAigcMaterial", "AssetName", "a" * 1025),
])
def test_invalid_resource_text_is_rejected_before_cloud_or_task_creation(tmp_path, action, field, value):
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda request: pytest.fail("invalid input reached supplier"))
        response = client.post("/v1/vega/" + action, json={"model": "vega-1.0-pro", field: value},
                               headers={"Authorization": "Bearer " + key, "Idempotency-Key": "invalid-text"})
        assert response.status_code == 422
        assert field in response.json()["error"]["message"]
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_tasks").fetchone()[0] == 0


@pytest.mark.parametrize("custom_name", [None, "组" * 64])
def test_new_auto_group_has_short_name_without_overwriting_existing_group(tmp_path, custom_name):
    calls = []
    def supplier(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"Response": {"TaskId": "up-" + str(len(calls)), "RequestId": "req"}})
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        client.app.state.provider_relay.transport = httpx.MockTransport(supplier)
        body = {"model": "vega-1.0-pro", "FileInfo": {"Type": "Url", "Url": "https://example.com/product.png"}, "AssetType": "Image"}
        if custom_name is not None:
            body["GroupName"] = custom_name
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "first-material"}
        assert client.post("/v1/vega/CreateAigcMaterial", json=body, headers=headers).status_code == 200
        assert 1 <= len(calls[0]["GroupName"]) <= 64
        if custom_name is not None:
            assert calls[0]["GroupName"] == custom_name
        # A replay is still the same task despite service-injected defaults.
        assert client.post("/v1/vega/CreateAigcMaterial", json=body, headers=headers).status_code == 200
        assert len(calls) == 1
        headers["Idempotency-Key"] = "second-material"
        body.pop("GroupName", None)
        assert client.post("/v1/vega/CreateAigcMaterial", json=body, headers=headers).status_code == 200
        assert "GroupName" not in calls[1]
        assert calls[1]["GroupId"] == calls[0]["GroupId"]


@pytest.mark.parametrize("action", ["CreateAigcMaterial", "CreateAigcLivenessValidate"])
@pytest.mark.parametrize("failure", ["rejected", "timeout", "missing_fields"])
def test_create_failures_are_saved_and_idempotent_replay_never_resubmits(tmp_path, action, failure):
    calls = []
    def supplier(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("read failed", request=request)
        response = {"RequestId": "rejected-request"}
        if failure == "rejected":
            response["Error"] = {"Code": "AuthFailure.UnauthorizedOperation", "Message": "Access denied"}
        return httpx.Response(200, json={"Response": response})
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        client.app.state.provider_relay.transport = httpx.MockTransport(supplier)
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "failed-material"}
        body = {"model": "vega-1.0-pro"}
        if action == "CreateAigcMaterial":
            body.update({"FileInfo": {"Type": "Url", "Url": "https://example.com/product.png"}, "AssetType": "Image"})
        first = client.post("/v1/vega/" + action, json=body, headers=headers)
        assert first.status_code in (502, 504)
        details = first.json()["error"]["details"]
        assert details["outcomeUnknown"] is (failure != "rejected")
        assert details["automaticRetry"] is False
        task_id = details["taskId"]
        with client.app.state.database.connect() as connection:
            saved = connection.execute("SELECT * FROM inference_tasks WHERE id=?", (task_id,)).fetchone()
            assert saved["status"] == "failed" and saved["completed_at"] is not None
            assert json.loads(saved["metadata_json"])["outcomeUnknown"] is (failure != "rejected")
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM vega_resources").fetchone()[0] == 0
        replay = client.post("/v1/vega/" + action, json=body, headers=headers)
        assert replay.status_code == (502 if failure == "rejected" else 409)
        assert replay.json()["error"]["details"]["taskId"] == task_id
        assert len(calls) == 1
        if failure == "rejected":
            assert replay.json()["error"]["details"]["upstreamRequestId"] == "rejected-request"
        if action == "CreateAigcMaterial":
            query = client.post("/v1/vega/DescribeTaskDetail", json={"model": body["model"], "TaskId": task_id}, headers=headers)
            assert query.status_code == 200
            assert query.json()["status"] == "failed" and query.json()["error"]["code"] == saved["error_code"]
            assert query.json()["outcomeUnknown"] is (failure != "rejected")
            assert len(calls) == 1


@pytest.mark.parametrize("action", ["CreateAigcMaterial", "CreateAigcLivenessValidate"])
def test_create_cancellation_is_unknown_not_permanently_queued(tmp_path, action):
    with relay_client(tmp_path) as client:
        key_id, _, _ = setup(client)
        relay = client.app.state.provider_relay
        async def interrupted(*args):
            raise asyncio.CancelledError()
        relay._vega_request = interrupted
        body = {"FileInfo": {"Type": "Url", "Url": "https://example.com/product.png"}, "AssetType": "Image"} if action == "CreateAigcMaterial" else {}
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(VegaResources(relay).call(ApiPrincipal(key_id, "vega_project"), "vega-1.0-pro", action, body, "cancelled"))
        with client.app.state.database.connect() as connection:
            saved = connection.execute("SELECT * FROM inference_tasks").fetchone()
            assert saved["status"] == "failed" and saved["error_code"] == "provider_outcome_unknown"
            assert json.loads(saved["metadata_json"])["outcomeUnknown"] is True


def test_startup_recovery_preserves_accepted_and_completed_materials(tmp_path):
    with relay_client(tmp_path) as client:
        key_id, _, _ = setup(client)
        relay = client.app.state.provider_relay
        principal = ApiPrincipal(key_id, "vega_project")
        route = relay.resolve(principal, "vega-1.0-pro")
        tasks = {}
        for label, operation in [("interrupted", "vega_CreateAigcMaterial"), ("accepted", "vega_CreateAigcMaterial"),
                                 ("liveness", "vega_CreateAigcLivenessValidate"), ("complete", "vega_CreateAigcMaterial")]:
            task, _ = relay._create_task(principal, route, operation, {"label": label}, label)
            tasks[label] = task["id"]
        with client.app.state.database.connect() as connection:
            connection.execute("UPDATE inference_tasks SET upstream_task_id='upstream' WHERE id=?", (tasks["accepted"],))
            connection.execute("UPDATE inference_tasks SET status='succeeded' WHERE id=?", (tasks["complete"],))
        resources = VegaResources(relay)
        resources.recover_interrupted_creates()
        resources.recover_interrupted_creates()
        with client.app.state.database.connect() as connection:
            saved = {row["id"]: row for row in connection.execute("SELECT * FROM inference_tasks")}
            for label in ("interrupted", "liveness"):
                assert saved[tasks[label]]["status"] == "failed"
                assert saved[tasks[label]]["error_code"] == "provider_outcome_unknown"
                assert json.loads(saved[tasks[label]]["metadata_json"])["outcomeUnknown"] is True
            assert saved[tasks["accepted"]]["status"] == "queued"
            assert saved[tasks["complete"]]["status"] == "succeeded"
