from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from hypothesis import settings as hypothesis_settings
from PIL import Image
from pillow_heif import register_heif_opener

from app.config import Settings
from app.errors import ApiError
from app.main import create_app
from app.volcengine import VolcengineClient


ADMIN_HEADERS = {"x-admin-token": "test-admin", "content-type": "application/json"}


def image_bytes(image_format: str) -> bytes:
    register_heif_opener()
    output = BytesIO()
    Image.new("RGB", (512, 512), "#526d82").save(output, format=image_format)
    return output.getvalue()


JPEG = image_bytes("JPEG")
PNG = image_bytes("PNG")
WEBP = image_bytes("WEBP")
BMP = image_bytes("BMP")
TIFF = image_bytes("TIFF")
GIF = image_bytes("GIF")
HEIF = image_bytes("HEIF")


class FakeVolcengine:
    async def call(self, action, payload, principal):
        return JSONResponse({"action": action, "payload": payload, "projectName": principal.project_name})


@pytest.fixture(autouse=True)
def stub_volcengine_project_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_project(_: VolcengineClient, project_name: str) -> dict[str, str]:
        return {"ProjectName": project_name, "Status": "active"}

    monkeypatch.setattr(VolcengineClient, "get_project", get_project)


def build_settings(database_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "volcengine_access_key": "test-ak",
        "volcengine_secret_key": "test-sk",
        "tos_bucket": "test-bucket",
        "tos_public_base_url": "https://cdn.example.com",
        "admin_cookie_secure": False,
        "admin_argon2_time_cost": 1,
        "admin_argon2_memory_cost": 8192,
        "admin_argon2_parallelism": 1,
        "admin_backup_enabled": False,
        "multi_provider_enabled": False,
        "database_path": database_path,
        "cors_origins": "http://localhost:3000",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def migrate_legacy_admin_test_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run existing internal-route tests through the real session/CSRF flow.

    The old test suite uses a sentinel X-Admin-Token header in many places. It is
    converted only in tests; production no longer accepts that header.
    """
    original_request = TestClient.request

    def request_with_admin_session(self: TestClient, method: str, url: str, **kwargs: object):
        headers = dict(kwargs.get("headers") or {})
        legacy = headers.pop("x-admin-token", None) or headers.pop("X-Admin-Token", None)
        if legacy == "test-admin":
            csrf_token = getattr(self, "_test_admin_csrf", None)
            if csrf_token is None:
                try:
                    _, initial_password = self.app.state.admin_auth.create_initial_super_admin(
                        "test-admin", "Test Admin"
                    )
                    # Legacy internal-route tests represent a daily business operator,
                    # not the security-only super administrator.
                    with self.app.state.database.connect() as connection:
                        connection.execute(
                            "UPDATE admin_users SET role='admin' WHERE username_normalized='test-admin'"
                        )
                    login_password = initial_password
                except ApiError as error:
                    if error.code != "initial_admin_exists":
                        raise
                    login_password = "Test-admin-password!2026"
                login = original_request(
                    self,
                    "POST",
                    "/api/internal/auth/login",
                    json={"username": "test-admin", "password": login_password},
                )
                if login.status_code != 200:
                    raise AssertionError(login.text)
                csrf_token = login.json()["csrfToken"]
                if login.json()["user"]["mustChangePassword"]:
                    changed = original_request(
                        self,
                        "POST",
                        "/api/internal/auth/change-password",
                        headers={"X-CSRF-Token": csrf_token},
                        json={
                            "currentPassword": login_password,
                            "newPassword": "Test-admin-password!2026",
                        },
                    )
                    if changed.status_code != 200:
                        raise AssertionError(changed.text)
                    login = original_request(
                        self,
                        "POST",
                        "/api/internal/auth/login",
                        json={"username": "test-admin", "password": "Test-admin-password!2026"},
                    )
                    if login.status_code != 200:
                        raise AssertionError(login.text)
                    csrf_token = login.json()["csrfToken"]
                setattr(self, "_test_admin_csrf", csrf_token)
            headers["X-CSRF-Token"] = csrf_token
            kwargs["headers"] = headers
        return original_request(self, method, url, **kwargs)

    monkeypatch.setattr(TestClient, "request", request_with_admin_session)


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
