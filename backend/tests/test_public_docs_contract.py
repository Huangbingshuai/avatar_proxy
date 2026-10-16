import json
import ast
import html
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from app.database import BUILTIN_DISABLED_MODEL_ALIASES, BUILTIN_MODEL_CATALOG
from app.routers.ark_compat import ARK_VIDEO_FIELDS, router as ark_router
from app.routers.assets import router as asset_router
from app.routers.auth import router as auth_router
from app.routers.openai_compat import (
    CHAT_FIELDS, RESPONSE_FIELDS, IMAGE_FIELDS, EMBEDDING_FIELDS,
    MULTIMODAL_EMBEDDING_FIELDS, SPEECH_FIELDS, TRANSCRIPTION_FIELDS,
    AUDIO_GENERATION_FIELDS, router as openai_router,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DOC = BACKEND_ROOT / "CLIENT_API.md"
REFERENCE_ROOT = BACKEND_ROOT / "docs" / "client-api"
ADMIN_BILLING_DOC = BACKEND_ROOT / "ADMIN_BILLING_API.md"
MODEL_RELAY_DOC = BACKEND_ROOT / "MODEL_RELAY_API.md"
RICHIDRAMA_DOC = BACKEND_ROOT / "RICHIDRAMA_RELAY_ALIGNMENT.md"
CUSTOMER_DOCS = [CLIENT_DOC, *sorted(REFERENCE_ROOT.glob("*.md"))]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _customer_text() -> str:
    return "\n".join(_text(path) for path in CUSTOMER_DOCS)


def _slug(heading: str) -> str:
    return re.sub(r"[^\w\s-]", "", heading.replace("`", "").lower()).replace(" ", "-")


def test_client_api_model_table_matches_builtin_catalog() -> None:
    model_section = _text(REFERENCE_ROOT / "models.md").split("## 模型与接口对照表", 1)[1].split("## 查询模型价格", 1)[0]
    rows = re.findall(r"^\| `([^`]+)` \| (.+)$", model_section, flags=re.MULTILINE)
    documented = {alias for alias, _ in rows}
    expected = {row[0] for row in BUILTIN_MODEL_CATALOG if row[0] not in BUILTIN_DISABLED_MODEL_ALIASES}
    assert documented == expected
    assert len(rows) == len(documented), "每个模型只保留一个对照行"
    assert all("POST /" in row for _, row in rows)


def test_each_model_has_its_own_reference_and_public_metadata() -> None:
    expected = {row[0] for row in BUILTIN_MODEL_CATALOG if row[0] not in BUILTIN_DISABLED_MODEL_ALIASES}
    reference = _text(REFERENCE_ROOT / "model-reference.md")
    documented = set(re.findall(r"^## `([^`]+)`$", reference, re.M))
    assert documented == expected
    metadata = json.loads((BACKEND_ROOT.parent / "tools/client-docs/models.json").read_text(encoding="utf-8"))
    assert {row["id"] for row in metadata} == expected
    assert len(metadata) == len(expected)
    catalog = {row[0]: row for row in BUILTIN_MODEL_CATALOG}
    for row in metadata:
        assert set(row) == {"id", "name", "modality", "capabilities", "summary"}
        assert row["capabilities"] == catalog[row["id"]][6]
        assert row["modality"] == catalog[row["id"]][3]
    for block in re.split(r"^## `[^`]+`$", reference, flags=re.M)[1:]:
        assert "```bash" in block
        assert "参数" in block
        assert "响应" in block or "结果" in block


def test_asset_operations_have_independent_reference_sections() -> None:
    assets = _text(REFERENCE_ROOT / "assets.md")
    for heading in (
        "上传本地素材", "创建素材组", "查询素材组列表", "查询单个素材组",
        "修改素材组", "删除素材组", "登记素材", "查询素材列表",
        "查询单个素材", "修改素材名称", "删除素材",
    ):
        assert f"## {heading}" in assets


def test_client_api_lists_current_public_model_routes() -> None:
    client = _text(CLIENT_DOC)
    route_paths = {
        route.path for router in (auth_router, asset_router, openai_router, ark_router)
        for route in router.routes
    }
    expected_paths = {
        "/api/auth/me",
        "/api/asset-group/create", "/api/asset-group/list", "/api/asset-group/get",
        "/api/asset-group/update", "/api/asset-group/delete",
        "/api/asset/create", "/api/asset/list", "/api/asset/get",
        "/api/asset/update", "/api/asset/delete", "/api/asset/upload-file",
        "/v1/models", "/v1/pricing", "/v1/chat/completions", "/v1/responses",
        "/v1/images/generations", "/v1/embeddings", "/v1/embeddings/multimodal",
        "/v1/audio/speech", "/v1/audio/transcriptions",
        "/v1/audio/transcriptions/{task_id}", "/v1/audio/generations",
        "/api/v3/contents/generations/tasks",
        "/api/v3/contents/generations/tasks/{task_id}",
    }
    assert expected_paths <= route_paths
    references = "\n".join(_text(p) for p in CUSTOMER_DOCS if p != CLIENT_DOC)
    for route in (route for router in (auth_router, asset_router, openai_router, ark_router) for route in router.routes):
        if route.path not in expected_paths:
            continue
        public_path = route.path.replace("{task_id}", "{taskId}")
        for method in route.methods - {"HEAD", "OPTIONS"}:
            assert f"| `{method}` | `{public_path}` |" in client
        assert public_path in references
    assert "/health" in client


def test_client_api_auth_example_matches_public_response() -> None:
    basics = _text(REFERENCE_ROOT / "basics.md")
    auth_section = basics.split("### 验证 API Key", 1)[1].split("## 地址与示例约定", 1)[0]
    assert '"authenticated": true' in auth_section
    assert '"apiKeyId":' in auth_section
    assert '"projectName":' not in auth_section


def test_client_api_documents_customer_visible_limits_and_errors() -> None:
    client = _customer_text()
    for fact in (
        "1～128 个字符", "范围为 `1`～`100`", "一次只接受一个字符串",
        "1～10000 个字符", "`mp3`、`pcm`、`ogg_opus`", "`-50`～`100`",
        "1～4000 个字符", "`metric`、`scope`、`limit`、`used`、`resetAt` 和 `requestId`",
        "`Retry-After`", "idempotency_outcome_unknown", "automaticRetry=false",
        "缺失的真实细分用量", "十进制字符串", "同项目的另一枚 Key",
    ):
        assert fact in client


def test_client_api_remains_customer_facing() -> None:
    client = _customer_text()
    for forbidden in (
        "/api/internal/", "main@", "MODEL_GENERATION_TIMEOUT_SECONDS",
        "/opt/avatar-proxy", "5.7 文档基线", "火山方舟", "漫剧", "RichiDrama", "瑞池",
    ):
        assert forbidden not in client
    # Reject full live keys while allowing the deliberately short placeholder.
    assert not re.search(r"vap_live_[A-Za-z0-9_-]{20,}", client)
    assert "客户系统对接检查表" in client
    assert "请联系管理员" in client
    assert "# 星辰平台 API 文档" in client
    assert len(_text(CLIENT_DOC).splitlines()) < 200


def test_specialized_docs_defer_to_client_contract() -> None:
    client = _customer_text()
    billing = _text(ADMIN_BILLING_DOC)
    relay = _text(MODEL_RELAY_DOC)
    richidrama = _text(RICHIDRAMA_DOC)
    assert "版本：6.0" in client
    assert "版本：1.2" in billing
    assert "独立的“模型价格”页面" in billing
    assert "`/v1/pricing`" in billing
    assert "CLIENT_API.md" in relay and "CLIENT_API.md" in richidrama
    assert len(relay.splitlines()) < 40
    assert "negative_prompt" not in IMAGE_FIELDS
    assert "`negative_prompt` 不属于当前公开图片契约" in client
    assert "aspect_ratio" not in ARK_VIDEO_FIELDS
    assert "只使用 `ratio`" in relay
    assert "只有 `ratio`" in richidrama


@pytest.mark.parametrize("path", CUSTOMER_DOCS + [MODEL_RELAY_DOC, RICHIDRAMA_DOC, ADMIN_BILLING_DOC])
def test_document_links_resolve(path: Path) -> None:
    # Strip fenced examples, so code samples are not mistaken for prose links.
    prose = re.sub(r"```.*?```", "", _text(path), flags=re.S)
    for href in re.findall(r"\]\(([^)]+)\)", prose):
        if href.startswith(("https://", "http://")):
            continue
        relative, _, anchor = href.partition("#")
        target = (path.parent / unquote(relative)).resolve() if relative else path
        assert target.is_file(), f"{path.name}: missing {href}"
        if anchor and target.suffix == ".md":
            headings = re.findall(r"^#{1,6} (.+)$", _text(target), flags=re.M)
            assert unquote(anchor) in {_slug(heading) for heading in headings}, f"{path.name}: broken {href}"


@pytest.mark.parametrize("path", CUSTOMER_DOCS)
def test_json_and_curl_examples_parse(path: Path) -> None:
    content = _text(path)
    for example in re.findall(r"```json\n(.*?)\n```", content, re.S):
        assert isinstance(json.loads(example), (dict, list))
    for block in re.findall(r"```bash\n(.*?)\n```", content, re.S):
        for body in re.findall(r"-d '([^']+)'", block, re.S):
            assert isinstance(json.loads(body), dict), path.name


def test_documented_text_whitelists_match_routes() -> None:
    content = _text(REFERENCE_ROOT / "text.md")
    for label, expected in (("Chat Completions", CHAT_FIELDS), ("Responses", RESPONSE_FIELDS)):
        block = content.split(f"{label} 当前接受的顶层字段为：", 1)[1].split("```text", 1)[1].split("```", 1)[0]
        documented = {field.strip() for field in block.replace("\n", "").split(",")}
        assert documented == expected


def test_curl_payloads_only_use_supported_model_fields() -> None:
    whitelists = {
        "/v1/chat/completions": CHAT_FIELDS, "/v1/responses": RESPONSE_FIELDS,
        "/v1/images/generations": IMAGE_FIELDS, "/v1/embeddings": EMBEDDING_FIELDS,
        "/v1/embeddings/multimodal": MULTIMODAL_EMBEDDING_FIELDS,
        "/v1/audio/speech": SPEECH_FIELDS, "/v1/audio/transcriptions": TRANSCRIPTION_FIELDS,
        "/v1/audio/generations": AUDIO_GENERATION_FIELDS,
        "/api/v3/contents/generations/tasks": ARK_VIDEO_FIELDS,
    }
    aliases = {row[0] for row in BUILTIN_MODEL_CATALOG if row[0] not in BUILTIN_DISABLED_MODEL_ALIASES}
    for path in CUSTOMER_DOCS:
        for block in re.findall(r"```bash\n(.*?)\n```", _text(path), re.S):
            for request in block.split("curl ")[1:]:
                endpoint = re.search(r"\$BASE_URL(/[^\s\"?]+)", request)
                body = re.search(r"-d '([^']+)'", request, re.S)
                if endpoint and body and endpoint[1] in whitelists:
                    payload = json.loads(body[1])
                    assert payload.keys() <= whitelists[endpoint[1]], path.name
                    assert payload["model"] in aliases


def test_generated_python_samples_are_valid_without_executing_requests() -> None:
    document = _text(BACKEND_ROOT / "CLIENT_API.html")
    samples = re.findall(r'<pre[^>]*data-language="python"[^>]*><code>(.*?)</code></pre>', document, re.S)
    assert len(samples) >= len(BUILTIN_MODEL_CATALOG)
    for sample in samples:
        source = html.unescape(sample)
        ast.parse(source)
        assert "urllib.request" in source
