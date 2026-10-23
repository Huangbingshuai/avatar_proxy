"""Offline customer-facing Draft acceptance; all supplier traffic is mocked."""
import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from app import seedance_draft
from app.billing import BillingManager
from app.database import BUILTIN_MODEL_CATALOG
from app.errors import ApiError
from app.provider_relay import ProviderRelay
from conftest import create_key
from test_provider_relay import provision, relay_client

PATH = "/api/v3/contents/generations/tasks"
MODEL = seedance_draft.MODEL
CATALOG = next(row for row in BUILTIN_MODEL_CATALOG if row[0] == MODEL)


def route():
    return SimpleNamespace(alias=MODEL, provider="volcengine_ark", capabilities=CATALOG[6],
                           upstream_model=CATALOG[5], channel_id="channel-original")


def final_payload(parent="vid_example"):
    return {"model": MODEL, "content": [{"type": "draft_task", "draft_task": {"id": parent}}], "resolution": "1080p"}


@pytest.fixture
def harness(tmp_path):
    with relay_client(tmp_path) as client:
        key_id, secret, channel = provision(client, provider="volcengine_ark", alias=MODEL, upstream_model=CATALOG[5])
        h = SimpleNamespace(client=client, key_id=key_id, channel=channel, relay=client.app.state.provider_relay,
                            headers={"Authorization": "Bearer " + secret}, submitted={}, calls=[], fail_final=False)

        def handler(request):
            h.calls.append((request.method, request.url.path))
            if request.method == "POST":
                body = json.loads(request.content)
                upstream_id = "provider-task-" + str(len(h.submitted) + 1)
                h.submitted[upstream_id] = {"body": body, "authorization": request.headers.get("authorization")}
                if h.fail_final and body["content"][0]["type"] == "draft_task":
                    return httpx.Response(503, json={"error": {"message": "mock supplier failure"}})
                return httpx.Response(200, json={"id": upstream_id})
            assert request.method == "GET"
            upstream_id = request.url.path.rsplit("/", 1)[1]
            submitted = h.submitted[upstream_id]["body"]
            is_draft = submitted.get("draft") is True
            body = {"id": upstream_id, "status": "succeeded", "draft": is_draft,
                    "resolution": submitted["resolution"], "duration": 4, "ratio": "16:9",
                    "content": {"video_url": "https://provider.example.com/result.mp4"},
                    "usage": {"completion_tokens": 10000 if is_draft else 50000}}
            if submitted["content"][0]["type"] == "draft_task":
                body["draft_task_id"] = submitted["content"][0]["draft_task"]["id"]
            return httpx.Response(200, json=body)

        h.relay.transport = httpx.MockTransport(handler)
        yield h


def create(h, body, key="draft-create", headers=None):
    return h.client.post(PATH, headers={**(headers or h.headers), "Idempotency-Key": key}, json=body)


def make_draft(h, *, video=False, finish=True):
    content = [{"type": "text", "text": "A paper boat crosses a pond"}]
    if video:
        content.append({"type": "video_url", "video_url": {"url": "https://example.com/reference.mp4"}, "role": "reference_video"})
    response = create(h, {"model": MODEL, "draft": True, "resolution": "480p", "duration": 4, "content": content})
    assert response.status_code == 200, response.text
    task_id = response.json()["id"]
    if finish:
        result = h.client.get(PATH + "/" + task_id, headers=h.headers)
        assert result.status_code == 200 and result.json()["status"] == "succeeded", result.text
    return task_id


@pytest.mark.parametrize("has_video", [False, True])
def test_draft_to_final_customer_flow_persists_billing_and_logs(harness, has_video):
    h = harness
    parent = make_draft(h, video=has_video)
    draft = h.client.get(PATH + "/" + parent, headers=h.headers).json()
    assert draft["draft"] is True
    assert draft["draft_expires_at"] == draft["created_at"] + seedance_draft.TTL_SECONDS
    payload = final_payload(parent)
    payload.update(watermark=True, return_last_frame=True, output_format="mov", draft=False)
    response = create(h, payload, "final-create")
    assert response.status_code == 200, response.text
    child = response.json()["id"]
    assert child != parent
    final = h.client.get(PATH + "/" + child, headers=h.headers).json()
    assert final["status"] == "succeeded" and final["draft"] is False
    assert final["draft_task_id"] == parent and final["resolution"] == "1080p"
    assert "provider-task-" not in json.dumps(final)
    forwarded = h.submitted["provider-task-2"]["body"]
    assert forwarded == {"model": CATALOG[5], "content": [{"type": "draft_task", "draft_task": {"id": "provider-task-1"}}],
                         "resolution": "1080p", "draft": False, "watermark": True, "return_last_frame": True, "output_format": "mov"}
    for _ in range(2):
        assert create(h, payload, "final-create").json()["id"] == child
        assert h.client.get(PATH + "/" + child, headers=h.headers).status_code == 200
    assert len(h.submitted) == 2
    with h.client.app.state.database.connect() as c:
        usages = [dict(row) for row in c.execute(
            "SELECT u.*,t.metadata_json,t.billing_metadata_json FROM inference_usage u JOIN inference_tasks t ON t.id=u.task_id ORDER BY u.rowid")]
        assert len(usages) == 2
        for usage in usages:
            billing = json.loads(usage["billing_metadata_json"])
            assert billing["containsVideoInput"] is has_video
            usage.update(provider="volcengine_ark", modality="video")
            measurements, reason = BillingManager._relay_measurements(usage)
            assert reason is None
            resolution = "480p" if usage["task_id"] == parent else "1080p"
            assert measurements[0][1] == resolution + (":video" if has_video else ":no_video")
            assert int(measurements[0][2]) == (10000 if resolution == "480p" else 50000)
        body = c.execute("SELECT request_params_json FROM request_logs WHERE api_key_id=? AND method='POST' ORDER BY id DESC LIMIT 1", (h.key_id,)).fetchone()[0]
        assert parent in body and 'draft_task' in body
        assert 'provider-task-' not in body


def test_draft_idempotency_survives_restart_expiration_and_rotation(harness, monkeypatch):
    h = harness
    parent = make_draft(h)
    h.relay.rotate_channel_secret(h.channel["id"], "mock-rotated-credential-abcdefgh", "admin")
    payload = final_payload(parent)
    child = create(h, payload, "upgrade-once").json()["id"]
    assert h.submitted["provider-task-1"]["authorization"] == h.submitted["provider-task-2"]["authorization"]
    db = h.client.app.state.database
    with db.connect() as c:
        created_at = c.execute("SELECT created_at FROM inference_tasks WHERE id=?", (parent,)).fetchone()[0]
        old_version, new_version = c.execute("SELECT credential_id FROM inference_tasks ORDER BY rowid").fetchall()
        assert old_version[0] == new_version[0]
    db.initialize()
    db.initialize()
    replacement = ProviderRelay(h.relay.settings, db)
    replacement.transport = h.relay.transport
    h.client.app.state.provider_relay = replacement
    monkeypatch.setattr("app.provider_relay._now_epoch", lambda: created_at + seedance_draft.TTL_SECONDS)
    replay = create(h, payload, "upgrade-once")
    assert replay.status_code == 200 and replay.json()["id"] == child
    expired = create(h, payload, "upgrade-new")
    assert expired.status_code == 410 and expired.json()["error"]["code"] == "video_draft_expired"
    assert len(h.submitted) == 2
    conflict = create(h, {**payload, "watermark": True}, "upgrade-once")
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_key_conflict"


@pytest.mark.parametrize("other_project", [False, True])
def test_draft_cannot_reference_another_key_or_project(harness, other_project):
    h = harness
    parent = make_draft(h)
    if other_project:
        _, secret, _ = provision(h.client, provider="volcengine_ark", alias=MODEL,
                                 upstream_model=CATALOG[5], project_name="other_project")
    else:
        _, secret = create_key(h.client, "relay_project", "other-key")
    response = create(h, final_payload(parent), "cross-owner", {"Authorization": "Bearer " + secret})
    assert response.status_code == 404 and response.json()["error"]["code"] == "video_draft_not_found"
    assert len(h.submitted) == 1


def test_unfinished_source_and_disabled_or_changed_channel_do_not_submit(harness):
    h = harness
    parent = make_draft(h, finish=False)
    response = create(h, final_payload(parent), "unfinished")
    assert response.status_code == 409 and response.json()["error"]["code"] == "video_draft_not_ready"
    h.client.get(PATH + "/" + parent, headers=h.headers)
    other = h.relay.create_channel(project_name="relay_project", name="other-channel", provider="volcengine_ark",
                                   secret="mock-other-account-abcdefgh", config={}, actor_id="admin")
    h.relay.set_project_models("relay_project", [{"model": MODEL, "channelId": other["id"]}], "admin")
    changed = create(h, final_payload(parent), "changed-channel")
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "video_draft_route_changed"
    with h.client.app.state.database.connect() as c:
        c.execute("UPDATE provider_channels SET status='disabled' WHERE id=?", (other["id"],))
    assert create(h, final_payload(parent), "disabled").status_code == 403
    assert len(h.submitted) == 1


def test_unknown_missing_and_failed_supplier_tasks_are_not_promoted(harness):
    h = harness
    missing = create(h, final_payload("vid_missing"), "missing")
    assert missing.status_code == 404
    parent = make_draft(h)
    h.fail_final = True
    failed = create(h, final_payload(parent), "supplier-failure")
    assert failed.status_code >= 500
    assert len(h.submitted) == 2
    replay = create(h, final_payload(parent), "supplier-failure")
    assert replay.status_code == 200
    child = replay.json()["id"]
    assert h.client.get(PATH + "/" + child, headers=h.headers).json()["status"] == "failed"
    assert len(h.submitted) == 2
    with h.client.app.state.database.connect() as c:
        assert c.execute("SELECT count(*) FROM inference_usage").fetchone()[0] == 1


def test_public_capabilities_and_invalid_requests_never_create_supplier_tasks(harness):
    h = harness
    models = h.client.get("/v1/models", headers=h.headers).json()["data"]
    capabilities = next(item["capabilities"] for item in models if item["id"] == MODEL)
    assert capabilities["draft"] and capabilities["draftToFinal"]
    assert capabilities["draftTaskTtlSeconds"] == seedance_draft.TTL_SECONDS
    invalid = [
        {"model":MODEL,"content":[{"type":"text","text":"a boat"}],"draft":True,"resolution":"720p"},
        {"model":MODEL,"content":[{"type":"text","text":"a boat"}],"draft":"true","resolution":"480p"},
        {**final_payload(),"duration":4},
        {**final_payload(),"draft":True},
        {**final_payload(),"content":["bad",*final_payload()["content"]]},
        {**final_payload(),"content":[{"type":"draft_task","draft_task":{"id":"provider-task-1"}}]},
    ]
    for index, payload in enumerate(invalid):
        response = create(h, payload, "invalid-" + str(index))
        assert response.status_code == 422, response.text
    assert h.submitted == {}
    with h.client.app.state.database.connect() as c:
        assert c.execute("SELECT count(*) FROM inference_tasks").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM inference_usage").fetchone()[0] == 0


def test_source_supplier_confirmation_is_required_at_api_boundary(harness):
    h = harness
    parent = make_draft(h)
    with h.client.app.state.database.connect() as c:
        c.execute("UPDATE inference_tasks SET metadata_json=? WHERE id=?", (json.dumps({"resolution":"480p"}), parent))
    response = create(h, final_payload(parent), "unverified")
    assert response.status_code == 409 and response.json()["error"]["code"] == "video_draft_unverified"
    assert len(h.submitted) == 1


@pytest.mark.parametrize("patch", [
    {"draft": True}, {"resolution": "720p"}, {"resolution": None}, {"duration": 4}, {"duration": None},
    {"seed": 3}, {"ratio": "16:9"}, {"generate_audio": False}, {"frames": 129}, {"camera_fixed": False}, {"task_type": "t2v"},
])
def test_final_rejects_repeated_inherited_parameters(patch):
    payload = final_payload()
    payload.update(patch)
    metadata = {k:v for k,v in payload.items() if k not in {"model", "duration", "seed"}}
    normalized = {"metadata": metadata, **{k:v for k,v in payload.items() if k in {"duration", "seed"}}}
    with pytest.raises(ApiError) as caught:
        seedance_draft.validate(route(), normalized)
    assert caught.value.status_code == 422


@pytest.mark.parametrize("resolution", [None, "720p", "1080p", "480P"])
def test_draft_requires_explicit_480p(resolution):
    with pytest.raises(ApiError, match="480p"):
        seedance_draft.validate(route(), {"metadata": {"draft": True, "resolution": resolution}})


@pytest.mark.parametrize("draft", [None, "true", 1, [], {}])
def test_draft_flag_is_a_real_boolean(draft):
    with pytest.raises(ApiError) as caught:
        seedance_draft.validate(route(), {"metadata": {"draft": draft, "resolution": "480p"}})
    assert caught.value.code == "video_draft_invalid"


@pytest.mark.parametrize("content", [
    [{"type":"draft_task"}], [{"type":"draft_task", "draft_task":None}],
    [{"type":"draft_task", "draft_task":{}}], [{"type":"draft_task", "draft_task":{"id":True}}],
    [{"type":"draft_task", "draft_task":{"id":"provider-task-1"}}],
    [{"type":"draft_task", "draft_task":{"id":"vid_"}}],
    [{"type":"draft_task", "draft_task":{"id":"vid_" + "x" * 129}}],
    [{"type":"draft_task", "draft_task":{"id":"vid_example", "url":"https://example.com"}}],
    [{"type":"draft_task", "draft_task":{"id":"vid_example"}, "role":"reference_video"}],
    ["invalid", {"type":"draft_task", "draft_task":{"id":"vid_example"}}],
    [{"type":"text","text":"extra"}, {"type":"draft_task", "draft_task":{"id":"vid_example"}}],
])
def test_reference_shape_is_strict(content):
    with pytest.raises(ApiError) as caught:
        seedance_draft.reference_id(route(), content)
    assert caught.value.code == "video_draft_reference_invalid"


def source():
    return {"id":"vid_source", "operation":"video", "model_alias":MODEL, "status":"succeeded",
            "upstream_task_id":"provider-task-1", "channel_id":"channel-original", "upstream_model":CATALOG[5],
            "created_at":1800000000, "metadata_json":json.dumps({"draft":True,"resolution":"480p"}),
            "billing_metadata_json":json.dumps({"draft":True,"containsVideoInput":True})}


@pytest.mark.parametrize(("field","value","code"), [
    ("operation","image","video_draft_source_invalid"), ("model_alias","another-model","video_draft_source_invalid"),
    ("billing_metadata_json", "{}", "video_draft_source_invalid"),
    ("billing_metadata_json", "null", "video_draft_source_invalid"),
    ("billing_metadata_json", "malformed", "video_draft_source_invalid"),
    ("billing_metadata_json", [], "video_draft_source_invalid"),
    ("status","failed","video_draft_not_ready"), ("status","canceled","video_draft_not_ready"),
    ("upstream_task_id",None,"video_draft_not_ready"), ("metadata_json","{}","video_draft_unverified"),
    ("metadata_json",json.dumps({"draft":False,"resolution":"480p"}),"video_draft_unverified"),
    ("metadata_json",json.dumps({"draft":True,"resolution":"720p"}),"video_draft_unverified"),
    ("created_at",0,"video_draft_source_invalid"), ("created_at",True,"video_draft_source_invalid"),
    ("created_at",1900000000,"video_draft_source_invalid"), ("channel_id","other","video_draft_route_changed"),
    ("upstream_model","other","video_draft_route_changed"),
    ("billing_metadata_json",json.dumps({"draft":True}),"video_draft_usage_unknown"),
])
def test_source_guards(field,value,code):
    task = source()
    task[field] = copy.deepcopy(value)
    with pytest.raises(ApiError) as caught:
        seedance_draft.source_context(task, route(), 1800000001)
    assert caught.value.code == code


def test_exact_seven_day_boundary_and_public_metadata():
    task = source()
    expiry = task["created_at"] + seedance_draft.TTL_SECONDS
    assert seedance_draft.source_context(task, route(), expiry-1)["containsVideoInput"] is True
    with pytest.raises(ApiError) as caught:
        seedance_draft.source_context(task, route(), expiry)
    assert caught.value.status_code == 410
    assert seedance_draft.public_metadata(task,{"draft":"invalid"}) == {"draft":True,"draft_expires_at":expiry}
    task["billing_metadata_json"] = json.dumps({"draft":False,"draftTaskId":"vid_parent"})
    assert seedance_draft.public_metadata(task,{}) == {"draft":False,"draft_task_id":"vid_parent"}


@pytest.mark.parametrize("provider", ["byteplus_modelark","modeltop","vega"])
def test_other_providers_do_not_gain_draft_support(provider):
    other = route()
    other.provider = provider
    assert not seedance_draft.supported(other)
    with pytest.raises(ApiError) as caught:
        seedance_draft.reference_id(other, final_payload()["content"])
    assert caught.value.code == "video_draft_unsupported"


def test_unrelated_content_is_not_draft():
    assert seedance_draft.reference_id(route(), None) is None
    assert seedance_draft.reference_id(route(), [{"type":"text","text":"normal"}]) is None
