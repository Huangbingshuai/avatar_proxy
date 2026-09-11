import re
from pathlib import Path

from app.database import BUILTIN_DISABLED_MODEL_ALIASES, BUILTIN_MODEL_CATALOG
from app.routers.ark_compat import ARK_VIDEO_FIELDS, router as ark_router
from app.routers.assets import router as asset_router
from app.routers.auth import router as auth_router
from app.routers.openai_compat import IMAGE_FIELDS, router as openai_router


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DOC = BACKEND_ROOT / "CLIENT_API.md"
ADMIN_BILLING_DOC = BACKEND_ROOT / "ADMIN_BILLING_API.md"
MODEL_RELAY_DOC = BACKEND_ROOT / "MODEL_RELAY_API.md"
RICHIDRAMA_DOC = BACKEND_ROOT / "RICHIDRAMA_RELAY_ALIGNMENT.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_client_api_model_table_matches_builtin_catalog() -> None:
    client = _text(CLIENT_DOC)
    model_section = client.split("### 13.1 可用模型", 1)[1].split("### 13.2", 1)[0]
    documented = set(re.findall(r"^\| `([^`]+)` \|", model_section, flags=re.MULTILINE))
    expected = {
        row[0] for row in BUILTIN_MODEL_CATALOG
        if row[0] not in BUILTIN_DISABLED_MODEL_ALIASES
    }
    assert documented == expected


def test_client_api_lists_current_public_model_routes() -> None:
    client = _text(CLIENT_DOC)
    route_paths = {
        route.path
        for router in (auth_router, asset_router, openai_router, ark_router)
        for route in router.routes
    }
    expected_paths = {
        "/api/auth/me",
        "/api/asset-group/create",
        "/api/asset-group/list",
        "/api/asset-group/get",
        "/api/asset-group/update",
        "/api/asset-group/delete",
        "/api/asset/create",
        "/api/asset/list",
        "/api/asset/get",
        "/api/asset/update",
        "/api/asset/delete",
        "/api/asset/upload-file",
        "/v1/models",
        "/v1/pricing",
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/images/generations",
        "/v1/embeddings",
        "/v1/embeddings/multimodal",
        "/v1/audio/speech",
        "/v1/audio/transcriptions",
        "/v1/audio/transcriptions/{task_id}",
        "/v1/audio/generations",
        "/api/v3/contents/generations/tasks",
        "/api/v3/contents/generations/tasks/{task_id}",
    }
    assert expected_paths <= route_paths
    for path in expected_paths:
        assert path.replace("{task_id}", "{taskId}") in client
    assert "/health" in client


def test_client_api_auth_example_matches_public_response() -> None:
    client = _text(CLIENT_DOC)
    auth_section = client.split("### 4.2 验证 API Key", 1)[1].split("## 5.", 1)[0]
    assert '"authenticated": true' in auth_section
    assert '"apiKeyId":' in auth_section
    assert '"projectName":' not in auth_section


def test_client_api_documents_customer_visible_limits_and_errors() -> None:
    client = _text(CLIENT_DOC)
    for fact in (
        "1～128 个字符",
        "范围为 `1`～`100`",
        "一次只接受一个字符串",
        "1～10000 个字符",
        "`mp3`、`pcm`、`ogg_opus`",
        "`-50`～`100`",
        "1～4000 个字符",
        "`metric`、`scope`、`limit`、`used`、`resetAt` 和 `requestId`",
        "`Retry-After`",
    ):
        assert fact in client


def test_client_api_remains_customer_facing() -> None:
    client = _text(CLIENT_DOC)
    assert "/api/internal/" not in client
    assert "main@" not in client
    assert "客户系统对接检查表" in client


def test_specialized_docs_defer_to_client_contract() -> None:
    client = _text(CLIENT_DOC)
    billing = _text(ADMIN_BILLING_DOC)
    relay = _text(MODEL_RELAY_DOC)
    richidrama = _text(RICHIDRAMA_DOC)

    assert "版本：5.8" in client
    assert "版本：1.2" in billing
    assert "独立的“模型价格”页面" in billing
    assert "`/v1/pricing`" in billing
    assert "旧的 `seedance-*`、`seedream-*` 短别名已经停用" in client
    assert "CLIENT_API.md" in relay
    assert "CLIENT_API.md" in richidrama
    assert "negative_prompt" not in IMAGE_FIELDS
    assert "`negative_prompt` 不属于当前公开图片契约" in client
    assert "aspect_ratio" not in ARK_VIDEO_FIELDS
    assert "只使用 `ratio`" in relay
    assert "只有 `ratio`" in richidrama
