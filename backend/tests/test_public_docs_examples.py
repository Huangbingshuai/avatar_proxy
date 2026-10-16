"""Replay customer HTML examples through real routes with fake providers only."""
import base64
import html
import json
import re
import shlex
import subprocess
from pathlib import Path

import httpx
import pytest

from app.database import BUILTIN_DISABLED_MODEL_ALIASES, BUILTIN_MODEL_CATALOG
from app.modeltop import MODELTOP_MODELS
from conftest import HEIF
from test_provider_relay import provision, relay_client
from test_storage_deep import SuccessfulTosClient, media_samples  # noqa: F401


DOCUMENT = Path(__file__).resolve().parents[1] / "CLIENT_API.html"
TASKS = "/api/v3/contents/generations/tasks"


def articles():
    return dict(re.findall(r'<article[^>]*id="([^"]+)"[^>]*>(.*?)</article>', DOCUMENT.read_text(encoding="utf-8"), re.S))


def requests(article):
    blocks = re.findall(r'<pre([^>]*)><code>(.*?)</code></pre>', article, re.S)
    for attrs, block in blocks:
        if 'data-language=' in attrs and 'data-language="shell"' not in attrs:
            continue
        for command in re.split(r"(?m)^curl ", "\n" + html.unescape(block))[1:]:
            args = shlex.split("curl " + command.replace("\\\n", ""))
            url = next(arg for arg in args if arg.startswith("$BASE_URL"))
            payload = json.loads(args[args.index("-d") + 1]) if "-d" in args else None
            method = args[args.index("-X") + 1] if "-X" in args else "POST" if payload or "-F" in args else "GET"
            yield method, url.removeprefix("$BASE_URL"), payload, args


CASES = [(row[0], provider) for row in BUILTIN_MODEL_CATALOG if row[0] not in BUILTIN_DISABLED_MODEL_ALIASES
         for provider in dict.fromkeys([row[2]] + (["modeltop"] if row[0] in MODELTOP_MODELS else []))]


def mock_provider(provider, calls):
    def handle(request):
        calls.append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path.endswith("/tts/unidirectional/sse"):
            audio = base64.b64encode(b"mock-mp3").decode()
            return httpx.Response(200, text=f'data: {{"code":0,"data":"{audio}"}}\n\n')
        if path.endswith("/bigmodel/submit"):
            return httpx.Response(200, json={}, headers={"x-api-status-code": "20000000"})
        if path.endswith("/bigmodel/query"):
            return httpx.Response(200, json={"audio_info": {"duration": 2500}, "result": {"text": "hello"}}, headers={"x-api-status-code": "20000000"})
        if path.endswith("/tts/create"):
            return httpx.Response(200, json={"data": {"url": "https://example.com/audio.mp3", "original_duration": 2}})
        if "/embeddings" in path:
            return httpx.Response(200, json={"data": {"embedding": [0.1, 0.2]}, "usage": {"prompt_tokens": 2}})
        if path.endswith("/images/generations"):
            image = {"b64_json": "aGVsbG8="} if provider == "modeltop" or body.get("response_format") == "b64_json" else {"url": "https://example.com/image.png"}
            data = {"model": body["model"], "data": [image]}
            return httpx.Response(200, json={"code": 200, "data": data} if provider == "maxmodel" else data)
        if path.endswith(("/chat/completions", "/responses")):
            if body.get("stream"):
                return httpx.Response(200, text='data: {"model":"mock","choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n', headers={"Content-Type": "text/event-stream"})
            return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"content": "hello"}}], "output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}]})
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST":
            if provider == "aliyun_bailian":
                return httpx.Response(200, json={"output": {"task_id": "mock-video"}})
            return httpx.Response(200, json={"id": "mock-video", "task_id": "mock-video"})
        if provider == "aliyun_bailian":
            return httpx.Response(200, json={"output": {"task_status": "SUCCEEDED", "video_url": "https://example.com/video.mp4", "video_duration": 8}})
        data = {"status": "succeeded", "duration": 4, "resolution": "480p", "content": {"video_url": "https://example.com/video.mp4"}}
        return httpx.Response(200, json={"task": data} if provider == "minimax" else data)
    return handle


@pytest.mark.parametrize(("alias", "provider"), CASES, ids=[a + ":" + p for a, p in CASES])
def test_every_model_html_example_reaches_correct_adapter(tmp_path, alias, provider):
    pages = articles()
    default = next(row[2] for row in BUILTIN_MODEL_CATALOG if row[0] == alias)
    page_id = "model-" + alias + ("-" + provider if provider != default else "")
    examples = list(requests(pages[page_id]))
    assert examples, alias
    with relay_client(tmp_path) as client:
        key_id, key, _ = provision(client, provider=provider, alias=alias, upstream_model="ignored",
                                   config={"workspaceId": "test-workspace", "region": "cn-beijing"} if provider == "aliyun_bailian" else {})
        relay = client.app.state.provider_relay
        calls = []
        relay.transport = httpx.MockTransport(mock_provider(provider, calls))
        task_id = None
        for index, (method, path, payload, _) in enumerate(examples):
            if path == "/v1/audio/transcriptions/asr_xxx":
                assert task_id
                path = "/v1/audio/transcriptions/" + task_id
            if "$TASK_ID" in path:
                assert task_id
                path = path.replace("$TASK_ID", task_id)
            headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "doc-example-" + str(index)}
            response = client.request(method, path, json=payload, headers=headers)
            if method == "DELETE":
                assert provider not in {"modeltop", "minimax", "aliyun_bailian"}, "Unsupported cancellation must not be presented as a working example"
            assert response.status_code in {200, 202, 204}, (method, path, payload, response.text)
            if payload and path in {TASKS, "/v1/audio/transcriptions"}:
                task_id = response.json()["id"]
            if method == "GET" and path.startswith(TASKS + "/"):
                assert response.json()["status"] == "succeeded"
                assert response.json()["content"]["video_url"]
        assert calls, "Model reference must exercise a generation endpoint, not only pricing"
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_usage WHERE api_key_id=?", (key_id,)).fetchone()[0] > 0


def test_general_model_examples_use_real_routes(tmp_path):
    """Also cover the shared reference pages, not just generated model pages."""
    all_articles = articles()
    known = {row[0]: row for row in BUILTIN_MODEL_CATALOG}
    for page in ("text", "images", "videos", "embeddings", "audio"):
        for index, (method, path, payload, _) in enumerate(requests(all_articles[page])):
            if not payload:
                continue  # Query/cancel lifecycle is exercised above.
            alias = payload["model"]
            provider = known[alias][2]
            with relay_client(tmp_path / (page + str(index))) as client:
                _, key, _ = provision(client, provider=provider, alias=alias, upstream_model="ignored",
                                       config={"workspaceId": "test-workspace", "region": "cn-beijing"} if provider == "aliyun_bailian" else {})
                calls = []
                client.app.state.provider_relay.transport = httpx.MockTransport(mock_provider(provider, calls))
                response = client.request(method, path, json=payload, headers={"Authorization": "Bearer " + key})
                assert response.status_code in {200, 202}, (page, index, response.text)
                assert calls


def test_asset_html_examples_route_query_fields_and_registration(tmp_path, monkeypatch, media_samples):
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    with relay_client(tmp_path) as client:
        key_id, key, _ = provision(client, provider="volcengine_ark", alias="glm-5.2", upstream_model="ignored")
        calls = []
        def provider(request):
            body = json.loads(request.content)
            action = request.url.params["Action"]
            assert body["ProjectName"] == "relay_project"
            calls.append((action, body))
            return httpx.Response(200, json={"ResponseMetadata": {"RequestId": "mock-asset-request"},
                                            "Result": {"Id": "asset-example" if action == "CreateAsset" else "group-example"}})
        client.app.state.volcengine.transport = httpx.MockTransport(provider)
        all_articles = articles()
        pages = [page for page in all_articles if page.startswith(("asset-", "group-"))]
        assert len(pages) == 11
        for page in pages:
            for method, path, payload, args in requests(all_articles[page]):
                files = None
                if "-F" in args:
                    value = args[args.index("-F") + 1]
                    filename, content_type = value.removeprefix("file=@./").split(";type=")
                    data = HEIF if filename.endswith("heic") else media_samples["sample" + Path(filename).suffix]
                    files = {"file": (filename, data, content_type)}
                if payload and payload.get("uploadId"):
                    # Substitute the upload prerequisite exactly as a customer must.
                    client.app.state.database.create_asset_record(payload["uploadId"], "relay_project", key_id,
                        "tos", payload["url"], bucket="test-bucket", object_key="example", asset_type=payload["assetType"])
                response = client.request(method, path, json=payload, files=files, headers={"Authorization": "Bearer " + key})
                assert response.status_code == 200, (page, response.text)
        assert {action for action, _ in calls} == {"CreateAssetGroup", "ListAssetGroups", "GetAssetGroup", "UpdateAssetGroup", "DeleteAssetGroup", "CreateAsset", "ListAssets", "GetAsset", "UpdateAsset", "DeleteAsset"}
        for action, body in calls:
            if action == "ListAssets":
                assert body["Filter"]["GroupIds"] == ["group-xxxxxxxx"]
            if action.startswith("List"):
                assert body["PageNumber"] == 1 and body["PageSize"] == 20


def test_generated_python_examples_execute_offline(monkeypatch):
    """Syntax-only checks miss incorrect variable substitution and binary decoding."""
    import io
    import urllib.request
    from contextlib import redirect_stdout

    monkeypatch.setenv("API_KEY", "mock-business-key")
    monkeypatch.setenv("TASK_ID", "mock-task-id")
    output_files = []
    def fake_open(filename, mode):
        assert mode == "wb"
        output_files.append(filename)
        return io.BytesIO()
    scripts = re.findall(r'<pre[^>]*data-language="python"[^>]*><code>(.*?)</code></pre>', DOCUMENT.read_text(encoding="utf-8"), re.S)
    for source in scripts:
        source = html.unescape(source)
        captured = []
        def urlopen(request, timeout):
            captured.append(request)
            assert timeout >= 1800
            assert request.get_header("Authorization") == "Bearer mock-business-key"
            assert "$TASK_ID" not in request.full_url
            body = json.loads(request.data) if request.data else {}
            if body.get("stream"):
                return io.BytesIO(b'data: {"choices":[]}\n\ndata: [DONE]\n\n')
            response = io.BytesIO(b'{"ok":true}')
            response.status = 204 if request.method == "DELETE" else 200
            return response
        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        with redirect_stdout(io.StringIO()):
            exec(compile(source, "<customer-example>", "exec"), {"open": fake_open})
        assert len(captured) == 1
    assert output_files == ["speech.mp3", "speech.mp3"]


def test_supplier_documentation_capabilities_match_effective_backend_catalogue():
    source = "import {supplierCatalog} from './tools/client-docs/build.mjs'; console.log(JSON.stringify(supplierCatalog));"
    variants = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", source], cwd=DOCUMENT.parents[1]))
    assert len(variants) == 48
    catalog = {row[0]: row for row in BUILTIN_MODEL_CATALOG}
    for variant in variants:
        assert variant["provider"] == (catalog[variant["id"]][2] if variant["primary"] else "modeltop")
        expected = MODELTOP_MODELS[variant["id"]][6] if variant["provider"] == "modeltop" else catalog[variant["id"]][6]
        assert variant["capabilities"] == expected, (variant["id"], variant["provider"])
