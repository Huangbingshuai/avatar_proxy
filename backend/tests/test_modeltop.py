"""ModelTop protocol and pricing tests: temporary SQLite and MockTransport only."""
import asyncio
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.billing import BillingManager, current_month, normalize_resolution
from app.database import Database, SCHEMA
from app.errors import ApiError
from app.modeltop import (MODELTOP_FX, MODELTOP_IMAGE_IDS, MODELTOP_MODEL_CATALOG,
                          MODELTOP_RATES, MODELTOP_VIDEO_IDS, image_token_measurements, modeltop_cny, modeltop_alias)
from app.security import ApiPrincipal
from conftest import create_key, create_project
from test_provider_relay import provision, relay_client
from test_billing import SUPER_ACTOR

TASKS = "/api/v3/contents/generations/tasks"


@pytest.mark.parametrize("model", MODELTOP_IMAGE_IDS)
def test_images_protocol_real_usage_billing_idempotency_logs(tmp_path, model):
    calls = []
    usage = {"input_tokens": 222, "input_tokens_details": {"text_tokens": 28, "image_tokens": 194},
             "output_tokens": 4160, "output_tokens_details": {"image_tokens": 4160}, "total_tokens": 4382}
    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://modeltop.ai/v1/images/generations"
        assert request.headers["authorization"] == "Bearer secret-modeltop-abcdefgh"
        payload = json.loads(request.content)
        assert payload == {"model": model, "prompt": "a cup", "n": 1, "size": "auto", "quality": "auto"}
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": "aW1hZ2U="}], "usage": usage})
    alias = modeltop_alias(model)
    with relay_client(tmp_path) as client:
        key_id, key, channel = provision(client, provider="modeltop", alias=alias, upstream_model="not-client-controlled")
        client.app.state.provider_relay.transport = httpx.MockTransport(handler)
        headers = {"Authorization": "Bearer " + key, "Idempotency-Key": "image-once"}
        payload = {"model": alias, "prompt": "a cup", "n": 1, "response_format": "b64_json"}
        response = client.post("/v1/images/generations", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["model"] == alias and response.json()["data"][0]["b64_json"]
        assert client.post("/v1/images/generations", json=payload, headers=headers).json() == response.json()
        assert client.post("/v1/images/generations", json={**payload, "prompt": "other"}, headers=headers).status_code == 409
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 1
            assert connection.execute("SELECT generated_images,input_tokens,output_tokens FROM inference_usage").fetchone()[:] == (1,222,4160)
            row = dict(connection.execute("SELECT u.*,m.modality,c.provider,t.metadata_json FROM inference_usage u JOIN model_catalog m ON m.alias=u.model_alias JOIN provider_channels c ON c.id=u.channel_id JOIN inference_tasks t ON t.id=u.task_id").fetchone())
            log = connection.execute("SELECT request_params_json,response_summary_json FROM request_logs WHERE path='/v1/images/generations' AND status_code=200 AND log_type='http' LIMIT 1").fetchone()
            assert json.loads(log[0])["body"] == payload
            assert json.loads(log[1])["body"]["usage"] == usage
            assert key not in log[0] + log[1] and "secret-modeltop" not in log[0] + log[1]
        measured, reason = client.app.state.billing._relay_measurements(row)
        assert reason is None and measured == [("input_tokens","modeltop:text",Decimal(28)),("input_tokens","modeltop:image",Decimal(194)),("output_tokens","modeltop:image",Decimal(4160))]
        rate = client.get("/v1/pricing",params={"model":alias},headers=headers).json()["data"][0]
        assert rate["currency"] == "CNY" and rate["prices"]
        internal = client.app.state.billing.get_rate(alias,current_month(),"modeltop")
        assert internal["officialSource"]["fxRateToCny"] == str(MODELTOP_FX)
        assert {r["dimension"] for r in internal["rules"]} >= {"text", "image"}
    assert len(calls) == 1


@pytest.mark.parametrize("model", MODELTOP_VIDEO_IDS)
def test_videos_pinned_key_idempotency_ownership_settlement(tmp_path, model):
    alias = modeltop_alias(model)
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer secret-modeltop-abcdefgh"
        if request.method == "POST":
            assert str(request.url) == "https://modeltop.ai/api/v3/contents/generations/tasks"
            payload=json.loads(request.content)
            assert payload["model"] == model and payload["duration"] == 4
            return httpx.Response(200,json={"id":"upstream-one"})
        assert str(request.url) == "https://modeltop.ai/api/v3/contents/generations/tasks/upstream-one"
        return httpx.Response(200,json={"status":"succeeded","duration":4,"resolution":"480p","content":{"video_url":"https://example.com/video.mp4"},"usage":{"completion_tokens":40000,"total_tokens":40000}})
    with relay_client(tmp_path) as client:
        key_id,key,channel=provision(client,provider="modeltop",alias=alias,upstream_model="ignored")
        relay=client.app.state.provider_relay
        relay.transport=httpx.MockTransport(handler)
        headers={"Authorization":"Bearer "+key,"Idempotency-Key":"video-once"}
        payload={"model":alias,"content":[{"type":"text","text":"a boat"}],"duration":4,"resolution":"480p"}
        response=client.post(TASKS,json=payload,headers=headers)
        assert response.status_code==200,response.text
        task_id=response.json()["id"]
        assert client.post(TASKS,json=payload,headers=headers).json()==response.json()
        relay.rotate_channel_secret(channel["id"],"rotated-secret-modeltop","owner")
        relay.set_channel_status(channel["id"],False)
        assert client.get("/v1/models",headers=headers).json()["data"]==[]
        _,other=create_key(client,"relay_project","other")
        assert client.get(TASKS+"/"+task_id,headers={"Authorization":"Bearer "+other}).status_code==404
        done=client.get(TASKS+"/"+task_id,headers=headers)
        assert done.status_code==200 and done.json()["status"]=="succeeded"
        assert done.json()["model"]==alias and done.json()["usage"]["completion_tokens"]==40000
        assert client.get(TASKS+"/"+task_id,headers=headers).status_code==200
        assert client.delete(TASKS+"/"+task_id,headers=headers).status_code==422
        with client.app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0]==1
            row=dict(connection.execute("SELECT u.*,m.modality,c.provider,t.metadata_json,t.billing_metadata_json FROM inference_usage u JOIN model_catalog m ON m.alias=u.model_alias JOIN provider_channels c ON c.id=u.channel_id JOIN inference_tasks t ON t.id=u.task_id").fetchone())
        measured,reason=client.app.state.billing._relay_measurements(row)
        assert reason is None and measured==[("output_tokens","modeltop:480p:no_video",Decimal(40000))]
    assert len(calls)==2


@pytest.mark.parametrize("extra,code", [
    ({"size":[]},"image_size_invalid"),({"size":"16x16"},"image_size_invalid"),
    ({"quality":"impossible"},"image_quality_invalid"),({"quality":[]},"image_quality_invalid"),
    ({"background":[]},"image_parameter_unsupported"),({"background":"transparent","output_format":"jpeg"},"image_output_format_unsupported"),
    ({"output_format":[]},"image_output_format_unsupported"),({"output_compression":30},"image_parameter_unsupported"),
    ({"output_format":"jpeg","output_compression":True},"image_parameter_unsupported"),
    ({"watermark":True},"image_parameter_unsupported"),({"n":11},"image_count_unsupported"),
    ({"image":"https://example.com/a.png"},"model_image_input_unsupported"),({"stream":True},"image_stream_unsupported"),
])
def test_invalid_image_parameters_no_upstream(tmp_path,extra,code):
    with relay_client(tmp_path) as client:
        _,key,_=provision(client,provider="modeltop",alias="gpt-image-2.5-flare",upstream_model="ignored")
        client.app.state.provider_relay.transport=httpx.MockTransport(lambda r:pytest.fail("must not call upstream"))
        response=client.post("/v1/images/generations",json={"model":"gpt-image-2.5-flare","prompt":"a cup",**extra},headers={"Authorization":"Bearer "+key})
        assert response.status_code==422 and response.json()["error"]["code"]==code


def test_image_custom_size_and_token_cache_safety(tmp_path):
    with relay_client(tmp_path) as client:
        key_id,_,_=provision(client,provider="modeltop",alias="gpt-image-2.5-flare",upstream_model="ignored")
        relay=client.app.state.provider_relay
        route=relay.resolve(ApiPrincipal(key_id,"relay_project"),"gpt-image-2.5-flare")
        body=relay._image_upstream_payload(route,{"prompt":"cup","size":"1280x720","quality":"max","background":"transparent","output_format":"webp","output_compression":40})
        assert body["quality"]=="max" and body["output_compression"]==40
    usage={"input_tokens":100,"input_tokens_details":{"text_tokens":80,"image_tokens":20,"cached_tokens":10},"output_tokens_details":{"image_tokens":500}}
    assert image_token_measurements(usage)==(None,"cached_input_split_unknown")
    usage["input_tokens_details"]["cached_tokens_details"]={"text_tokens":8,"image_tokens":2}
    measured,reason=image_token_measurements(usage)
    assert reason is None and measured[0][2]==72 and measured[1][2]==18 and measured[-1][2]==10
    assert image_token_measurements({})==(None,"usage_unknown")
    usage["input_tokens"]=99
    assert image_token_measurements(usage)==(None,"usage_invalid")


def test_modeltop_upgrade_isolated_rates_and_channel_constraints(tmp_path):
    path=tmp_path/"upgrade.db"
    old=SCHEMA.replace("'modeltop',", "")
    with sqlite3.connect(path) as c:
        c.executescript(old)
        c.execute("INSERT INTO projects(name,display_name) VALUES ('old','Old')")
        c.execute("INSERT INTO provider_channels(id,project_name,name,provider) VALUES ('old','old','Old','byteplus_modelark')")
    database=Database(path)
    database.initialize()
    with database.connect() as c:
        count=c.execute("SELECT COUNT(*) FROM billing_model_rates").fetchone()[0]
        c.execute("UPDATE billing_model_rates SET unit_price_micros=123 WHERE model_alias='gpt-image-2' AND metric='output_tokens'")
    database.initialize()
    with database.connect() as c:
        assert c.execute("SELECT provider FROM provider_channels WHERE id='old'").fetchone()[0]=="byteplus_modelark"
        assert c.execute("SELECT COUNT(*) FROM model_catalog WHERE provider='modeltop'").fetchone()[0]==6
        assert c.execute("SELECT COUNT(*) FROM project_model_bindings").fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM billing_model_rates").fetchone()[0]==count
        assert c.execute("SELECT unit_price_micros FROM billing_model_rates WHERE model_alias='gpt-image-2' AND metric='output_tokens'").fetchone()[0]==123
        assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok" and c.execute("PRAGMA foreign_key_check").fetchall()==[]
    assert modeltop_cny("30")==Decimal("201.194820")
    assert normalize_resolution("4K")=="4k"
    assert MODELTOP_RATES["dreamina-seedance-2.0"][-2][1]=="modeltop:4k:no_video"


@pytest.mark.parametrize("kind", ["error", "empty"])
def test_image_failure_does_not_settle(tmp_path,kind):
    with relay_client(tmp_path) as client:
        _,key,_=provision(client,provider="modeltop",alias="gpt-image-2",upstream_model="ignored")
        client.app.state.provider_relay.transport=httpx.MockTransport(lambda r:httpx.Response(403,json={"message":"insufficient credits"}) if kind=="error" else httpx.Response(200,json={"data":[{"error":{"code":"blocked"}}]}))
        response=client.post("/v1/images/generations",headers={"Authorization":"Bearer "+key},json={"model":"gpt-image-2","prompt":"a cup"})
        assert response.status_code in {403,502}
        with client.app.state.database.connect() as c:
            assert c.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0]==0
            assert c.execute("SELECT status FROM inference_tasks").fetchone()[0]=="failed"


def test_same_model_switches_channel_price_and_capabilities_without_duplicate_alias(tmp_path):
    with relay_client(tmp_path) as client:
        key_id,key,channel=provision(client,provider="modeltop",alias="gpt-image-2",upstream_model="ignored")
        relay=client.app.state.provider_relay
        billing=client.app.state.billing
        month=current_month()
        rules=billing.get_rate("gpt-image-2",month)["rules"]
        billing.set_rate("gpt-image-2",month,{"rules":rules+[{"metric":"image","dimension":"","unitSize":1,"unitPriceYuan":"0.300000"}]},SUPER_ACTOR)
        billing.set_project_terms("relay_project",month,True,10000,SUPER_ACTOR)
        listed=relay.project_models("relay_project")
        model=next(m for m in listed if m["model"]=="gpt-image-2")
        assert model["providers"]==["maxmodel","modeltop"]
        assert sum(m["id"]=="gpt-image-2" for m in relay.catalog())==1
        calls=[]
        def handler(request):
            calls.append(request)
            data={"data":[{"url":"https://example.com/a.png"}]}
            if request.url.host=="modeltop.ai":
                data["usage"]={"input_tokens":10,"input_tokens_details":{"text_tokens":10,"image_tokens":0},"output_tokens":100,"output_tokens_details":{"image_tokens":100},"total_tokens":110}
                return httpx.Response(200,json=data)
            assert request.url.host=="aiapi.maxmaas.com"
            return httpx.Response(200,json={"code":200,"data":data})
        relay.transport=httpx.MockTransport(handler)
        headers={"Authorization":"Bearer "+key}
        prices=client.get("/v1/pricing?model=gpt-image-2",headers=headers).json()["data"][0]
        assert prices["provider"]=="modeltop" and all(p["metric"]!="image" for p in prices["prices"])
        assert all(not str(p["dimension"]).startswith("modeltop:") for p in prices["prices"])
        assert client.post("/v1/images/generations",json={"model":"gpt-image-2","prompt":"cup"},headers={**headers,"Idempotency-Key":"on-modeltop"}).status_code==200
        maxmodel=relay.create_channel(project_name="relay_project",name="other",provider="maxmodel",config={},secret="maxmodel-test-key",actor_id="owner")
        relay.set_project_models("relay_project",[{"model":"gpt-image-2","channelId":maxmodel["id"],"enabled":True}],"admin")
        assert relay.resolve(ApiPrincipal(key_id,"relay_project"),"gpt-image-2").provider=="maxmodel"
        prices=client.get("/v1/pricing?model=gpt-image-2",headers=headers).json()["data"][0]
        assert prices["provider"]=="maxmodel" and len(prices["prices"])==1 and prices["prices"][0]["metric"]=="image"
        assert client.post("/v1/images/generations",json={"model":"gpt-image-2","prompt":"cup"},headers={**headers,"Idempotency-Key":"on-maxmodel"}).status_code==200
        asyncio.run(billing.reconcile("relay_project",month))
        with client.app.state.database.connect() as c:
            components=c.execute("SELECT metric,resolution,net_amount_micros FROM billing_usage_components ORDER BY resolution").fetchall()
            assert ("image","",300000) in [tuple(x) for x in components]
            assert ("output_tokens","modeltop:image",20119) in [tuple(x) for x in components]
            assert c.execute("SELECT COUNT(*) FROM billing_usage_items WHERE status='rated'").fetchone()[0]==2
        assert len(calls)==2


def test_old_video_remains_on_modeltop_after_switching_to_byteplus(tmp_path):
    with relay_client(tmp_path) as client:
        _,key,channel=provision(client,provider="modeltop",alias="dreamina-seedance-2.5",upstream_model="ignored")
        relay=client.app.state.provider_relay
        calls=[]
        def handler(request):
            calls.append(request)
            assert request.url.host=="modeltop.ai"
            assert request.headers["authorization"]=="Bearer secret-modeltop-abcdefgh"
            if request.method=="POST":return httpx.Response(200,json={"id":"pinned"})
            return httpx.Response(200,json={"status":"succeeded","duration":4,"resolution":"480p","content":{"video_url":"https://example.com/a.mp4"},"usage":{"completion_tokens":40000}})
        relay.transport=httpx.MockTransport(handler)
        headers={"Authorization":"Bearer "+key}
        task=client.post(TASKS,json={"model":"dreamina-seedance-2.5","duration":4,"content":[{"type":"text","text":"cup"}]},headers=headers).json()["id"]
        byteplus=relay.create_channel(project_name="relay_project",name="byteplus",provider="byteplus_modelark",config={},secret="byteplus-secret",actor_id="owner")
        relay.set_project_models("relay_project",[{"model":"dreamina-seedance-2.5","channelId":byteplus["id"],"enabled":True}],"admin")
        assert next(m for m in relay.project_models("relay_project") if m["model"]=="dreamina-seedance-2.5")["upstreamModel"]=="dreamina-seedance-2-5-260628"
        assert client.get(TASKS+"/"+task,headers=headers).json()["status"]=="succeeded"
        assert len(calls)==2


@pytest.mark.parametrize("details,expected",[
    ({"text_tokens":10,"image_tokens":0,"cached_tokens":4},None),
    ({"text_tokens":0,"image_tokens":10,"cached_tokens":4},None),
    ({"text_tokens":10,"image_tokens":0,"cached_tokens":11},"usage_invalid"),
    ({"text_tokens":10,"image_tokens":0,"cached_tokens":None},"usage_unknown"),
    ({"text_tokens":True,"image_tokens":0},"usage_unknown"),
    ({"text_tokens":8,"image_tokens":2,"cached_tokens":4,"cached_tokens_details":{}},"cached_input_split_unknown"),
    ({"text_tokens":8,"image_tokens":2,"cached_tokens":4,"cached_tokens_details":{"text_tokens":4,"image_tokens":1}},"usage_invalid"),
])
def test_image_cache_and_unknown_usage_details(details,expected):
    result,reason=image_token_measurements({"input_tokens":10,"input_tokens_details":details,"output_tokens_details":{"image_tokens":100}})
    assert reason==expected
    if expected is None:assert result[-1]==("cached_input_tokens","",Decimal(4))


@pytest.mark.parametrize("modality,extra,reason",[
    ("text",{"input_tokens":None},"usage_unknown"),
    ("text",{"cached_input_tokens":-1},"usage_invalid"),
    ("text",{"cached_input_tokens":1001},"usage_invalid"),
    ("text",{"cached_input_tokens":30},None),
    ("text",{"model_alias":"doubao-seed-2.0-pro","input_tokens":100000},None),
    ("text",{"model_alias":"doubao-seed-2.0-pro","input_tokens":200000},None),
    ("image",{"generated_images":None},"usage_unknown"),
    ("image",{"model_alias":"doubao-seedream-5.0-pro","billing_metadata_json":"{}"},"image_size_unknown"),
    ("image",{"model_alias":"doubao-seedream-5.0-pro","billing_metadata_json":'{"requestedSize":"4K","inputImageCount":3}'},None),
    ("image",{"model_alias":"dola-seedream-5.0-pro","metadata_json":'{"response":{"data":[]}}'},"image_size_unknown"),
    ("image",{"model_alias":"dola-seedream-5.0-pro","metadata_json":'{"response":{"data":[{"url":"https://example.com/a"}]}}'},"image_size_unknown"),
    ("image",{"model_alias":"dola-seedream-5.0-pro","metadata_json":'{"response":{"data":[{"url":"https://example.com/a","size":"1024x1024"}]}}'},None),
    ("embedding",{"input_tokens":None},"usage_unknown"),
    ("embedding",{"model_alias":"doubao-embedding-vision"},"embedding_input_unknown"),
    ("embedding",{"model_alias":"doubao-embedding-vision","usage_dimension":"image"},None),
    ("audio",{"capabilities_json":'{"billingMetric":"characters"}'},"usage_unknown"),
    ("audio",{"capabilities_json":'{"billingMetric":"characters"}',"input_characters":12},None),
    ("audio",{"audio_seconds":0},"usage_unknown"),
    ("audio",{"audio_seconds":2},None),
    ("video",{"provider":"modeltop","model_alias":"dreamina-seedance-2.0","output_tokens":None},"usage_unknown"),
    ("video",{"provider":"modeltop","model_alias":"dreamina-seedance-2.0"},"resolution_unknown"),
    ("video",{"provider":"modeltop","model_alias":"dreamina-seedance-2.0","metadata_json":'{"resolution":"4k"}',"billing_metadata_json":'{"containsVideoInput":true}'},None),
    ("video",{"provider":"volcengine_ark","model_alias":"doubao-seedance-1.0-pro"},None),
    ("video",{"video_seconds":None},"usage_unknown"),
    ("video",{"video_seconds":4},"resolution_unknown"),
    ("video",{"video_seconds":4,"metadata_json":'{"resolution":"720p"}'},None),
])
def test_shared_measurement_safety_and_missing_dimensions(modality,extra,reason):
    row={"modality":modality,"model_alias":"generic","provider":"other","input_tokens":1000,"output_tokens":100,"generated_images":1,"audio_seconds":None,"video_seconds":None,**extra}
    result,actual=BillingManager._relay_measurements(row)
    assert actual==reason
    if reason is None: assert result is not None


@pytest.mark.parametrize("size,expected",[("1024x1024","output:le2610000"),("4000x4000","output:gt2610000"),("1K","output:le2610000"),("4K","output:gt2610000"),("auto",None)])
def test_existing_pixel_price_buckets_unchanged(size,expected):
    assert BillingManager._image_pixel_bucket(size)==expected


@pytest.mark.parametrize("prices",[
    {"rules":{}},{"rules":[1]},{"rules":[{"metric":"input_tokens","unitSize":"bad"}]},
    {"rules":[{"metric":"invalid","unitSize":100}]},
    {"rules":[{"metric":"input_tokens","unitSize":100,"unitPriceYuan":"1"}]*2},
])
def test_price_rule_validation(prices):
    with pytest.raises(ApiError):BillingManager._rate_rows({"modality":"image"},prices)


@pytest.mark.parametrize("model,prices,metric",[
    ({"modality":"embedding"},{"inputPerMillionYuan":"1"},"input_tokens"),
    ({"modality":"audio","capabilities":{"billingMetric":"characters","billingUnit":10000}},{"perTenThousandCharactersYuan":"3"},"characters"),
    ({"modality":"audio","capabilities":{"billingMetric":"audio_second","billingUnit":3600}},{"perHourYuan":"3"},"audio_second"),
    ({"modality":"audio","capabilities":{"billingMetric":"audio_second","billingUnit":60}},{"perMinuteYuan":"3"},"audio_second"),
])
def test_existing_embedding_audio_price_forms_remain_compatible(model,prices,metric):
    assert BillingManager._rate_rows(model,prices)[0][0]==metric
    assert BillingManager._editable_rule_templates(model)[0]["metric"]==metric
