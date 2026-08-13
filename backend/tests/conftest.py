from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from hypothesis import settings as hypothesis_settings

from app.config import Settings
from app.main import create_app


ADMIN_HEADERS = {"x-admin-token": "test-admin", "content-type": "application/json"}


class FakeVolcengine:
    async def call(self, action, payload, principal):
        return JSONResponse({"action": action, "payload": payload, "projectName": principal.project_name})


def build_settings(database_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "volcengine_access_key": "test-ak",
        "volcengine_secret_key": "test-sk",
        "seedance_ark_api_key": "test-ark-key",
        "tos_bucket": "test-bucket",
        "tos_public_base_url": "https://cdn.example.com",
        "console_admin_token": "test-admin",
        "database_path": database_path,
        "cors_origins": "http://localhost:3000",
    }
    values.update(overrides)
    return Settings(**values)


def create_project(client: TestClient, name: str = "drama_prod") -> None:
    response = client.post(
        "/api/internal/project/create",
        headers=ADMIN_HEADERS,
        json={"name": name, "displayName": "短剧生产", "description": "production"},
    )
    assert response.status_code == 201, response.text


def create_key(client: TestClient, project_name: str = "drama_prod", name: str = "production") -> tuple[str, str]:
    response = client.post(
        "/api/internal/apikey/create",
        headers=ADMIN_HEADERS,
        json={"name": name, "projectName": project_name},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["apiKey"]["id"], body["secret"]


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    return build_settings


@pytest.fixture
def client_factory(settings_factory: Callable[..., Settings]) -> Callable[..., Iterator[TestClient]]:
    def factory(database_path: Path, **overrides: object) -> TestClient:
        return TestClient(create_app(settings_factory(database_path, **overrides)))

    return factory


hypothesis_settings.register_profile(
    "ci",
    max_examples=50,
    deadline=None,
    derandomize=True,
)
hypothesis_settings.load_profile("ci")
