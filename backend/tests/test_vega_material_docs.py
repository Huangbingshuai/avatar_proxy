"""Replay every published Vega resource example, without cloud requests/fees."""
import json
import re
from pathlib import Path

import httpx

from app.vega_resources import ACTIONS, TEXT_LIMITS
from test_provider_relay import relay_client
from test_public_docs_examples import articles, requests
from test_vega import setup


def test_every_vega_resource_action_has_an_independent_documented_example(tmp_path):
    examples = {}
    for page_id, article in articles().items():
        if not page_id.startswith(("vega-material-", "vega-liveness-")):
            continue
        sample = list(requests(article))
        assert len(sample) == 1, page_id
        method, path, body, args = sample[0]
        action = path.rsplit("/", 1)[-1]
        assert action in ACTIONS and action not in examples
        assert method == "POST" and path == "/v1/vega/" + action
        assert body["model"] == "vega-1.0-pro"
        assert set(body) - {"model"} <= ACTIONS[action]
        examples[action] = (body, args)
    assert set(examples) == set(ACTIONS)

    calls = []
    def handler(request):
        action = request.headers["X-TC-Action"]
        calls.append(action)
        result = {"RequestId": "docs-request"}
        if action == "CreateAigcLivenessValidate":
            result.update(LivenessToken="docs-token", H5Link="https://example.com/live")
        elif action == "DescribeAigcLivenessValidateResult":
            result.update(Status="DONE", GroupId="docs-group")
        elif action == "CreateAigcMaterial":
            result["TaskId"] = "supplier-material-task"
        elif action == "DescribeTaskDetail":
            assert json.loads(request.content)["TaskId"] == "supplier-material-task"
            result.update(Status="FINISH", CreateAigcMaterialTask={
                "Status": "FINISH", "ErrCode": 0,
                "Output": {"AssetId": "docs-asset", "GroupId": "docs-group"},
            })
        return httpx.Response(200, json={"Response": result})

    with relay_client(tmp_path) as client:
        _, key, _ = setup(client)
        relay = client.app.state.provider_relay
        relay.transport = httpx.MockTransport(handler)
        replacements = {"replace-with-returned-token": "docs-token", "asset-example": "docs-asset", "group-example": "docs-group"}
        order = ["CreateAigcLivenessValidate", "DescribeAigcLivenessValidateResult", "CreateAigcMaterial",
                 "DescribeTaskDetail", "DescribeAigcMaterial", "DescribeAigcMaterialList", "ModifyAigcMaterial",
                 "DescribeAigcMaterialGroup", "ModifyAigcMaterialGroup", "DeleteAigcMaterial"]
        for action in order:
            body, args = examples[action]
            encoded = json.dumps(body)
            for old, new in replacements.items():
                encoded = encoded.replace(old, new)
            headers = {"Authorization": "Bearer " + key}
            for index, arg in enumerate(args):
                if arg == "-H" and args[index + 1].startswith("Idempotency-Key:"):
                    headers["Idempotency-Key"] = args[index + 1].split(":", 1)[1].strip()
            response = client.post("/v1/vega/" + action, json=json.loads(encoded), headers=headers)
            assert response.status_code == 200, (action, response.text)
            if action == "CreateAigcMaterial":
                replacements["tsk_material_example"] = response.json()["id"]
        assert calls == order
        with relay.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM inference_usage").fetchone()[0] == 0


def test_markdown_and_client_index_list_all_vega_resource_routes():
    backend = Path(__file__).resolve().parents[1]
    material = (backend / "docs/client-api/vega-materials.md").read_text(encoding="utf-8")
    index = (backend / "CLIENT_API.md").read_text(encoding="utf-8")
    assert set(re.findall(r"`POST /v1/vega/([A-Za-z]+)`", material)) == set(ACTIONS)
    for action in ACTIONS:
        assert f"| `POST` | `/v1/vega/{action}` |" in index
    assert "不是Response.TaskId" in material
    assert "不是JSON布尔值" in material
    assert "同一个幂等键" in material


def test_group_name_documentation_matches_the_local_supplier_limit():
    backend = Path(__file__).resolve().parents[1]
    material = (backend / "docs/client-api/vega-materials.md").read_text(encoding="utf-8")
    assert TEXT_LIMITS["GroupName"] == 64
    rows = [line for line in material.splitlines() if line.startswith("| GroupName |")]
    assert len(rows) == 2
    assert all("64字符" in row and "1024" not in row for row in rows)
    assert "后续登记不覆盖已有组名" in material
