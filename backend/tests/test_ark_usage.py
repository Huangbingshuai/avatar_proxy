import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.main import create_app


ARK_KEY = "12345678-1234-1234-1234-123456789abc"
ARK_MASK = "123****89abc"
HYPHENATED_ARK_KEY = "ark-live-part-2c0ba9-e2dca"


def ark_headers(key: str = ARK_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_ark_usage_queries_key_suffix_and_returns_only_seedance(tmp_path: Path, settings_factory) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "ResponseMetadata": {"RequestId": "usage-request-1"},
                "Result": {
                    "Fields": [
                        {"Metric": "Day", "Values": ["2026-08-17", "2026-08-18"]},
                        {"Metric": "ModelName", "Values": ["doubao-seedance-2-5", "doubao-seed-2-0-pro"]},
                        {"Metric": "AuthToken", "Values": [ARK_MASK, ARK_MASK]},
                        {"Metric": "ReqCnt", "Values": ["2", "9"]},
                        {"Metric": "InputTokens", "Values": ["10", "90"]},
                        {"Metric": "OutputTokens", "Values": ["20", "90"]},
                        {"Metric": "TotalTokens", "Values": ["30", "180"]},
                        {"Metric": "VideoDurationSeconds", "Values": ["10", "0"]},
                    ],
                    "DataCount": 2,
                },
            },
        )

    app = create_app(settings_factory(tmp_path / "ark-usage.db"))
    with TestClient(app) as client:
        app.state.volcengine.transport = httpx.MockTransport(handler)
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-17", "end": "2026-08-18", "interval": "Day"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keySuffix"] == ARK_KEY[-12:]
    assert body["summary"] == {
        "inputTokens": 10,
        "outputTokens": 20,
        "totalTokens": 30,
        "requestCount": 2,
        "metrics": {"VideoDurationSeconds": 10},
    }
    assert body["records"] == [{
        "date": "2026-08-17",
        "modelName": "doubao-seedance-2-5",
        "requestCount": 2,
        "inputTokens": 10,
        "outputTokens": 20,
        "totalTokens": 30,
        "metrics": {"VideoDurationSeconds": 10},
    }]
    assert body["billingAmountIncluded"] is False
    assert body["upstreamRequestId"] == "usage-request-1"
    assert ARK_KEY not in response.text

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert request.url.host == "ark.cn-beijing.volcengineapi.com"
    assert request.url.params["Action"] == "GetInferenceUsage"
    assert request.headers["authorization"].startswith("HMAC-SHA256 ")
    upstream_body = json.loads(request.content)
    assert "ProjectName" not in upstream_body
    assert upstream_body == {
        "QueryInterval": "Day",
        "StartTime": "2026-08-17",
        "EndTime": "2026-08-18",
        "Filters": [
            {"Key": "ModelEndpoint", "Values": []},
            {"Key": "ModelName", "Values": []},
            {"Key": "ModelUnitID", "Values": []},
            {"Key": "AuthToken", "ValueLike": ARK_MASK, "Values": []},
            {"Key": "BillingStatus", "Values": []},
        ],
    }
    assert ARK_KEY not in request.content.decode("utf-8")


def test_ark_usage_accepts_object_and_encoded_records(tmp_path: Path, settings_factory) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "Result": {
                "Fields": [{"Metric": "Day"}, {"Metric": "ModelName"}, {"Metric": "ReqCnt"}],
                "Records": [
                    {"Day": "2026-08-18", "ModelName": "Seedance-custom", "ReqCnt": 1},
                    json.dumps({"Values": ["2026-08-18", "doubao-seedance-2-0", "2"]}),
                    "not-json",
                    7,
                ],
            },
        })

    app = create_app(settings_factory(tmp_path / "ark-record-shapes.db"))
    with TestClient(app) as client:
        app.state.volcengine.transport = httpx.MockTransport(handler)
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-18", "end": "2026-08-18"},
        )

    assert response.status_code == 200
    assert response.json()["summary"]["requestCount"] == 3
    assert len(response.json()["records"]) == 2


def test_ark_usage_masks_key_and_parses_real_data_shape(
    tmp_path: Path,
    settings_factory,
) -> None:
    expected_mask = "ark****e2dca"
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "ResponseMetadata": {"RequestId": "real-shape-request"},
            "Result": {
                "Fields": [
                    {"Name": "Day", "Type": "DATE"},
                    {"Name": "ModelName", "Type": "STRING"},
                    {"Name": "AuthToken", "Type": "STRING"},
                    {"Name": "OutputTokens", "Type": "BIGINT"},
                    {"Name": "TotalTokens", "Type": "BIGINT"},
                    {"Name": "ReqCnt", "Type": "BIGINT"},
                ],
                "Data": [[
                    "2026-08-17",
                    "doubao-seedance-2-5",
                    expected_mask,
                    "2830950",
                    "2830950",
                    "12",
                ]],
                "DataCount": 1,
            },
        })

    app = create_app(settings_factory(tmp_path / "ark-real-data.db"))
    with TestClient(app) as client:
        app.state.volcengine.transport = httpx.MockTransport(handler)
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(HYPHENATED_ARK_KEY),
            params={"start": "2026-08-05", "end": "2026-08-18"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keySuffix"] == HYPHENATED_ARK_KEY[-12:]
    assert body["summary"]["outputTokens"] == 2830950
    assert body["summary"]["totalTokens"] == 2830950
    assert body["summary"]["requestCount"] == 12
    assert body["records"][0]["modelName"] == "doubao-seedance-2-5"
    upstream_body = captured["body"]
    assert isinstance(upstream_body, dict)
    assert upstream_body["Filters"][3] == {
        "Key": "AuthToken",
        "ValueLike": expected_mask,
        "Values": [],
    }


def test_ark_usage_discards_non_matching_auth_token_records(tmp_path: Path, settings_factory) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "Result": {
                "Fields": [
                    {"Metric": "Day"},
                    {"Metric": "ModelName"},
                    {"Metric": "AuthToken"},
                    {"Metric": "TotalTokens"},
                    {"Metric": "ReqCnt"},
                ],
                "Records": [
                    ["2026-08-18", "doubao-seedance-2-5", ARK_MASK, "30", "1"],
                    ["2026-08-18", "doubao-seedance-2-5", "different-token", "999", "9"],
                ],
            }
        })

    app = create_app(settings_factory(tmp_path / "ark-token-defense.db"))
    with TestClient(app) as client:
        app.state.volcengine.transport = httpx.MockTransport(handler)
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-18", "end": "2026-08-18"},
        )

    assert response.status_code == 200
    assert response.json()["summary"]["totalTokens"] == 30
    assert response.json()["summary"]["requestCount"] == 1


def test_ark_usage_requires_ark_key_and_valid_date_range(tmp_path: Path, settings_factory) -> None:
    app = create_app(settings_factory(tmp_path / "ark-validation.db"))
    with TestClient(app) as client:
        missing = client.get(
            "/api/video/ark-usage", params={"start": "2026-08-01", "end": "2026-08-18"}
        )
        malformed = client.get(
            "/api/video/ark-usage",
            headers=ark_headers("short key"),
            params={"start": "2026-08-01", "end": "2026-08-18"},
        )
        reversed_range = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-18", "end": "2026-08-01"},
        )
        too_large = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-06-01", "end": "2026-08-18"},
        )

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "missing_ark_api_key"
    assert malformed.status_code == 401
    assert malformed.json()["error"]["code"] == "invalid_ark_api_key"
    assert reversed_range.status_code == 400
    assert reversed_range.json()["error"]["code"] == "invalid_usage_date_range"
    assert too_large.status_code == 400
    assert too_large.json()["error"]["code"] == "usage_date_range_too_large"


def test_ark_usage_returns_zero_for_key_without_usage(tmp_path: Path, settings_factory) -> None:
    app = create_app(settings_factory(tmp_path / "ark-empty.db"))
    with TestClient(app) as client:
        app.state.volcengine.transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"Result": {"Fields": [], "Records": [], "DataCount": 0}})
        )
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-18", "end": "2026-08-18"},
        )

    assert response.status_code == 200
    assert response.json()["records"] == []
    assert response.json()["summary"] == {
        "inputTokens": 0,
        "outputTokens": 0,
        "totalTokens": 0,
        "requestCount": 0,
        "metrics": {},
    }


def test_ark_usage_maps_upstream_failures_without_leaking_key(tmp_path: Path, settings_factory) -> None:
    cases = [
        (403, "AccessDenied", "ark_usage_permission_denied", 503),
        (429, "RequestLimitExceeded", "ark_usage_rate_limited", 503),
        (400, "InvalidParameter.Filters", "ark_usage_query_failed", 502),
    ]
    for upstream_status, upstream_code, code, expected_status in cases:
        app = create_app(settings_factory(tmp_path / f"ark-error-{upstream_status}.db"))
        with TestClient(app) as client:
            app.state.volcengine.transport = httpx.MockTransport(
                lambda _, status=upstream_status, error_code=upstream_code: httpx.Response(
                    status,
                    headers={"retry-after": "30"},
                    json={
                        "ResponseMetadata": {
                            "RequestId": f"request-{status}",
                            "Error": {"Code": error_code, "Message": ARK_KEY},
                        }
                    },
                )
            )
            response = client.get(
                "/api/video/ark-usage",
                headers=ark_headers(),
                params={"start": "2026-08-18", "end": "2026-08-18"},
            )

        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["upstreamCode"] == upstream_code
        assert response.json()["error"]["upstreamRequestId"] == f"request-{upstream_status}"
        assert ARK_KEY not in response.text
        if upstream_status == 429:
            assert response.headers["retry-after"] == "30"


def test_ark_usage_maps_error_envelope_even_when_upstream_returns_http_200(
    tmp_path: Path,
    settings_factory,
) -> None:
    app = create_app(settings_factory(tmp_path / "ark-error-envelope.db"))
    with TestClient(app) as client:
        app.state.volcengine.transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "ResponseMetadata": {
                        "RequestId": "error-envelope-request",
                        "Error": {
                            "Code": "InvalidParameter.Filters",
                            "Message": f"invalid filter {ARK_KEY}",
                        },
                    }
                },
            )
        )
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-18", "end": "2026-08-18"},
        )

    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "ark_usage_query_failed",
        "message": "火山方舟拒绝了用量查询",
        "upstreamCode": "InvalidParameter.Filters",
        "upstreamRequestId": "error-envelope-request",
    }
    assert ARK_KEY not in response.text


def test_ark_usage_rejects_missing_server_credentials(tmp_path: Path, settings_factory) -> None:
    app = create_app(settings_factory(
        tmp_path / "ark-no-credentials.db",
        volcengine_access_key="",
        volcengine_secret_key="",
    ))
    with TestClient(app) as client:
        response = client.get(
            "/api/video/ark-usage",
            headers=ark_headers(),
            params={"start": "2026-08-18", "end": "2026-08-18"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_credentials_missing"
