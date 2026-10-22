"""Vega contracts: mock HTTP and temporary SQLite, never billable cloud calls."""
import asyncio
import hashlib
import hmac
import json
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.billing import BillingManager, current_month
from app.database import Database, SCHEMA
from app.errors import ApiError
from app.vega import (VEGA_FX, VEGA_MODEL_CATALOG, VEGA_RATES, VERSIONS, channel_config,
                      credentials, measurements, signed_request, submit_payload, video_result)
from conftest import create_key, create_project
from test_provider_relay import relay_client

TASKS = "/api/v3/contents/generations/tasks"
SECRET = json.dumps({"secretId": "example-id-12345678", "secretKey": "example-key-12345678"})


def setup(client, version="1.0-pro", site="domestic", project="vega_project"):
    create_project(client, project)
    key_id, key = create_key(client, project, "vega-key")
    relay = client.app.state.provider_relay
    channel = relay.create_channel(project_name=project, name="Vega", provider="vega",
                                   config={"site": site, "subAppId": "123456"}, secret=SECRET, actor_id="super")
    relay.set_project_models(project, [{"model": "vega-" + version, "channelId": channel["id"], "enabled": True}], "admin")
    return key_id, key, channel


def request_body(version="1.0-pro", **extra):
    return {"model": "vega-" + version, "content": [{"type": "text", "text": "小船缓慢驶过海面"}],
            "duration": 4, **extra}


def finish(version, *, usage=None, error=0):
    return {"Response": {"RequestId": "request-query", "Status": "FINISH", "AigcVideoTask": {
        "Status": "FINISH", "ErrCode": error, "ErrCodeExt": "Blocked" if error else "", "Message": "blocked" if error else "",
        "Input": {"OutputConfig": {"Resolution": "768P" if version == "1.0-lite" else "720P", "AspectRatio": "16:9"}},
        "Output": {"Usage": usage if usage is not None else {"OutputSeconds": 4, "InputSeconds": 0,
            "InputImageCount": 0, "CompletionTokens": 1200, "TotalTokens": 1300},
            "FileInfos": [{"FileUrl": "https://example.com/video.mp4", "UsageType": "", "MetaData": {"Duration": 4}},
                          {"FileUrl": "https://example.com/last.png", "UsageType": "last_frame_url"}]}}}}


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("site", ["domestic", "international"])
def test_videos_contract_credentials_pin_idempotency_usage_and_logs(tmp_path, version, site):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == ("vod.tencentcloudapi.com" if site == "domestic" else "vod.intl.tencentcloudapi.com")
        assert request.url.path == "/" and request.method == "POST"
        assert "example-id-12345678" in request.headers["Authorization"]
        body = json.loads(request.content)
        assert body["SubAppId"] == 123456
        if request.headers["X-TC-Action"] == "CreateAigcVideoTask":
            assert body["ModelName"] == "wand-vega-video" and body["ModelVersion"] == version
            assert body["OutputConfig"]["Duration"] == 4
            assert body["OutputConfig"]["StorageMode"] == "Temporary"
            ext = json.loads(body["ExtInfo"])
            assert json.loads(ext["WandVegaParameters"])["ReturnVegaUsage"] is True
            return httpx.Response(200, json={"Response": {"TaskId": "upstream-video", "RequestId": "request-create"}})
        assert body["TaskId"] == "upstream-video"
        return httpx.Response(200, json=finish(version))
    with relay_client(tmp_path) as client:
        key_id, key, channel = setup(client, version, site)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "video-once"}
        body = request_body(version)
        created = client.post(TASKS, json=body, headers=headers)
        assert created.status_code == 200, created.text
        assert client.post(TASKS, json=body, headers=headers).json() == created.json()
        assert client.post(TASKS, json={**body, "duration": 5}, headers=headers).status_code == 409
        task_id = created.json()["id"]
        _, other_key = create_key(client, "vega_project", "other")
        assert client.get(TASKS + "/" + task_id, headers={"Authorization": "Bearer " + other_key}).status_code == 404
        relay.rotate_channel_secret(channel["id"], json.dumps({"secretId": "new-example-id", "secretKey": "new-example-key"}), "super")
        relay.set_channel_status(channel["id"], False)
        completed = client.get(TASKS + "/" + task_id, headers=headers)
        assert completed.status_code == 200, completed.text
        data = completed.json()
        assert data["status"] == "succeeded" and data["usage"]["completion_tokens"] == 1200
        assert data["usage"]["vega"]["OutputSeconds"] == 4
        assert data["content"]["last_frame_url"]
        assert client.get(TASKS + "/" + task_id, headers=headers).json() == data
        assert client.delete(TASKS + "/" + task_id, headers=headers).status_code == 422
        with client.app.state.database.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 1
            row = dict(c.execute("SELECT u.*,c.provider,t.metadata_json,t.billing_metadata_json FROM inference_usage u JOIN provider_channels c ON c.id=u.channel_id JOIN inference_tasks t ON t.id=u.task_id").fetchone())
            logs = str([tuple(r) for r in c.execute("SELECT request_params_json,response_summary_json FROM request_logs WHERE log_type='http'")])
            assert "OutputSeconds" in logs and "小船" in logs
            assert "example-key-12345678" not in logs and key not in logs
            cipher = c.execute("SELECT secret_ciphertext FROM provider_credentials LIMIT 1").fetchone()[0]
            assert "example-key" not in cipher
        assert BillingManager._relay_measurements(row)[0][0] == ("video_second", f"{site}:{'768p' if version == '1.0-lite' else '720p'}:no_video", Decimal(4))
    assert len(calls) == 2


def test_signature_matches_independent_tc3_calculation():
    url, headers, body = signed_request(SECRET, {"site": "domestic", "subAppId": "123456"}, "DescribeTaskDetail", {"TaskId": "task"}, 1551113065)
    assert url == "https://vod.tencentcloudapi.com/" and headers["X-TC-Version"] == "2018-07-17"
    request = "\n".join(["POST", "/", "", "content-type:application/json; charset=utf-8\nhost:vod.tencentcloudapi.com\nx-tc-action:describetaskdetail\n", "content-type;host;x-tc-action", hashlib.sha256(body).hexdigest()])
    key = b"TC3example-key-12345678"
    for part in ["2019-02-25", "vod", "tc3_request"]:
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    string = "TC3-HMAC-SHA256\n1551113065\n2019-02-25/vod/tc3_request\n" + hashlib.sha256(request.encode()).hexdigest()
    assert headers["Authorization"].endswith("Signature=" + hmac.new(key, string.encode(), hashlib.sha256).hexdigest())


@pytest.mark.parametrize("secret", ["api-key-not-a-pair", "{}", '{"secretId":"abcdefgh","secretKey":"x"}', '[]'])
def test_credentials_reject_incomplete_pairs(secret):
    with pytest.raises(ApiError):
        credentials(secret)


@pytest.mark.parametrize("config", [{}, {"site": "other", "subAppId": "1"}, {"subAppId": "0"}, {"subAppId": "1", "baseUrl": "https://evil.example"}])
def test_config_rejects_overrides(config):
    with pytest.raises(ApiError):
        channel_config(config)


@pytest.mark.parametrize("change", [{"duration": 3}, {"duration": float("inf")}, {"duration": True},
    {"resolution": "480p"}, {"seed": True}, {"frames": 25}, {"vega": {"generate_mode": "Fast"}},
    {"vega": {"task_type": "edit"}}, {"watermark": False}, {"generate_audio": "true"},
    {"content": [{"type": "audio_url", "audio_url": {"url": "https://example.com/a.mp3"}, "role": "reference_audio"}]}])
def test_payload_validation_before_upstream(change):
    row = VEGA_MODEL_CATALOG[1]
    route = SimpleNamespace(capabilities=row[6], upstream_model=row[5])
    base = {"duration": change.get("duration", 4), "metadata": {"content": request_body()["content"], **{k:v for k,v in change.items() if k not in {"duration", "seed"}}}}
    if "seed" in change:
        base["seed"] = change["seed"]
    with pytest.raises(ApiError):
        submit_payload(route, base)


def test_lite_tail_only_ext_double_json_and_prompt_limit():
    row = VEGA_MODEL_CATALOG[0]
    route = SimpleNamespace(capabilities=row[6], upstream_model=row[5])
    body = submit_payload(route, {"metadata": {"content": [{"type": "image_url", "role": "last_frame", "image_url": {"url": "https://example.com/last.jpg"}}], "vega": {"enhance_prompt": "disable", "generate_mode": "Fast", "video_quality_mode": "SuperFast"}}})
    assert body["FileInfos"][0]["Usage"] == "LastFrame"
    assert json.loads(json.loads(body["ExtInfo"])["WandVegaParameters"])["GenerateMode"] == "Fast"
    with pytest.raises(ApiError):
        submit_payload(route, {"prompt": "x" * 7001})
    with pytest.raises(ApiError):
        submit_payload(route, {"prompt": "hi", "duration": -1})


@pytest.mark.parametrize("version,has_video,usage,expected", [
    ("1.0-lite", True, {"OutputSeconds": 4, "InputSeconds": 2, "InputImageCount": 7}, Decimal(6)),
    ("1.0-pro", True, {"OutputSeconds": 6, "InputSeconds": 2}, Decimal(10)),
    ("1.5-pro", True, {"OutputSeconds": 6, "InputSeconds": 4}, Decimal(10)),
    ("1.0-pro-fast", False, {"OutputSeconds": 4}, Decimal(4)),
])
def test_measurements_real_usage_floor_image_surcharge(version, has_video, usage, expected):
    row = {"model_alias": "vega-" + version,
           "billing_metadata_json": json.dumps({"resolution": "1080p", "vegaSite": "domestic", "containsVideoInput": has_video}),
           "metadata_json": json.dumps({"usage": {"vega": usage}})}
    items, reason = measurements(row)
    assert reason is None and items[0][2] == expected
    if version == "1.0-lite":
        assert items[1] == ("image", "domestic:input:after_five", Decimal(2))
    for bad in ({}, {"OutputSeconds": 0}, {"OutputSeconds": -1}, {"OutputSeconds": "NaN"}):
        assert measurements({**row, "metadata_json": json.dumps({"usage": {"vega": bad}})})[0] is None


def test_migration_preserves_history_and_does_not_enable_projects(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as c:
        c.executescript(SCHEMA.replace(",'vega'", ""))
        c.execute("INSERT INTO projects(name,display_name) VALUES ('old','Old')")
        c.execute("INSERT INTO provider_channels(id,project_name,name,provider) VALUES ('old','old','Old','modeltop')")
    database = Database(path)
    database.initialize()
    database.initialize()
    with database.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM model_catalog WHERE provider='vega'").fetchone()[0] == 11
        assert c.execute("SELECT COUNT(*) FROM provider_channels").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM project_billing_terms").fetchone()[0] == 0
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert len(VEGA_RATES) == 5
    pro = dict(((m,d), p) for m,d,_,p in VEGA_RATES["vega-1.0-pro"])
    assert pro[("video_second", "domestic:720p:no_video")] == Decimal(".795")
    assert pro[("video_second", "international:720p:video")] == (Decimal(".0769") * VEGA_FX).quantize(Decimal(".000001"))


def test_public_pricing_only_current_site_and_no_automatic_probe(tmp_path):
    with relay_client(tmp_path) as client:
        _, key, channel = setup(client, site="international")
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda r: pytest.fail("must not send a cloud probe"))
        result = asyncio.run(client.app.state.provider_relay.test_channel(channel["id"]))
        assert result["status"] == "manual"
        data = client.get("/v1/pricing?model=vega-1.0-pro", headers={"Authorization": "Bearer " + key}).json()
        assert data["data"][0]["configured"]
        assert all(p["dimension"].startswith("international:") for p in data["data"][0]["prices"])


@pytest.mark.parametrize("reply,code", [({"Response": {"Error": {"Code": "AuthFailure", "Message": "denied"}}}, 502),
                                      ({"Response": {"Error": {"Code": "LimitExceeded.Concurrent", "Message": "busy"}}}, 429),
                                      ({}, 502), ({"Response": {}}, 502)])
def test_errors_and_missing_task_ids_do_not_create_billable_usage(tmp_path, reply, code):
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda r: httpx.Response(200, json=reply))
        response = client.post(TASKS, json=request_body(), headers={"Authorization": "Bearer " + key, "Idempotency-Key": "failure"})
        assert response.status_code == code, response.text
        with client.app.state.database.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0


def test_material_flow_owned_assets_liveness_and_no_route_overrides(tmp_path):
    calls = []
    def handler(request):
        action = request.headers["X-TC-Action"]
        body = json.loads(request.content)
        calls.append((action, body))
        if action == "CreateAigcMaterial":
            assert body["GroupId"].startswith("vg_") and body["IsRealPerson"] == "False"
            return httpx.Response(200, json={"Response": {"TaskId": "up-material", "RequestId": "r"}})
        if action == "DescribeTaskDetail":
            return httpx.Response(200, json={"Response": {"Status": "FINISH", "CreateAigcMaterialTask": {
                "Status": "FINISH", "ErrCode": 0, "Output": {"AssetId": "asset-owned", "GroupId": calls[0][1]["GroupId"]}}}})
        if action == "CreateAigcVideoTask":
            assert body["FileInfos"][0]["Url"] == "asset://asset-owned"
            return httpx.Response(200, json={"Response": {"TaskId": "video", "RequestId": "r"}})
        if action == "CreateAigcLivenessValidate":
            return httpx.Response(200, json={"Response": {"LivenessToken": "sensitive-liveness", "H5Link": "https://example.com/live?token=secret"}})
        return httpx.Response(200, json={"Response": {"RequestId": "r"}})
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "material"}
        body = {"model": "vega-1.0-pro", "FileInfo": {"Type": "Url", "Url": "https://example.com/person.png"}, "AssetType": "Image"}
        path = "/v1/vega/CreateAigcMaterial"
        created = client.post(path, json=body, headers=headers)
        assert created.status_code == 200, created.text
        assert client.post(path, json=body, headers=headers).json() == created.json()
        assert client.post(path, json={**body, "SubAppId": 999}, headers=headers).status_code == 422
        query = {"model": body["model"], "TaskId": created.json()["id"]}
        assert client.post("/v1/vega/DescribeTaskDetail", json=query, headers=headers).json()["Response"]["CreateAigcMaterialTask"]["Output"]["AssetId"] == "asset-owned"
        media = {"model": body["model"], "content": [{"type": "image_url", "image_url": {"url": "asset://asset-owned"}, "role": "reference_image"}]}
        assert client.post(TASKS, json=media, headers=headers).status_code == 200
        _, other = create_key(client, "vega_project", "second")
        assert client.post(TASKS, json=media, headers={"Authorization": "Bearer " + other}).status_code == 404
        assert client.post("/v1/vega/DescribeTaskDetail", json=query, headers={"Authorization": "Bearer " + other}).status_code == 404
        assert client.post("/v1/vega/DeleteAigcMaterial", json={"model": body["model"]}, headers=headers).status_code == 422
        live = client.post("/v1/vega/CreateAigcLivenessValidate", json={"model": body["model"]}, headers=headers)
        assert live.status_code == 200
        assert live.json()["Response"]["LivenessToken"] == "sensitive-liveness"
        assert client.get(TASKS + "/" + live.json()["id"], headers=headers).status_code == 404
        with client.app.state.database.connect() as c:
            assert "sensitive-liveness" not in str([tuple(r) for r in c.execute("SELECT * FROM vega_resources")])
            logs = str([tuple(r) for r in c.execute("SELECT response_summary_json FROM request_logs")])
            assert "sensitive-liveness" not in logs and "token=secret" not in logs
        assert client.post("/v1/vega/DeleteAigcMaterial", json={"model": body["model"], "AssetId": "asset-owned"}, headers=headers).status_code == 200
        assert client.post(TASKS, json=media, headers={**headers, "Idempotency-Key": "after-delete"}).status_code == 404


def test_failed_and_incomplete_results_not_success():
    assert video_result({"Status": "PROCESSING"})["status"] == "running"
    assert video_result(finish("1.0-pro", error=1)["Response"])["status"] == "failed"
    with pytest.raises(ApiError):
        video_result({"Status": "FINISH"})


@pytest.mark.parametrize("version,usage,list_yuan,net_yuan", [
    ("1.0-lite", {"OutputSeconds": 4, "InputSeconds": 2, "InputImageCount": 7}, "2.550000", "2.040000"),
    ("1.0-pro", {"OutputSeconds": 6, "InputSeconds": 2}, "5.000000", "4.000000"),
])
def test_actual_monthly_bill_decimal_discount_replay_and_unknown(tmp_path, version, usage, list_yuan, net_yuan):
    def handler(request):
        if request.headers["X-TC-Action"] == "CreateAigcVideoTask":
            return httpx.Response(200, json={"Response": {"TaskId": "up", "RequestId": "r"}})
        return httpx.Response(200, json=finish(version, usage=usage))
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client, version)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        with client.app.state.database.connect() as c:
            c.execute("INSERT INTO project_billing_terms(id,project_name,effective_month,enabled,discount_bps,updated_by) VALUES ('term','vega_project',?,1,8000,'test')", (current_month(),))
        body = {"model": "vega-" + version, "content": [
            {"type": "video_url", "video_url": {"url": "https://example.com/ref.mp4"}, "role": "reference_video"}]}
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "bill-once"}
        task = client.post(TASKS, json=body, headers=headers).json()["id"]
        assert client.get(TASKS + "/" + task, headers=headers).json()["status"] == "succeeded"
        billing = client.app.state.billing
        for _ in range(2):
            statement = asyncio.run(billing.preview("vega_project", current_month()))["statement"]
            assert statement["subtotalYuan"] == list_yuan and statement["totalYuan"] == net_yuan
            assert statement["pendingCount"] == 0
        with client.app.state.database.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM billing_usage_items").fetchone()[0] == 1
            c.execute("UPDATE inference_tasks SET metadata_json='{}' WHERE id=?", (task,))
        statement = asyncio.run(billing.preview("vega_project", current_month()))["statement"]
        assert statement["pendingCount"] == 1


@pytest.mark.parametrize("action,body,expected", [
    ("Anything", {}, 404), ("CreateAigcMaterial", {}, 422),
    ("CreateAigcMaterial", {"FileInfo": {"Type": "Url", "Url": "file:///local"}, "AssetType": "Image"}, 422),
    ("CreateAigcMaterial", {"FileInfo": {"Type": "Url", "Url": "https://example.com/a.png"}, "AssetType": "Other"}, 422),
    ("CreateAigcMaterial", {"FileInfo": {"Type": "Url", "Url": "https://example.com/a.png"}, "AssetType": "Image", "IsRealPerson": "True"}, 422),
    ("CreateAigcLivenessValidate", {"CallbackUrl": "https://example.com/callback"}, 422),
    ("DescribeAigcMaterial", {"AssetId": "someone-else"}, 404),
    ("DescribeAigcMaterial", {}, 422),
    ("DeleteAigcMaterial", {"AssetId": "a", "GroupId": "b"}, 422),
    ("CreateAigcMaterial", {"AssetName": 123}, 422),
])
def test_resource_invalid_requests_never_reach_cloud(tmp_path, action, body, expected):
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda r: pytest.fail("invalid request reached VOD"))
        response = client.post("/v1/vega/" + action, json={"model": "vega-1.0-pro", **body}, headers={"Authorization": "Bearer " + key, "Idempotency-Key": "bad"})
        assert response.status_code == expected, response.text


def test_resource_actions_liveness_success_group_management_and_pinned_material_query(tmp_path):
    from app.security import ApiPrincipal
    from app.vega_resources import VegaResources
    calls = []
    def handler(request):
        action = request.headers["X-TC-Action"]
        body = json.loads(request.content)
        calls.append((action, body))
        result = {"RequestId": "r"}
        if action == "CreateAigcLivenessValidate":
            result.update({"LivenessToken": "token-123", "H5Link": "https://example.com/h5"})
        elif action == "DescribeAigcLivenessValidateResult":
            assert "example-id-12345678" in request.headers["Authorization"]
            result.update({"GroupId": "group-real", "Status": "DONE"})
        elif action == "CreateAigcMaterial":
            assert body["IsRealPerson"] == "True" and body["GroupId"] == "group-real"
            result["TaskId"] = "mat"
        elif action == "DescribeTaskDetail":
            assert "example-id-12345678" in request.headers["Authorization"]
            result.update({"Status": "FINISH", "CreateAigcMaterialTask": {"Status": "FINISH", "ErrCode": 0,
                "Output": {"AssetId": "asset-real", "GroupId": "group-real"}}})
        return httpx.Response(200, json={"Response": result})
    with relay_client(tmp_path) as client:
        key_id, key, channel = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "live"}
        def call(action, **kwargs):
            return client.post("/v1/vega/" + action, json={"model": "vega-1.0-pro", **kwargs}, headers=headers)
        assert call("CreateAigcLivenessValidate").status_code == 200
        assert call("DescribeAigcLivenessValidateResult", LivenessToken="token-123").json()["Response"]["Status"] == "DONE"
        headers["Idempotency-Key"] = "material"
        material = call("CreateAigcMaterial", FileInfo={"Type": "Url", "Url": "https://example.com/person.jpg"}, AssetType="Image", GroupId="group-real", IsRealPerson="True")
        assert material.status_code == 200, material.text
        task = material.json()["id"]
        relay.rotate_channel_secret(channel["id"], json.dumps({"secretId": "new-example-id", "secretKey": "new-example-key"}), "test")
        assert call("DescribeTaskDetail", TaskId=task).status_code == 200
        for action, fields in [
            ("DescribeAigcMaterial", {"AssetId": "asset-real"}),
            ("ModifyAigcMaterial", {"AssetId": "asset-real", "AssetName": "renamed"}),
            ("ModifyAigcMaterialGroup", {"GroupId": "group-real", "GroupName": "renamed"}),
            ("DescribeAigcMaterialGroup", {"GroupId": "group-real"}),
            ("DescribeAigcMaterialList", {"GroupId": "group-real", "Limit": 10, "Offset": 0}),
        ]:
            assert call(action, **fields).status_code == 200, action
        assert call("DescribeAigcMaterialList", GroupId="group-real", Limit=10, Offset=1).status_code == 422
        assert call("ModifyAigcMaterial", AssetId="asset-real").status_code == 422
        assert call("DeleteAigcMaterial", GroupId="group-real").status_code == 200
        assert call("DescribeTaskDetail", TaskId=task).status_code == 200
        resources = VegaResources(relay)
        with pytest.raises(ApiError):
            resources.owns(ApiPrincipal(key_id, "vega_project"), relay.resolve(ApiPrincipal(key_id, "vega_project"), "vega-1.0-pro"), "AssetId", "asset-real")
        relay.set_channel_status(channel["id"], False)
        assert call("DescribeAigcLivenessValidateResult", LivenessToken="token-123").status_code == 200


@pytest.mark.parametrize("version,site,action", [("1.0-lite", "domestic", "DescribeAigcMaterial"),
    ("1.0-pro", "international", "CreateAigcLivenessValidate")])
def test_unsupported_resources_modes_do_not_reach_provider(tmp_path, version, site, action):
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client, version, site)
        client.app.state.provider_relay.transport = httpx.MockTransport(lambda r: pytest.fail("unsupported call"))
        response = client.post("/v1/vega/" + action, json={"model": "vega-" + version, **({"AssetId": "asset"} if version == "1.0-lite" else {})}, headers={"Authorization": "Bearer " + key, "Idempotency-Key": "mode"})
        assert response.status_code == 422


def test_resource_model_and_idempotency_validation(tmp_path):
    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        headers = {"Authorization": "Bearer " + key}
        assert client.post("/v1/vega/CreateAigcLivenessValidate", json={}, headers=headers).status_code == 422
        assert client.post("/v1/vega/CreateAigcLivenessValidate", json={"model": "vega-1.0-pro"}, headers={**headers, "Idempotency-Key": "x" * 129}).status_code == 422
        assert client.post("/v1/vega/CreateAigcLivenessValidate", json={"model": "vega-1.0-pro"}, headers=headers).status_code == 422


def test_resource_idempotency_hash_includes_model_alias(tmp_path):
    with relay_client(tmp_path) as client:
        _, key, channel = setup(client)
        relay = client.app.state.provider_relay
        relay.set_project_models("vega_project", [{"model": model, "channelId": channel["id"], "enabled": True}
                                                  for model in ("vega-1.0-pro", "vega-1.5-pro")], "test")
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"Response": {"LivenessToken": "one-token", "H5Link": "https://example.com/h5"}})
        relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "same-business-order"}
        first = client.post("/v1/vega/CreateAigcLivenessValidate", json={"model": "vega-1.0-pro"}, headers=headers)
        assert first.status_code == 200
        conflict = client.post("/v1/vega/CreateAigcLivenessValidate", json={"model": "vega-1.5-pro"}, headers=headers)
        assert conflict.status_code == 409
        assert len(calls) == 1
