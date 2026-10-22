# 模型目录与价格

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

## 查询可用模型

```bash
curl "$BASE_URL/v1/models" \
  -H "Authorization: Bearer $API_KEY"
```

只返回当前项目已启用且渠道可用的模型。同一项目的有效业务 Key 共享模型授权；任务访问仍按创建任务的 Key 隔离。请求中的 `model` 必须原样使用返回的 `id`，不能拼接版本号或真实上游模型 ID。

响应示例：

```json
{
  "object": "list",
  "data": [
    {
      "id": "doubao-seed-2.0-lite",
      "object": "model",
      "created": 0,
      "owned_by": "richbest",
      "display_name": "Doubao Seed 2.0 Lite",
      "modality": "text",
      "capabilities": {
        "chat": true,
        "responses": true,
        "stream": true,
        "imageInput": true,
        "vision": true
      }
    }
  ]
}
```

`data` 为空不代表业务 Key 无效，而是该 Key 所属项目尚未开通可用模型。客户端应使用返回的 `id` 作为后续请求的 `model`，不要缓存或猜测未返回的模型。如需使用其他模型，请联系管理员为当前项目开通；开通后项目下现有业务 Key 可直接使用，无需重新签发。

## 模型与接口对照表

此表说明已接入范围，不代表项目默认全部开通。同一别名只出现一次，实际能力和价格取决于当前项目渠道。

| 对外模型别名 | 能力 | 发起请求接口 | 响应方式或结果接口 | 独立参考 |
|---|---|---|---|---|
| `deepseek-v4-flash` | 文本对话 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#deepseek-v4-flash) |
| `deepseek-v4-pro` | 文本对话 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#deepseek-v4-pro) |
| `glm-5.2` | 文本对话 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#glm-52) |
| `doubao-seed-2.1-pro` | 文本、识图 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-21-pro) |
| `doubao-seed-2.1-turbo` | 文本、识图 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-21-turbo) |
| `doubao-seed-2.0-pro` | 文本、识图 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-20-pro) |
| `doubao-seed-2.0-lite` | 文本、识图 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-20-lite) |
| `doubao-seed-2.0-mini` | 文本、识图 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-20-mini) |
| `doubao-seed-evolving` | 文本、识图、Coding 与 Agent | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-evolving) |
| `doubao-seed-character` | 文本对话、角色扮演 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-character) |
| `doubao-seed-2.0-code` | 文本、识图、编程 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 | [查看接口](model-reference.md#doubao-seed-20-code) |
| `doubao-seed-translation` | 文本翻译 | `POST /v1/responses` | 同步 JSON；必须使用翻译结构化输入 | [查看接口](model-reference.md#doubao-seed-translation) |
| `doubao-seedream-5.0-pro` | 生图、参考图改图；最多 10 张参考图，单次 1 张结果 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 | [查看接口](model-reference.md#doubao-seedream-50-pro) |
| `doubao-seedream-5.0-lite` | 生图、参考图改图、组图；最多 10 张参考图、15 张结果 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 | [查看接口](model-reference.md#doubao-seedream-50-lite) |
| `doubao-seedream-5.0` | 生图、参考图改图；最多 10 张参考图，单次 1 张结果 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 | [查看接口](model-reference.md#doubao-seedream-50) |
| `doubao-seedream-4.5` | 生图、参考图改图、组图；最多 10 张参考图、15 张结果 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 | [查看接口](model-reference.md#doubao-seedream-45) |
| `doubao-seedream-4.0` | 生图、参考图改图、组图；最多 10 张参考图、15 张结果 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 | [查看接口](model-reference.md#doubao-seedream-40) |
| `gpt-image-2` | 生图；MaxModel单张、ModelTop最多10张 | `POST /v1/images/generations` | 同步JSON；ModelTop优先读取Base64 | [查看接口](model-reference.md#gpt-image-2) |
| `doubao-embedding-vision` | 文本、图片和视频多模态向量化 | `POST /v1/embeddings`<br>`POST /v1/embeddings/multimodal` | 同步 JSON | [查看接口](model-reference.md#doubao-embedding-vision) |
| `doubao-seed-tts-2.0` | 语音合成 | `POST /v1/audio/speech` | 音频二进制响应 | [查看接口](model-reference.md#doubao-seed-tts-20) |
| `doubao-seedasr-2.0` | 异步录音识别 | `POST /v1/audio/transcriptions` | `GET /v1/audio/transcriptions/{taskId}` | [查看接口](model-reference.md#doubao-seedasr-20) |
| `doubao-seed-audio-1.0` | 音频生成 | `POST /v1/audio/generations` | 同步 JSON | [查看接口](model-reference.md#doubao-seed-audio-10) |
| `doubao-seedance-2.5` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#doubao-seedance-25) |
| `doubao-seedance-2.0` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#doubao-seedance-20) |
| `doubao-seedance-2.0-fast` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#doubao-seedance-20-fast) |
| `doubao-seedance-2.0-mini` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#doubao-seedance-20-mini) |
| `doubao-seedance-1.0-pro` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#doubao-seedance-10-pro) |
| `doubao-seedance-1.0-pro-fast` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#doubao-seedance-10-pro-fast) |
| `dreamina-seedance-2.5` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-25) |
| `dreamina-seedance-2.0` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-20) |
| `dreamina-seedance-2.0-fast` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-20-fast) |
| `dreamina-seedance-2.0-mini` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-20-mini) |
| `dola-seedream-5.0-pro` | 生图、参考图改图；单次 1 张结果 | `POST /v1/images/generations` | 同步 JSON，结果为 URL 或 Base64 | [查看接口](model-reference.md#dola-seedream-50-pro) |
| `dola-seedream-5.0-lite` | 生图、参考图改图、组图；最多 15 张结果 | `POST /v1/images/generations` | 同步 JSON，结果为 URL 或 Base64 | [查看接口](model-reference.md#dola-seedream-50-lite) |
| `dola-seedream-5.0-flash` | 生图、参考图改图；单次 1 张结果 | `POST /v1/images/generations` | 同步 JSON，结果为 URL 或 Base64 | [查看接口](model-reference.md#dola-seedream-50-flash) |
| `wan3.0-video` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#wan30-video) |
| `minimax-h3` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#minimax-h3) |
| `gpt-image-2.5-flare` | 文生图；最多 10 张 | `POST /v1/images/generations` | 同步 JSON，优先读取 `data[].b64_json` | [查看接口](model-reference.md#gpt-image-25-flare) |
| `gpt-image-2.5-sunburst` | 文生图；最多 10 张 | `POST /v1/images/generations` | 同步 JSON，优先读取 `data[].b64_json` | [查看接口](model-reference.md#gpt-image-25-sunburst) |
| `dreamina-seedance-2.5-filter-off` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-25-filter-off) |
| `dreamina-seedance-2.0-filter-off` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-20-filter-off) |
| `dreamina-seedance-2.0-fast-filter-off` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-20-fast-filter-off) |
| `dreamina-seedance-2.0-mini-filter-off` | 异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#dreamina-seedance-20-mini-filter-off) |
创建和查询视频任务必须使用同一枚业务 API Key；支持取消的供应商同样要求使用创建任务时的业务 Key。

模型是否已经对当前项目开放，以 `/v1/models` 的实时返回结果为准。请求未开通的模型会返回 `403 model_not_allowed`，请联系管理员确认项目授权和供应商渠道状态。

| `vega-1.0-lite` | Vega多模态异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#vega-10-lite) |
| `vega-1.0-pro` | Vega多模态异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#vega-10-pro) |
| `vega-1.0-pro-fast` | Vega多模态异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#vega-10-pro-fast) |
| `vega-1.0-pro-mini` | Vega多模态异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#vega-10-pro-mini) |
| `vega-1.5-pro` | Vega多模态异步视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` | [查看接口](model-reference.md#vega-15-pro) |
| `vega-image-1.0-lite` | 文生图、参考图生图；最多3张参考图 | `POST /v1/images/tasks` / `POST /v1/images/generations` | 异步查询或同步JSON，临时URL | [查看接口](model-reference.md#vega-image-10-lite) |
| `vega-image-1.0-flash` | 文生图、参考图生图；最多6张参考图 | `POST /v1/images/tasks` / `POST /v1/images/generations` | 异步查询或同步JSON，临时URL | [查看接口](model-reference.md#vega-image-10-flash) |
| `vega-image-1.0-pro` | 文生图、参考图生图；最多6张参考图 | `POST /v1/images/tasks` / `POST /v1/images/generations` | 异步查询或同步JSON，临时URL | [查看接口](model-reference.md#vega-image-10-pro) |
| `wand-vega-vl-1.0-lite` | 纯文本及图片、视频、音频、文件理解 | `POST /v1/chat/completions` | JSON / SSE，不支持Responses | [查看接口](model-reference.md#wand-vega-vl-10-lite) |
| `wand-vega-vl-1.0-flash` | 纯文本及图片、视频、音频、文件理解 | `POST /v1/chat/completions` | JSON / SSE，不支持Responses | [查看接口](model-reference.md#wand-vega-vl-10-flash) |
| `wand-vega-vl-1.0-pro` | 图片、视频、音频、文件理解；不支持纯文本 | `POST /v1/chat/completions` | JSON / SSE，不支持Responses | [查看接口](model-reference.md#wand-vega-vl-10-pro) |

每个“查看接口”包含该模型的请求、参数、示例与结果；无需先猜测应使用哪类接口。

左侧按供应商分组，再选择模型。`gpt-image-2` 同时出现在 MaxModel 和 ModelTop 下；四个标准 `dreamina-seedance-*` 型号同时出现在 BytePlus 和 ModelTop 下。它们的公开路径及模型别名相同，但数量限制、参数、结果格式或取消能力可能不同，请按当前项目的 `provider` 阅读。`-filter-off` 型号只列在 ModelTop 下。Vega独立列在“Vega（腾讯云点播）”下。

## 查询模型价格

```bash
curl "$BASE_URL/v1/pricing" \
  -H "Authorization: Bearer $API_KEY"
```

该接口使用与其他客户接口相同的业务 Key 鉴权，只返回当前业务 Key 所属项目已启用且渠道可用的模型，不会返回其他项目或尚未开通的模型。可使用可选查询参数 `model` 按模型别名或展示名称进行不区分大小写的包含匹配：

```bash
curl "$BASE_URL/v1/pricing?model=glm-5.2" \
  -H "Authorization: Bearer $API_KEY"
```

`model` 长度为 1～128 个字符，包含空格或其他特殊字符时应进行 URL 编码。不传该参数时返回当前项目的完整可用模型价格表；未匹配到模型时仍返回 `200`，但 `data` 为空数组。

完整响应示例：

```json
{
  "object": "list",
  "month": "2026-09",
  "currency": "CNY",
  "tax_inclusive": false,
  "billing_enabled": true,
  "discount_bps": 8000,
  "data": [
    {
      "id": "glm-5.2",
      "object": "model_price",
      "display_name": "GLM 5.2",
      "provider": "volcengine_ark",
      "modality": "text",
      "currency": "CNY",
      "tax_inclusive": false,
      "configured": true,
      "prices": [
        {
          "metric": "cached_input_tokens",
          "dimension": null,
          "unit_size": 1000000,
          "list_price_yuan": "2.000000",
          "effective_price_yuan": "1.600000"
        },
        {
          "metric": "input_tokens",
          "dimension": null,
          "unit_size": 1000000,
          "list_price_yuan": "8.000000",
          "effective_price_yuan": "6.400000"
        },
        {
          "metric": "output_tokens",
          "dimension": null,
          "unit_size": 1000000,
          "list_price_yuan": "28.000000",
          "effective_price_yuan": "22.400000"
        }
      ]
    }
  ]
}
```

顶层字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `month` | string | 当前价格账期，格式为 `YYYY-MM` |
| `currency` | string | 固定为人民币 `CNY` |
| `tax_inclusive` | boolean | 当前固定为 `false`，表示税前价格 |
| `billing_enabled` | boolean | 当前项目是否已启用账单归集；为 `false` 时仍可查询参考价 |
| `discount_bps` | integer | 当前项目价格系数，`10000` 为原价、`8000` 为八折 |
| `data` | array | 当前项目可用模型的价格列表 |

模型及价格字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 请求模型接口时使用的公开模型名称 |
| `display_name` | string | 用于界面展示的模型名称 |
| `provider` | string | 模型供应商标识 |
| `modality` | string | `text`、`image`、`video`、`embedding` 或 `audio` |
| `configured` | boolean | 是否已有可用价格；为 `false` 时 `prices` 为空且不代表免费 |
| `prices[].metric` | string | 计价指标，例如输入、缓存输入、输出、图片、视频时长、字符或音频时长 |
| `prices[].dimension` | string/null | 上下文档位、图片规格、分辨率和是否包含视频输入等计价维度 |
| `prices[].unit_size` | integer | 对应单价所覆盖的计量单位数量，例如 `1000000` 表示每百万 Token |
| `prices[].list_price_yuan` | string | 平台公开税前单价，使用十进制字符串返回 |
| `prices[].effective_price_yuan` | string | 应用当前项目价格系数后的税前单价 |

只有单价明确返回 `"0.000000"` 才表示免费。金额字段必须作为十进制字符串处理，不要转换成二进制浮点数后用于最终金额计算。价格接口用于调用前查询，实际结算仍以服务端记录的成功用量和对应账期价格为准。

常见响应：

| HTTP 状态 | 说明 |
|---|---|
| `200` | 查询成功；未匹配模型时 `data` 为空 |
| `401` | 业务 Key 缺失、无效或已停用 |
| `422` | `model` 参数为空或长度超过限制 |
| `503` | 模型中转功能当前未启用 |

## 海外模型计价维度

海外模型的价格直接使用官方公示价折算成人民币，不叠加加价；`list_price_yuan` 就是可核对的原价，`effective_price_yuan` 再按项目价格系数打折。海外价目只影响金额，不改变任何请求字段。

| 模型 | `metric` | `unit_size` | `dimension` | 含义 |
|---|---|---|---|---|
| `dreamina-seedance-*` | `output_tokens` | `1000000` | `480p:no_video`、`480p:video`、`720p:*`、`1080p:*` | 每百万输出 Token；`no_video` 表示请求中不含视频参考输入，`video` 表示含视频参考输入 |
| `dola-seedream-5.0-pro` | `image` | `1` | `output:le2610000` | 单张生成结果，输出图不超过 261 万像素 | [查看接口](model-reference.md#dola-seedream-50-pro) |
| `dola-seedream-5.0-pro` | `image` | `1` | `output:gt2610000` | 单张生成结果，输出图超过 261 万像素 | [查看接口](model-reference.md#dola-seedream-50-pro) |
| `dola-seedream-5.0-pro` | `image` | `1` | `input:after_first` | 输入参考图的第一张之后的每张图片 | [查看接口](model-reference.md#dola-seedream-50-pro) |
| `dola-seedream-5.0-flash`、`dola-seedream-5.0-lite` | `image` | `1` | 空值 | 每张成功输出图片 |

海外视频按上游返回的真实输出 Token 计费，而不是按时长。任务查询响应里的 `usage.completion_tokens` 就是结算依据，可以用它核对预估金额：

```json
{"model": "dreamina-seedance-2.0-mini", "usage": {"completion_tokens": 40594, "total_tokens": 40594}}
```

上例为 4 秒 480p 文生视频。若 `/v1/pricing` 返回该分辨率维度的 `list_price_yuan` 为 `23.467588`，则原价金额约 `40594 × 23.467588 ÷ 1000000 = 0.952643` 元。同一段视频换成 720p、1080p 或加入视频参考输入时，上游 Token 数和适用维度都会变化，请以实际返回的 `usage` 和对应维度单价为准，不要用时长做最终金额。

Pro 图片落在哪一档由输出图的实际像素决定，`1K`、`1.5K` 档通常不超过 261 万像素，`2K` 及以上可能超过；两条价位都会出现在 `/v1/pricing` 中，最终以实际结算金额为准。平台不对海外模型单独提供优惠券或包月口径，项目价格系数（`discount_bps`）对全部模型统一生效，`/v1/pricing` 与月度账单使用同一份价目。

## ModelTop 计价维度

ModelTop 渠道的 GPT 生图按文本输入、图片输入、图片输出及缓存 Token 细分计价；视频按输出 Token、分辨率及是否包含视频参考输入计价。具体人民币单价以 `/v1/pricing` 为准。

GPT Image 2 未单独公示的缓存输入价格、缺失的真实细分用量均进入待计价，不默认免费。所有海外渠道均返回人民币单价，客户无需自行换汇；渠道变更后应重新查询价目。

`billing_enabled=false` 只表示项目未启用本系统账单归集，不代表供应商调用免费。该公开接口不提供账单、调整项或支付状态。
