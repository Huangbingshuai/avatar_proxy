import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import tos
from fastapi.testclient import TestClient
from hypothesis import assume, given, strategies as st
from PIL import Image

from app.main import create_app
from app.errors import ApiError
from app.storage import content_matches_type, inspect_media, is_placeholder

from conftest import (
    ADMIN_HEADERS,
    BMP,
    GIF,
    HEIF,
    JPEG,
    PNG,
    TIFF,
    WEBP,
    build_settings,
    create_key,
    create_project,
)


class SuccessfulTosClient:
    uploads: list[tuple[str, str, bytes, str]] = []
    deletes: list[tuple[str, str]] = []

    def __init__(self, *args):
        pass

    def put_object(self, bucket, key, *, content, content_type):
        payload = content.read() if hasattr(content, "read") else content
        self.uploads.append((bucket, key, payload, content_type))
        return SimpleNamespace(etag="etag", request_id="request-id")

    def delete_object(self, bucket, key):
        self.deletes.append((bucket, key))
        return SimpleNamespace(status_code=204)


def upload(client: TestClient, secret: str, filename: str, content: bytes, content_type: str):
    return client.post(
        "/api/asset/upload-file",
        headers={"Authorization": f"Bearer {secret}"},
        files={"file": (filename, content, content_type)},
    )


@pytest.fixture(scope="module")
def media_samples(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required for real audio/video validation tests")
    directory = tmp_path_factory.mktemp("media-samples")
    commands = {
        "sample.mp4": [
            "-f", "lavfi", "-i", "color=c=blue:s=640x640:r=24:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        ],
        "sample.mov": [
            "-f", "lavfi", "-i", "color=c=green:s=640x640:r=24:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        ],
        "sample.wav": [
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=2",
            "-c:a", "pcm_s16le",
        ],
        "sample.mp3": [
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100:duration=2",
            "-c:a", "libmp3lame", "-b:a", "128k",
        ],
    }
    samples: dict[str, bytes] = {}
    for filename, arguments in commands.items():
        destination = directory / filename
        try:
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *arguments, str(destination)],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            pytest.skip(f"ffmpeg could not generate {filename}: {error}")
        samples[filename] = destination.read_bytes()
    return samples


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "suffix"),
    [
        ("portrait.jpg", JPEG, "image/jpeg", ".jpg"),
        ("portrait.png", PNG, "image/png", ".png"),
        ("portrait.webp", WEBP, "image/webp", ".webp"),
        ("portrait.bmp", BMP, "image/bmp", ".bmp"),
        ("portrait.tiff", TIFF, "image/tiff", ".tiff"),
        ("portrait.gif", GIF, "image/gif", ".gif"),
        ("portrait.heic", HEIF, "image/heic", ".heic"),
        ("portrait.heif", HEIF, "image/heif", ".heif"),
    ],
    ids=["jpeg", "png", "webp", "bmp", "tiff", "gif", "heic", "heif"],
)
def test_supported_image_types_upload_and_commit_usage(
    tmp_path: Path, monkeypatch, filename: str, content: bytes, content_type: str, suffix: str
) -> None:
    SuccessfulTosClient.uploads.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / f"{suffix[1:]}.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, filename, content, content_type)
        usage = client.get(
            "/api/internal/quota/usage",
            headers=ADMIN_HEADERS,
            params={"projectName": "drama_prod"},
        ).json()["usage"]

    assert response.status_code == 200
    assert response.json()["objectKey"].endswith(suffix)
    assert response.json()["contentType"] == content_type
    assert response.json()["size"] == len(content)
    assert response.json()["assetType"] == "Image"
    assert response.json()["mediaMetadata"]["width"] == 512
    record = app.state.database.get_asset_record(response.json()["uploadId"])
    assert record is not None
    assert record["asset_type"] == "Image"
    assert record["content_type"] == content_type
    assert usage["totalStorageBytes"] == len(content)


@pytest.mark.parametrize(
    ("filename", "content_type", "asset_type"),
    [
        ("sample.mp4", "video/mp4", "Video"),
        ("sample.mov", "video/quicktime", "Video"),
        ("sample.wav", "audio/wav", "Audio"),
        ("sample.mp3", "audio/mpeg", "Audio"),
    ],
)
def test_supported_audio_and_video_uploads_are_probed_and_persisted(
    tmp_path: Path,
    monkeypatch,
    media_samples: dict[str, bytes],
    filename: str,
    content_type: str,
    asset_type: str,
) -> None:
    SuccessfulTosClient.uploads.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / f"{filename}.db"))
    content = media_samples[filename]
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, filename, content, content_type)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assetType"] == asset_type
    assert body["contentType"] == content_type
    assert body["size"] == len(content)
    assert body["mediaMetadata"]["duration"] >= 2
    if asset_type == "Video":
        assert body["mediaMetadata"]["width"] == 640
        assert body["mediaMetadata"]["height"] == 640
        assert body["mediaMetadata"]["fps"] == 24
    record = app.state.database.get_asset_record(body["uploadId"])
    assert record is not None
    assert record["asset_type"] == asset_type
    assert record["content_type"] == content_type


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("broken.mp4", "video/mp4"),
        ("broken.mov", "video/quicktime"),
        ("broken.wav", "audio/wav"),
        ("broken.mp3", "audio/mpeg"),
    ],
)
def test_corrupt_audio_and_video_are_rejected(
    tmp_path: Path, filename: str, content_type: str
) -> None:
    app = create_app(build_settings(tmp_path / f"broken-{filename}.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, filename, b"not-a-media-file", content_type)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_media_content"


def ffprobe_result(
    *,
    media_type: str,
    duration: float,
    width: int = 640,
    height: int = 640,
    fps: float = 24,
) -> SimpleNamespace:
    if media_type == "video":
        streams = [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": width,
                "height": height,
                "avg_frame_rate": f"{int(fps * 1000)}/1000",
                "r_frame_rate": f"{int(fps * 1000)}/1000",
                "duration": str(duration),
            }
        ]
        format_name = "mov,mp4,m4a,3gp,3g2,mj2"
    else:
        streams = [{"codec_type": "audio", "codec_name": "mp3", "duration": str(duration)}]
        format_name = "mp3"
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {"format": {"format_name": format_name, "duration": str(duration)}, "streams": streams}
        ),
    )


@pytest.mark.parametrize(
    ("duration", "fps", "expected_code"),
    [
        (1.999, 24, "invalid_video_duration"),
        (30.001, 24, "invalid_video_duration"),
        (2, 23.9, "invalid_video_fps"),
        (2, 60.1, "invalid_video_fps"),
    ],
)
def test_video_duration_and_fps_outside_official_boundaries_are_rejected(
    tmp_path: Path, monkeypatch, duration: float, fps: float, expected_code: str
) -> None:
    monkeypatch.setattr(
        "app.storage.subprocess.run",
        lambda *args, **kwargs: ffprobe_result(media_type="video", duration=duration, fps=fps),
    )

    with pytest.raises(ApiError) as captured:
        inspect_media(tmp_path / "probe.mp4", "video/mp4")

    assert captured.value.code == expected_code


@pytest.mark.parametrize(("duration", "fps"), [(2, 24), (30, 60)])
def test_video_duration_and_fps_official_boundaries_are_accepted(
    tmp_path: Path, monkeypatch, duration: float, fps: float
) -> None:
    monkeypatch.setattr(
        "app.storage.subprocess.run",
        lambda *args, **kwargs: ffprobe_result(media_type="video", duration=duration, fps=fps),
    )

    metadata = inspect_media(tmp_path / "probe.mp4", "video/mp4")

    assert metadata["duration"] == duration
    assert metadata["fps"] == fps


@pytest.mark.parametrize(("duration", "valid"), [(1.999, False), (2, True), (30, True), (30.001, False)])
def test_audio_duration_boundaries(tmp_path: Path, monkeypatch, duration: float, valid: bool) -> None:
    monkeypatch.setattr(
        "app.storage.subprocess.run",
        lambda *args, **kwargs: ffprobe_result(media_type="audio", duration=duration),
    )
    if valid:
        assert inspect_media(tmp_path / "probe.mp3", "audio/mpeg")["duration"] == duration
    else:
        with pytest.raises(ApiError) as captured:
            inspect_media(tmp_path / "probe.mp3", "audio/mpeg")
        assert captured.value.code == "invalid_audio_duration"


@pytest.mark.parametrize(
    ("size", "expected_code"),
    [((300, 512), "invalid_image_dimensions"), ((6000, 512), "invalid_image_dimensions"),
     ((512, 1280), "invalid_image_ratio"), ((1280, 512), "invalid_image_ratio")],
)
def test_image_dimension_and_ratio_boundaries(
    tmp_path: Path, size: tuple[int, int], expected_code: str
) -> None:
    path = tmp_path / f"{size[0]}x{size[1]}.png"
    Image.new("RGB", size, "#526d82").save(path, format="PNG")

    with pytest.raises(ApiError) as captured:
        inspect_media(path, "image/png")

    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    ("content", "content_type", "status", "code"),
    [
        (b"", "image/png", 400, "empty_file"),
        (b"plain text", "text/plain", 415, "unsupported_media_type"),
        (JPEG, "image/png", 400, "media_type_mismatch"),
        (PNG, "image/jpeg", 400, "media_type_mismatch"),
        (b"RIFFbad-data", "image/webp", 400, "invalid_media_content"),
    ],
)
def test_upload_validation_rejects_empty_unsupported_and_forged_files(
    tmp_path: Path, content: bytes, content_type: str, status: int, code: str
) -> None:
    app = create_app(build_settings(tmp_path / f"{code}-{content_type.split('/')[-1]}.db"))
    filename = {
        "image/png": "payload.png",
        "image/jpeg": "payload.jpg",
        "image/webp": "payload.webp",
        "text/plain": "payload.txt",
    }[content_type]
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, filename, content, content_type)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_upload_rejects_extension_that_does_not_match_declared_media_type(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "extension.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, "portrait.exe", PNG, "image/png")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_file_extension"


def test_upload_rejects_file_above_configured_limit(tmp_path: Path) -> None:
    app = create_app(build_settings(tmp_path / "large.db", upload_max_bytes=8))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, "large.png", PNG + b"x", "image/png")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"tos_access_key": "", "volcengine_access_key": ""}, "tos_not_configured"),
        ({"tos_bucket": "Invalid_Bucket"}, "tos_bucket_invalid"),
    ],
)
def test_upload_rejects_missing_configuration_and_invalid_bucket(
    tmp_path: Path, overrides: dict, code: str
) -> None:
    app = create_app(build_settings(tmp_path / f"{code}.db", **overrides))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, "portrait.png", PNG, "image/png")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == code


def test_filename_is_sanitized_and_default_public_url_is_derived(tmp_path: Path, monkeypatch) -> None:
    SuccessfulTosClient.uploads.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / "filename.db", tos_public_base_url=""))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        response = upload(client, secret, "../../bad name<>.PNG", PNG, "image/png")

    body = response.json()
    assert response.status_code == 200
    assert body["objectKey"].startswith("avatar-assets/drama_prod/")
    assert body["objectKey"].endswith("-badname.png")
    assert body["url"].startswith("https://test-bucket.tos-cn-beijing.volces.com/")
    assert ".." not in body["objectKey"]


@given(st.binary(min_size=0, max_size=64), st.sampled_from(["image/png", "image/jpeg", "image/webp"]))
def test_random_non_image_bytes_never_pass_signature_validation(content: bytes, content_type: str) -> None:
    valid = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    assume(not valid[content_type])
    assert content_matches_type(content, content_type) is False


@pytest.mark.parametrize("value", ["", "  ", "your_key", "YOUR_SECRET", "replace_with_real_value"])
def test_placeholder_detection_is_case_and_whitespace_insensitive(value: str) -> None:
    assert is_placeholder(value) is True


def test_tos_server_error_rolls_back_quota_and_maps_response(tmp_path: Path, monkeypatch) -> None:
    class ServerFailure:
        def __init__(self, *args):
            pass

        def put_object(self, *args, **kwargs):
            response = SimpleNamespace(request_id="tos-request", headers={}, status=503)
            raise tos.exceptions.TosServerError(response, "busy", "ServiceUnavailable", "host", "/object")

    monkeypatch.setattr("app.storage.tos.TosClientV2", ServerFailure)
    app = create_app(build_settings(tmp_path / "server-failure.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={
                "projectName": "drama_prod",
                "enabled": True,
                "dailyUploadFiles": 1,
                "dailyUploadBytes": len(PNG),
            },
        )
        response = upload(client, secret, "portrait.png", PNG, "image/png")
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()["usage"]

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "tos_upload_rejected"
    assert "tos-request" in response.json()["error"]["message"]
    assert usage.get("dailyUploadFiles", 0) == 0
    assert usage.get("dailyUploadBytes", 0) == 0


def test_tos_client_error_rolls_back_then_same_quota_can_succeed(tmp_path: Path, monkeypatch) -> None:
    class ClientFailure:
        def __init__(self, *args):
            pass

        def put_object(self, *args, **kwargs):
            raise tos.exceptions.TosClientError("bad client")

    monkeypatch.setattr("app.storage.tos.TosClientV2", ClientFailure)
    app = create_app(build_settings(tmp_path / "client-failure.db"))
    with TestClient(app) as client:
        create_project(client)
        _, secret = create_key(client)
        client.put(
            "/api/internal/project/quota",
            headers=ADMIN_HEADERS,
            json={
                "projectName": "drama_prod",
                "enabled": True,
                "dailyUploadFiles": 1,
                "dailyUploadBytes": len(PNG),
            },
        )
        failed = upload(client, secret, "portrait.png", PNG, "image/png")
        monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
        succeeded = upload(client, secret, "portrait.png", PNG, "image/png")

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "tos_upload_failed"
    assert succeeded.status_code == 200


def test_ledger_write_failure_rolls_back_quota_and_deletes_uploaded_object(tmp_path: Path, monkeypatch) -> None:
    SuccessfulTosClient.deletes.clear()
    monkeypatch.setattr("app.storage.tos.TosClientV2", SuccessfulTosClient)
    app = create_app(build_settings(tmp_path / "ledger-failure.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.database.create_asset_record = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full"))
        response = upload(client, secret, "portrait.png", PNG, "image/png")
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()["usage"]

    assert response.status_code == 500
    assert usage.get("dailyUploadFiles", 0) == 0
    assert usage.get("dailyUploadBytes", 0) == 0
    assert usage["totalStorageBytes"] == 0
    assert len(SuccessfulTosClient.deletes) == 1


def test_failed_rollback_delete_still_releases_reserved_quota(tmp_path: Path, monkeypatch) -> None:
    class RollbackDeleteFailure(SuccessfulTosClient):
        def delete_object(self, bucket, key):
            raise tos.exceptions.TosClientError("delete failed")

    monkeypatch.setattr("app.storage.tos.TosClientV2", RollbackDeleteFailure)
    app = create_app(build_settings(tmp_path / "rollback-delete.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        create_project(client)
        _, secret = create_key(client)
        app.state.database.create_asset_record = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full"))
        response = upload(client, secret, "portrait.png", PNG, "image/png")
        usage = client.get(
            "/api/internal/quota/usage", headers=ADMIN_HEADERS, params={"projectName": "drama_prod"}
        ).json()["usage"]

    assert response.status_code == 500
    assert usage.get("dailyUploadFiles", 0) == 0
    assert usage["totalStorageBytes"] == 0


def test_cleanup_boundary_includes_exactly_48_hours_but_not_newer(tmp_path: Path) -> None:
    from app.database import Database

    database = Database(tmp_path / "cleanup-boundary.db")
    database.initialize()
    database.create_asset_record(
        "exact", "avatar-proxy", "key", "tos", "https://cdn/exact.png",
        bucket="test-bucket", object_key="exact.png", size_bytes=1,
    )
    database.create_asset_record(
        "newer", "avatar-proxy", "key", "tos", "https://cdn/newer.png",
        bucket="test-bucket", object_key="newer.png", size_bytes=1,
    )
    with database.connect() as connection:
        connection.execute("UPDATE asset_records SET created_at=datetime('now','-48 hours') WHERE record_id='exact'")
        connection.execute("UPDATE asset_records SET created_at=datetime('now','-48 hours','+1 second') WHERE record_id='newer'")

    candidates = database.cleanup_candidates(hours=48)
    assert [record["record_id"] for record in candidates] == ["exact"]


def test_external_url_delete_never_calls_tos_and_marks_deleted(tmp_path: Path, monkeypatch) -> None:
    class MustNotConstruct:
        def __init__(self, *args):
            raise AssertionError("TOS client must not be used for external URLs")

    monkeypatch.setattr("app.storage.tos.TosClientV2", MustNotConstruct)
    app = create_app(build_settings(tmp_path / "external.db"))
    with TestClient(app):
        app.state.database.create_asset_record(
            "external", "avatar-proxy", "key", "external_url", "https://example.com/image.png", status="active"
        )
        record = app.state.database.get_asset_record("external")
        assert asyncio.run(app.state.storage.delete_record_object(record)) is True
        deleted = app.state.database.get_asset_record("external")

    assert deleted["status"] == "deleted"
    assert deleted["deleted_at"] is not None


@pytest.mark.asyncio
async def test_maintenance_loop_logs_iteration_failure_and_remains_cancellable(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    from app.database import Database
    from app.quota import QuotaManager
    from app.storage import TosStorage

    database = Database(tmp_path / "maintenance.db")
    database.initialize()
    storage = TosStorage(build_settings(tmp_path / "maintenance.db"), database, QuotaManager(database))

    async def failed_cleanup() -> int:
        raise RuntimeError("cleanup failed")

    async def cancel_sleep(_: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(storage, "cleanup_once", failed_cleanup)
    monkeypatch.setattr("app.storage.asyncio.sleep", cancel_sleep)
    with pytest.raises(asyncio.CancelledError):
        await storage.maintenance_loop()
    assert "TOS cleanup maintenance failed" in caplog.text
