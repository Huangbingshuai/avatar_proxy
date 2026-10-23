"""Image/VL contracts on one Vega channel, using mocked supplier HTTP only."""
import base64
import io
import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app import vega, vega_image, vega_vl
from app.billing import BillingManager
from app.errors import ApiError
from conftest import create_key, create_project
from test_provider_relay import relay_client

SECRET = {"secretId": "example-id-12345678", "secretKey": "example-key-12345678", "apiToken": "mock-vl-token-12345678"}
TASKS = "/v1/images/tasks"


def setup(client, site="domestic"):
    create_project(client, "vega_shared")
    key_id, key = create_key(client, "vega_shared", "shared-key")
    relay = client.app.state.provider_relay
    channel = relay.create_channel(project_name="vega_shared", name="Unified Vega", provider="vega",
        config={"site": site, "subAppId": "123456"}, secret=json.dumps(SECRET), actor_id="super")
    relay.set_project_models("vega_shared", [{"model": a, "channelId": channel["id"], "enabled": True}
        for a in [*vega_image.MODELS, *vega_vl.MODELS, "vega-1.0-pro"]], "admin")
    return key_id, {"Authorization": "Bearer " + key, "Idempotency-Key": "create-once"}, channel


def image_result(error=0, inputs=0):
    return {"Response": {"RequestId": "query-image", "Status": "FINISH", "AigcImageTask": {
        "Status": "FINISH", "ErrCode": error, "ErrCodeExt": "Blocked" if error else "", "Message": "blocked" if error else "",
        "Input": {"FileInfos": [{} for _ in range(inputs)]}, "Output": {"FileInfos": [{
            "FileUrl": "https://example.com/generated.png", "ExpireTime": "2026-12-01T00:00:00Z",
            "MetaData": {"Width": 1920, "Height": 1080}}]}}}}


@pytest.mark.parametrize("alias", list(vega_image.MODELS))
@pytest.mark.parametrize("site", ["domestic", "international"])
def test_async_images_pin_credentials_isolate_keys_and_settle_once(tmp_path, alias, site):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == vega.VEGA_HOSTS[site]
        assert "example-id-12345678" in request.headers["authorization"]
        body = json.loads(request.content)
        assert body["SubAppId"] == 123456
        if request.headers["x-tc-action"] == "CreateAigcImageTask":
            assert body["ModelName"] == "wand-vega-image"
            assert body["OutputConfig"]["StorageMode"] == "Temporary"
            assert body["OutputConfig"]["AspectRatio"] == "16:9"
            assert body["SessionId"].startswith("img_")
            return httpx.Response(200, json={"Response": {"TaskId": "supplier-image", "RequestId": "create-image"}})
        assert body["TaskId"] == "supplier-image"
        return httpx.Response(200, json=image_result())
    with relay_client(tmp_path) as client:
        _, headers, channel = setup(client, site)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        body = {"model": alias, "prompt": "a quiet lake", "size": "1920x1080"}
        first = client.post(TASKS, headers=headers, json=body)
        assert first.status_code == 200, first.text
        task_id = first.json()["id"]
        assert client.post(TASKS, headers=headers, json=body).json() == first.json()
        assert client.post(TASKS, headers=headers, json={**body, "prompt": "changed"}).status_code == 409
        _, other = create_key(client, "vega_shared", "other")
        hidden = client.get(TASKS + "/" + task_id, headers={"Authorization": "Bearer " + other})
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "image_task_not_found"
        missing = client.get(TASKS + "/img_missing", headers=headers)
        assert missing.status_code == 404
        assert missing.json()["error"]["message"] == "生图任务不存在"
        relay.rotate_channel_secret(channel["id"], json.dumps({"secretId": "new-secret-id", "secretKey": "new-secret-key"}), "super")
        relay.set_channel_status(channel["id"], False)
        relay.recover_interrupted_images()
        result = client.get(TASKS + "/" + task_id, headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "succeeded"
        assert result.json()["result"]["data"][0]["url"].startswith("https://example.com/")
        assert client.get(TASKS + "/" + task_id, headers=headers).json() == result.json()
        with relay.database.connect() as c:
            rows = c.execute("SELECT u.*,m.modality,c.provider,t.billing_metadata_json,t.metadata_json FROM inference_usage u JOIN model_catalog m ON m.alias=u.model_alias JOIN provider_channels c ON c.id=u.channel_id JOIN inference_tasks t ON t.id=u.task_id").fetchall()
        assert len(rows) == 1
        measures, reason = BillingManager._relay_measurements(dict(rows[0]))
        assert reason is None and measures[0] == ("image", site + ":output", Decimal(1))
    assert len(calls) == 2


def test_sync_generation_and_api_token_rotation_keep_same_channel(tmp_path):
    def handler(request):
        if request.headers.get("x-tc-action") == "CreateAigcImageTask":
            return httpx.Response(200, json={"Response": {"TaskId": "image-1"}})
        return httpx.Response(200, json=image_result())
    with relay_client(tmp_path) as client:
        _, headers, channel = setup(client)
        relay = client.app.state.provider_relay
        relay.rotate_channel_secret(channel["id"], json.dumps({"apiToken": "updated-vl-token"}), "super")
        with relay.database.connect() as c:
            encrypted = c.execute("SELECT secret_ciphertext FROM provider_credentials WHERE channel_id=? AND status='active'", (channel["id"],)).fetchone()[0]
        assert json.loads(relay.vault.decrypt(encrypted)) == {**SECRET, "apiToken": "updated-vl-token"}
        assert "updated-vl-token" not in json.dumps(relay.get_channel(channel["id"]))
        relay.transport = httpx.MockTransport(handler)
        result = client.post("/v1/images/generations", headers=headers, json={"model": "vega-image-1.0-lite", "prompt": "lake"})
        assert result.status_code == 200, result.text
        assert len(result.json()["data"]) == 1
        assert client.post(TASKS, headers={"Authorization": headers["Authorization"]}, json={"model": "vega-image-1.0-lite", "prompt": "lake"}).status_code == 422


@pytest.mark.parametrize("tier,maximum", [("lite", 1), ("flash", 4), ("pro", 4)])
@pytest.mark.parametrize("path", [TASKS, "/v1/images/generations"])
def test_image_count_matches_supplier_limit_before_submission(tmp_path, tier, maximum, path):
    calls = []
    alias = "vega-image-1.0-" + tier

    def handler(request):
        calls.append(request)
        if request.headers["x-tc-action"] == "CreateAigcImageTask":
            output = json.loads(request.content)["OutputConfig"]
            assert output.get("OutputImageCount", 1) == maximum
            return httpx.Response(200, json={"Response": {"TaskId": "image-at-limit"}})
        result = image_result()
        result["Response"]["AigcImageTask"]["Output"]["FileInfos"] *= maximum
        return httpx.Response(200, json=result)

    with relay_client(tmp_path) as client:
        _, headers, _ = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        catalog = next(item for item in client.get("/v1/models", headers=headers).json()["data"] if item["id"] == alias)
        assert catalog["capabilities"]["maxN"] == maximum
        body = {"model": alias, "prompt": "product photography", "n": maximum + 1}
        rejected = client.post(path, headers=headers, json=body)
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "image_count_unsupported"
        assert not calls
        with relay.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_tasks").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0
        accepted = client.post(path, headers=headers, json={**body, "n": maximum})
        assert accepted.status_code == 200, accepted.text
        if path == TASKS:
            accepted = client.get(TASKS + "/" + accepted.json()["id"], headers=headers)
            images = accepted.json()["result"]["data"]
        else:
            images = accepted.json()["data"]
        assert len(images) == maximum
        with relay.database.connect() as connection:
            assert connection.execute("SELECT generated_images FROM inference_usage WHERE status='succeeded'").fetchone()[0] == maximum


@pytest.mark.parametrize("tier", ["lite", "flash", "pro"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("site", ["domestic", "international"])
def test_vl_media_stream_and_cache_usage_share_vega_channel(tmp_path, tier, stream, site):
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
             "prompt_tokens_details": {"cached_tokens": 0, "cache_read_tokens": 30, "video_tokens": 60},
             "completion_tokens_details": {"reasoning_tokens": 12}}
    def handler(request):
        assert request.url == "https://mmu.vod-qcloud.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + SECRET["apiToken"]
        assert len(request.headers["tx-user-session-id"]) == 64
        body = json.loads(request.content)
        assert body["thinking_enabled"] is True
        data = {"id": "vl-response", "model": body["model"], "choices": [{"message": {"role": "assistant", "content": "a lake"}}], "usage": usage}
        if stream:
            return httpx.Response(200, headers={"Content-Type": "text/event-stream", "X-Request-Id": "vl-upstream"},
                                  content=("data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n").encode())
        return httpx.Response(200, headers={"X-Request-Id": "vl-upstream"}, json=data)
    with relay_client(tmp_path) as client:
        _, headers, _ = setup(client, site)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        body = {"model": "wand-vega-vl-1.0-" + tier, "stream": stream, "thinking_enabled": True, "reasoning_split": True,
                "messages": [{"role": "user", "content": [{"type": "text", "text": "describe"}, {"type": "video_url", "video_url": {"url": "https://example.com/video.mp4"}}]}]}
        response = client.post("/v1/chat/completions", headers={**headers, "Tx-User-Session-Id": "customer-session"}, json=body)
        assert response.status_code == 200, response.text
        assert all(s in response.text for s in ("a lake", "video_tokens", "reasoning_tokens"))
        with relay.database.connect() as c:
            rows = c.execute("SELECT u.*,m.modality,c.provider FROM inference_usage u JOIN model_catalog m ON m.alias=u.model_alias JOIN provider_channels c ON c.id=u.channel_id").fetchall()
        assert len(rows) == 1 and rows[0]["cached_input_tokens"] == 30
        measures, reason = BillingManager._relay_measurements(dict(rows[0]))
        assert reason is None and measures == [("input_tokens", site, Decimal(70)), ("output_tokens", site, Decimal(20)), ("cached_input_tokens", site, Decimal(30))]
        price = next(p for p in client.get("/v1/pricing", headers=headers).json()["data"] if p["id"] == body["model"])
        assert all(rule["dimension"] == site for rule in price["prices"])


def test_vl_invalid_media_and_missing_token_do_not_call_supplier(tmp_path):
    with relay_client(tmp_path) as client:
        _, headers, channel = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda r: pytest.fail("Invalid request reached supplier"))
        body = {"model": "wand-vega-vl-1.0-pro", "messages": [{"role": "user", "content": "pure text"}]}
        assert client.post("/v1/chat/completions", headers=headers, json=body).status_code == 422
        assert client.post("/v1/chat/completions", headers=headers, json={**body, "stream": True}).status_code == 422
        assert client.post("/v1/responses", headers=headers, json={"model": body["model"], "input": "hello"}).status_code == 422
        for part in ({"type": "file", "file_url": "https://example.com/a.pdf"},
                     {"type": "file", "file": {"file_url": "asset://other-project"}},
                     {"type": "input_audio", "input_audio": {"data": "!!!", "format": "wav"}}):
            assert client.post("/v1/chat/completions", headers=headers, json={**body, "messages": [{"role": "user", "content": [part]}]}).status_code == 422
        with relay.database.connect() as c:
            c.execute("UPDATE provider_credentials SET secret_ciphertext=? WHERE channel_id=? AND status='active'", (relay.vault.encrypt(json.dumps({k: SECRET[k] for k in ("secretId", "secretKey")})), channel["id"]))
        assert client.post("/v1/chat/completions", headers=headers, json={"model": "wand-vega-vl-1.0-lite", "messages": [{"role": "user", "content": "hello"}]}).status_code == 503


def test_image_real_format_and_missing_chargeable_usage():
    raw = io.BytesIO()
    Image.new("RGB", (2, 2)).save(raw, format="PNG")
    data = "data:image/png;base64," + base64.b64encode(raw.getvalue()).decode()
    route = SimpleNamespace(alias="vega-image-1.0-pro", upstream_model="1.0-pro", channel_config={"site": "domestic"}, capabilities=vega_image.MODELS["vega-image-1.0-pro"][6])
    result = vega_image.submit_payload(route, {"model": route.alias, "image": [data], "n": 2, "size": "4K", "aspect_ratio": "9:16"})
    assert result["FileInfos"][0]["Type"] == "Base64" and not result["FileInfos"][0]["Base64"].startswith("data:")
    assert result["OutputConfig"]["OutputImageCount"] == 2
    for payload in ({"prompt": "x" * 2001}, {"prompt": "x", "n": True}, {"prompt": "x", "image": ["data:image/png;base64,YmFk"]},
                    {"prompt": "x", "size": "512x512"}, {"prompt": "x", "response_format": "b64_json"}):
        with pytest.raises(ApiError):
            vega_image.submit_payload(route, payload)
    row = {"model_alias": route.alias, "generated_images": 2, "billing_metadata_json": json.dumps({"vegaSite": "domestic", "inputImageCount": 5}), "metadata_json": json.dumps({"vegaInputImageCount": 5})}
    assert vega_image.measurements(row)[0][-1] == ("image", "domestic:input:after_three", Decimal(2))
    row["metadata_json"] = "{}"
    assert vega_image.measurements(row) == (None, "usage_unknown")
    assert vega_vl.session_header(SimpleNamespace(id="a", project_name="p"), "same") != vega_vl.session_header(SimpleNamespace(id="b", project_name="p"), "same")


def test_missing_task_id_is_ambiguous_and_not_free_success(tmp_path):
    with relay_client(tmp_path) as client:
        _, headers, _ = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"Response": {"RequestId": "missing-id"}}))
        body = {"model": "vega-image-1.0-pro", "prompt": "lake"}
        assert client.post(TASKS, headers=headers, json=body).status_code == 502
        with relay.database.connect() as c:
            assert c.execute("SELECT status FROM inference_usage").fetchone()[0] == "unknown"
        assert client.post(TASKS, headers=headers, json=body).json()["status"] == "failed"
    assert vega_image.task_result(image_result(error=1)["Response"])["status"] == "failed"
    with pytest.raises(ApiError):
        vega_image.task_result({"AigcImageTask": {"Status": "FINISH", "ErrCode": 0, "Output": {"FileInfos": []}}})


@pytest.mark.parametrize("kind", ["incomplete", "malformed", "error_event", "http_error"])
def test_vl_stream_errors_remain_unsettled_and_redact_credentials(tmp_path, kind):
    usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
             "prompt_tokens_details": {"cached_tokens": 0}}
    first = "data:" + json.dumps({"id": "vl-err", "usage": usage}) + "\n\n"
    tail = {"incomplete": "", "malformed": "data:bad-json\n\n",
            "error_event": "data:" + json.dumps({"error": {"message": SECRET["apiToken"]}}) + "\n\ndata:[DONE]\n\n"}
    def handler(request):
        if kind == "http_error":
            return httpx.Response(401, json={"error": {"message": "Invalid " + SECRET["apiToken"]}})
        return httpx.Response(200, text=first + tail[kind], headers={"Content-Type": "text/event-stream"})
    with relay_client(tmp_path) as client:
        _, headers, _ = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        response = client.post("/v1/chat/completions", headers=headers, json={"model": "wand-vega-vl-1.0-lite", "stream": True,
            "messages": [{"role": "user", "content": "hello"}]})
        assert response.status_code == 200 and "error" in response.text
        assert SECRET["apiToken"] not in response.text
        with relay.database.connect() as c:
            assert c.execute("SELECT status FROM inference_usage").fetchone()[0] == "unknown"


def test_vl_http_error_and_invalid_stream_options(tmp_path):
    body = {"model": "wand-vega-vl-1.0-lite", "messages": [{"role": "user", "content": "hello"}]}
    with relay_client(tmp_path) as client:
        _, headers, _ = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "Invalid " + SECRET["apiToken"]}}))
        response = client.post("/v1/chat/completions", headers=headers, json=body)
        assert response.status_code == 401 and SECRET["apiToken"] not in response.text
        relay.transport = httpx.MockTransport(lambda r: pytest.fail("Invalid configuration reached supplier"))
        for option in (True, {"include_usage": 1}, {"extra": True}):
            assert client.post("/v1/chat/completions", headers=headers, json={**body, "stream": True, "stream_options": option}).status_code == 422


def test_one_channel_does_not_mix_resource_or_credential_types(tmp_path):
    with relay_client(tmp_path) as client:
        _, headers, channel = setup(client, "international")
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(lambda r: pytest.fail("Unsupported operation reached supplier"))
        for alias in ("vega-image-1.0-pro", "wand-vega-vl-1.0-pro"):
            result = client.post("/v1/vega/CreateAigcMaterial", headers=headers,
                json={"model": alias, "FileInfo": {"Type": "Image", "Url": "https://example.com/a.jpg"}})
            assert result.status_code == 422 and "vega_resource_unsupported" in result.text
        rates = client.get("/v1/pricing?model=vega-image-1.0-pro", headers=headers).json()["data"]
        assert len(rates) == 1 and not rates[0]["configured"] and rates[0]["prices"] == []
        with relay.database.connect() as c:
            c.execute("UPDATE provider_credentials SET secret_ciphertext=? WHERE channel_id=? AND status='active'",
                      (relay.vault.encrypt(json.dumps({"apiToken": SECRET["apiToken"]})), channel["id"]))
        assert client.post(TASKS, headers=headers, json={"model": "vega-image-1.0-lite", "prompt": "lake"}).status_code == 503


@pytest.mark.parametrize("part", [
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj", "detail": "high"}},
    {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,YWJj"}},
    {"type": "input_audio", "input_audio": {"url": "https://example.com/a.mp3"}},
    {"type": "input_audio", "input_audio": {"data": "YWJj", "format": "wav"}},
    {"type": "file", "file": {"file_url": "https://example.com/a.pdf"}},
    {"type": "file", "file": {"file_data": "data:application/pdf;base64,YWJj", "file_name": "a.pdf"}},
])
def test_vl_all_media_shapes_pass_without_rewriting_customer_parts(part):
    payload = {"model": "wand-vega-vl-1.0-pro", "messages": [{"role": "user", "content": [part]}]}
    assert vega_vl.validate_payload(payload, pro=True) == payload


@pytest.mark.parametrize("part", [
    {"type": "input_audio", "input_audio": {"data": 1234, "format": "wav"}},
    {"type": "input_audio", "input_audio": {"url": "data:image/png;base64,YWJj"}},
    {"type": "file", "file": {"file_url": "data:application/pdf;base64,YWJj"}},
    {"type": "image_url", "image_url": {"url": "https://example.com/a.png", "detail": "invalid"}},
])
def test_vl_media_types_remain_strict(part):
    with pytest.raises(ApiError):
        vega_vl.validate_payload({"messages": [{"role": "user", "content": [part]}]}, pro=True)
