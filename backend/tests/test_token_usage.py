import math
import sqlite3

import pytest

from app.security import ApiPrincipal
from app.token_usage import COMPLETE_TOKENS_SQL, KNOWN_TOKENS_SQL, token_count, token_summary
from test_provider_relay import relay_client
from test_vega import setup


@pytest.mark.parametrize("value,expected", [
    (None, None), (True, None), (False, None), ("12", None), ({}, None),
    (-1, None), (0, 0), (12, 12), (12.0, 12), (1.5, None),
    (math.nan, None), (math.inf, None), (2**63, None),
])
def test_token_counts_never_truncate_or_invent_values(value, expected):
    assert token_count(value) == expected


@pytest.mark.parametrize("incoming,outgoing,total,known,complete", [
    (None, None, None, None, False),
    (0, None, None, 0, False),
    (None, 19, None, 19, False),
    (11, None, None, 11, False),
    (0, 118800, None, 118800, True),
    (100, 30, None, 130, True),
    (10, 20, 40, 40, True),
    (10, 20, 0, 0, True),
    (-1, 9, -5, 9, False),
])
def test_sql_and_usage_api_agree_without_overwriting_missing_totals(incoming, outgoing, total, known, complete):
    assert token_summary(incoming, outgoing, total) == (known, complete)
    with sqlite3.connect(":memory:") as connection:
        actual = connection.execute(
            f"SELECT {KNOWN_TOKENS_SQL},{COMPLETE_TOKENS_SQL} "
            "FROM (SELECT ? AS input_tokens,? AS output_tokens,? AS total_tokens)",
            (incoming, outgoing, total),
        ).fetchone()
    assert actual == (known, int(complete))


def test_overview_reads_historical_components_without_backfill_or_double_counting(tmp_path):
    with relay_client(tmp_path) as client:
        key_id, _, _ = setup(client)
        relay = client.app.state.provider_relay
        principal = ApiPrincipal(key_id, "vega_project")
        route = relay.resolve(principal, "vega-1.0-pro")
        samples = [
            {"input_tokens": 0, "completion_tokens": 118800},
            {"input_tokens": 0, "completion_tokens": 318000},
            {"input_tokens": 0, "completion_tokens": 475200},
            {}, {"input_tokens": 0}, {"input_tokens": 7},
            {"input_tokens": 10, "completion_tokens": 20, "total_tokens": 40},
            {"prompt_tokens": 100, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 20}},
            {"input_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        ]
        for index, usage in enumerate(samples):
            relay._record_usage(request_id=f"tokens-{index}", principal=principal, route=route, status="succeeded", usage=usage)
        relay._record_usage(request_id="failed", principal=principal, route=route, status="failed", usage={"total_tokens": 999})
        with relay.database.connect() as connection:
            connection.execute("INSERT INTO video_usage(api_key_id,project_name,task_id,model,total_tokens) VALUES (?,?,?,?,?)",
                               (key_id, "vega_project", "legacy-video", "legacy", 9))
            before = [tuple(r) for r in connection.execute("SELECT input_tokens,output_tokens,total_tokens FROM inference_usage ORDER BY id")]
        for _ in range(2):
            stats = relay.database.overview()["stats"]
            assert stats["modelCalls"] == 10
            assert stats["tokenUsage"] == 912186
            assert stats["tokenUsageIncompleteCalls"] == 3
        with relay.database.connect() as connection:
            assert before == [tuple(r) for r in connection.execute("SELECT input_tokens,output_tokens,total_tokens FROM inference_usage ORDER BY id")]
        usage = relay.usage(project_name="vega_project", key_id=None, model=None, provider=None, start=None, end=None, limit=100)
        by_request = {item["requestId"]: item for item in usage}
        assert by_request["tokens-0"]["totalTokens"] is None
        assert by_request["tokens-0"]["knownTokens"] == 118800
        assert by_request["tokens-0"]["tokenUsageComplete"] is True
        assert by_request["tokens-3"]["knownTokens"] is None
        assert by_request["tokens-3"]["tokenUsageComplete"] is False
        assert by_request["tokens-4"]["knownTokens"] == 0
        assert by_request["tokens-4"]["tokenUsageComplete"] is False


def test_invalid_provider_counts_remain_null_and_are_not_reported_as_free(tmp_path):
    with relay_client(tmp_path) as client:
        key_id, _, _ = setup(client)
        relay = client.app.state.provider_relay
        principal = ApiPrincipal(key_id, "vega_project")
        relay._record_usage(request_id="invalid-counts", principal=principal,
                            route=relay.resolve(principal, "vega-1.0-pro"), status="succeeded",
                            usage={"prompt_tokens": True, "completion_tokens": -10,
                                   "total_tokens": 1.5, "cached_input_tokens": math.inf})
        with relay.database.connect() as connection:
            row = connection.execute("SELECT input_tokens,cached_input_tokens,output_tokens,total_tokens FROM inference_usage").fetchone()
            assert tuple(row) == (None, None, None, None)
        assert relay.database.overview()["stats"]["tokenUsageIncompleteCalls"] == 1
