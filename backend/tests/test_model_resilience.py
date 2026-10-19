"""Slow/failed providers are simulated; no paid or external requests."""
import asyncio
import json

import httpx
import pytest

from app.errors import ApiError
from app.security import ApiPrincipal
from test_provider_relay import provision, relay_client


IMAGE = {"model": "gpt-image-2", "prompt": "a circle", "quality": "low", "n": 1}
OUTPUT = {"data": [{"url": "https://example.com/image.png"}], "usage": {"total_tokens": 12}}


def setup_image(client):
    key_id, key, _ = provision(client, provider="modeltop", alias="gpt-image-2", upstream_model="ignored")
    return ApiPrincipal(key_id, "relay_project"), {"Authorization": "Bearer " + key, "Idempotency-Key": "one-image"}


@pytest.mark.parametrize("provider,alias,size", [
    ("modeltop", "gpt-image-2", "1024x1024"),
    ("volcengine_ark", "doubao-seedream-5.0-pro", "1K"),
    ("byteplus_modelark", "dola-seedream-5.0-pro", "1K"),
    ("maxmodel", "gpt-image-2", "1024x1024"),
])
def test_slow_generation_ignores_legacy_30_seconds_and_caches(tmp_path, provider, alias, size):
    calls = []
    with relay_client(tmp_path, upstream_timeout_seconds=30) as client:
        _, key, _ = provision(client, provider=provider, alias=alias, upstream_model="ignored")
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "one-slow-image"}
        payload = {"model":alias, "prompt":"a circle", "n":1, "size":size}
        def handler(request):
            calls.append(request)
            assert json.loads(request.content)["size"] == size
            timeout = request.extensions["timeout"]
            assert timeout == {"connect": 10.0, "read": 1800.0, "write": 120.0, "pool": 10.0}
            # Simulate a provider that cannot finish inside the old 30s window.
            if timeout["read"] <= 30:
                raise httpx.ReadTimeout("slow generation", request=request)
            envelope = {"code":200, "data":OUTPUT} if provider=="maxmodel" else OUTPUT
            return httpx.Response(200, json=envelope)
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        first = client.post("/v1/images/generations", json=payload, headers=headers)
        second = client.post("/v1/images/generations", json=payload, headers=headers)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert len(calls) == 1


@pytest.mark.parametrize("exception,status,phase,uncertain", [
    (httpx.ReadTimeout,504,"read",True), (httpx.WriteTimeout,504,"write",True),
    (httpx.ConnectTimeout,504,"connect",False), (httpx.PoolTimeout,504,"pool",False),
    (httpx.ConnectError,502,"connect",False), (httpx.ReadError,502,"read",True),
    (httpx.RemoteProtocolError,502,"read",True),
])
def test_errors_are_classified_redacted_never_retried_or_zero_billed(tmp_path, exception, status, phase, uncertain):
    calls = []
    with relay_client(tmp_path) as client:
        _, headers = setup_image(client)
        def handler(request):
            calls.append(request)
            raise exception("secret-provider-key must never appear", request=request)
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        first = client.post("/v1/images/generations", json=IMAGE, headers=headers)
        assert first.status_code == status
        details = first.json()["error"]["details"]
        assert details == {"phase":phase, "outcomeUnknown":uncertain, "automaticRetry":False}
        assert "secret-provider-key" not in first.text
        second = client.post("/v1/images/generations", json=IMAGE, headers=headers)
        assert second.status_code == 409
        assert len(calls) == 1
        with client.app.state.database.connect() as c:
            usage = c.execute("SELECT status,total_tokens,generated_images FROM inference_usage").fetchall()
            assert len(usage) == int(uncertain)
            if uncertain:
                assert tuple(usage[0]) == ("unknown",None,None)
            logged = c.execute("SELECT response_summary_json FROM request_logs WHERE status_code=?",(status,)).fetchone()[0]
            assert "secret-provider-key" not in logged


def test_client_disconnect_does_not_cancel_paid_image_and_cached_result_is_recoverable(tmp_path):
    with relay_client(tmp_path, model_image_max_inflight=1) as client:
        principal, headers = setup_image(client)
        relay = client.app.state.provider_relay
        calls = []
        async def run():
            entered, release = asyncio.Event(), asyncio.Event()
            async def handler(request):
                calls.append(request)
                entered.set()
                await release.wait()
                return httpx.Response(200,json=OUTPUT)
            relay.transport = httpx.MockTransport(handler)
            waiting_client = asyncio.create_task(relay.generate_image(principal,"gpt-image-2",IMAGE,"one-image"))
            await entered.wait()
            waiting_client.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting_client
            assert len(relay._image_jobs) == 1
            with pytest.raises(ApiError) as full:
                await relay.generate_image(principal,"gpt-image-2",IMAGE,"another-paid-request")
            assert full.value.code == "model_capacity_exceeded" and full.value.headers["Retry-After"] == "10"
            with pytest.raises(ApiError) as busy:
                await relay.generate_image(principal,"gpt-image-2",IMAGE,"one-image")
            assert busy.value.code == "idempotency_request_in_progress"
            release.set()
            await asyncio.gather(*relay._image_jobs)
        asyncio.run(run())
        recovered = client.post("/v1/images/generations",json=IMAGE,headers=headers)
        assert recovered.status_code == 200 and recovered.json()["data"] == OUTPUT["data"]
        assert len(calls) == 1
        with client.app.state.database.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 1


def test_shutdown_marks_result_unknown_and_restart_recovery_is_idempotent(tmp_path):
    with relay_client(tmp_path) as client:
        principal, headers = setup_image(client)
        relay = client.app.state.provider_relay
        async def run():
            entered = asyncio.Event()
            async def handler(_):
                entered.set()
                await asyncio.Event().wait()
            relay.transport = httpx.MockTransport(handler)
            waiter = asyncio.create_task(relay.generate_image(principal,"gpt-image-2",IMAGE,"one-image"))
            await entered.wait()
            await relay.aclose()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        asyncio.run(run())
        route = relay.resolve(principal,"gpt-image-2")
        relay._create_task(principal,route,"image",IMAGE,"interrupted-on-restart")
        relay.recover_interrupted_images()
        relay.recover_interrupted_images()
        with client.app.state.database.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM inference_usage WHERE status='unknown'").fetchone()[0] == 2
            assert c.execute("SELECT COUNT(*) FROM inference_tasks WHERE status IN ('queued','running')").fetchone()[0] == 0
        replay = client.post("/v1/images/generations",json=IMAGE,headers=headers)
        assert replay.status_code == 409 and replay.json()["error"]["code"] == "idempotency_outcome_unknown"


def test_polling_and_stream_have_separate_timeouts_and_stream_errors_are_sse(tmp_path):
    with relay_client(tmp_path,model_stream_idle_timeout_seconds=240) as client:
        key_id, key, _ = provision(client,provider="volcengine_ark",alias="glm-5.2",upstream_model="ignored")
        relay = client.app.state.provider_relay
        route = relay.resolve(ApiPrincipal(key_id,"relay_project"),"glm-5.2")
        def handler(request):
            if request.method == "GET":
                assert request.extensions["timeout"]["read"] == 30
                return httpx.Response(200,json={})
            assert request.extensions["timeout"]["read"] == 240
            raise httpx.ReadTimeout("private-key",request=request)
        relay.transport = httpx.MockTransport(handler)
        asyncio.run(relay._request(route,"GET","/models"))
        response = client.post("/v1/chat/completions",json={"model":"glm-5.2","messages":[],"stream":True},headers={"Authorization":"Bearer "+key})
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        assert "provider_response_timeout" in response.text and "private-key" not in response.text


def test_timeout_settings_are_bounded(tmp_path):
    from conftest import build_settings
    from pydantic import ValidationError
    for name, value in [("model_generation_timeout_seconds",0),("model_generation_timeout_seconds",3601),
                        ("model_connect_timeout_seconds",0),("model_stream_idle_timeout_seconds",-1)]:
        with pytest.raises(ValidationError):
            build_settings(tmp_path / "config.db",**{name:value})


def test_unknown_generation_is_pending_billing_not_free(tmp_path):
    from app.billing import current_month
    with relay_client(tmp_path) as client:
        principal, _ = setup_image(client)
        relay = client.app.state.provider_relay
        route = relay.resolve(principal,"gpt-image-2")
        relay._record_usage(request_id="unconfirmed",principal=principal,route=route,status="unknown")
        with client.app.state.database.connect() as c:
            c.execute("INSERT INTO project_billing_terms(id,project_name,effective_month,enabled,discount_bps,updated_by) VALUES (?,?,?,1,10000,'test')",
                      ("enabled-for-test",principal.project_name,current_month()))
        asyncio.run(client.app.state.billing.reconcile())
        with client.app.state.database.connect() as c:
            row = c.execute("SELECT status,pending_reason,list_amount_micros,net_amount_micros FROM billing_usage_items").fetchone()
            assert tuple(row) == ("pending","provider_outcome_unknown",None,None)


def test_all_model_operations_use_execution_or_metadata_policy(tmp_path):
    from dataclasses import replace
    with relay_client(tmp_path,model_generation_timeout_seconds=900) as client:
        principal, _ = setup_image(client)
        relay = client.app.state.provider_relay
        base = relay.resolve(principal,"gpt-image-2")
        async def exercise():
            for modality, method, path, expected in [
                ("image","POST","/images/generations",900),
                ("text","POST","/chat/completions",900),
                ("text","POST","/responses",900),
                ("audio","POST","/audio/generations",900),
                ("video","POST","/contents/generations/tasks",900),
                ("video","GET","/contents/generations/tasks/id",30),
                ("embedding","POST","/embeddings",30),
            ]:
                def handler(request):
                    assert request.extensions["timeout"]["read"] == expected
                    return httpx.Response(200,json={})
                relay.transport = httpx.MockTransport(handler)
                await relay._request(replace(base,modality=modality),method,path,{})
        asyncio.run(exercise())
