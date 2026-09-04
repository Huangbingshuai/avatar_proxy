import re
from pathlib import Path

from app.database import BUILTIN_DISABLED_MODEL_ALIASES, BUILTIN_MODEL_CATALOG
from app.routers.ark_compat import ARK_VIDEO_FIELDS, router as ark_router
from app.routers.openai_compat import IMAGE_FIELDS, router as openai_router


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DOC = BACKEND_ROOT / "CLIENT_API.md"
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
        for router in (openai_router, ark_router)
        for route in router.routes
    }
    expected_paths = {
        "/v1/models",
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/images/generations",
        "/api/v3/contents/generations/tasks",
        "/api/v3/contents/generations/tasks/{task_id}",
    }
    assert expected_paths <= route_paths
    for path in expected_paths:
        assert path.replace("{task_id}", "{taskId}") in client


def test_specialized_docs_defer_to_client_contract() -> None:
    client = _text(CLIENT_DOC)
    relay = _text(MODEL_RELAY_DOC)
    richidrama = _text(RICHIDRAMA_DOC)

    assert "版本：5.3" in client
    assert "CLIENT_API.md" in relay
    assert "CLIENT_API.md" in richidrama
    assert "negative_prompt" not in IMAGE_FIELDS
    assert "`negative_prompt` 不属于当前公开图片契约" in client
    assert "aspect_ratio" not in ARK_VIDEO_FIELDS
    assert "只使用 `ratio`" in relay
    assert "只有 `ratio`" in richidrama
