# Vega 图片与多模态理解

[文档首页](../../CLIENT_API.md) · [模型目录](models.md) · [逐模型示例](model-reference.md) · [Vega 视频与素材](vega.md)

## 先开通，再调用

Vega 视频、图片和多模态理解共用本站的 **Vega 渠道**，不是三个供应商。管理员为项目绑定渠道、启用模型后，客户只传本站业务 API Key 和模型别名；不要传腾讯云 SecretId、SecretKey、API Token、SubAppId、站点或上游地址。

本文使用以下环境变量；请将业务 Key 换成管理员发放的值：

```bash
export BASE_URL="https://api.richbest.cn"
export API_KEY="请填写本站业务APIKey"
```

以 `GET /v1/models` 返回的可用模型为准；文档中的模型不代表项目已经开通。

## Vega-Image 模型

| 本站 model | 参考图上限 | 输出张数 n | 提示词 |
|---|---|---|---|
| `vega-image-1.0-lite` | 3 | 1 | 最多2000字符 |
| `vega-image-1.0-flash` | 6 | 1～15，供应商可能进一步限制 | 同上 |
| `vega-image-1.0-pro` | 6 | 1～15，供应商可能进一步限制 | 同上 |

支持文生图与参考图生图。没有参考图时必须填写非空 `prompt`；有参考图时可省略提示词。参考图字段为 `image`，可传一个字符串或字符串数组，每项为公网 HTTP(S) URL 或 JPEG、PNG、WebP 的 Base64 Data URL。不接受 `asset://`、腾讯云 FileId 或火山 assetId。

远程参考图每张不超过10MB，实际格式及大小由上游检查；所有内联参考图解码后合计不超过7 MiB，并在本站校验真实图片格式。客户应确保远程链接在处理期间持续有效。

### 推荐：异步创建并查询

```bash
curl "$BASE_URL/v1/images/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: image-order-001" \
  -d '{"model":"vega-image-1.0-flash","prompt":"清晨的森林，柔和光线，水彩风格","size":"1K","aspect_ratio":"16:9","n":1}'
```

响应示例（使用本站任务 ID，不是上游 TaskId）：

```json
{"id":"img_示例任务ID","object":"image_task","model":"vega-image-1.0-flash","status":"queued","progress":0}
```

创建接口必须提供1～128字符的 `Idempotency-Key`。同一业务 Key 下，相同键与相同请求返回原任务；更改请求内容必须使用新键。网络超时或结果未知时不要换键重复提交，以免重复生成和计费。

```bash
export TASK_ID="请填写创建接口返回的id"
curl "$BASE_URL/v1/images/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

处理状态为 `queued / running / succeeded / failed`。建议间隔2～5秒查询。任务仅可由创建它的业务 Key 查询，凭证轮换后仍使用任务创建时固定的渠道与凭证版本。

```json
{
  "id":"img_示例任务ID",
  "object":"image_task",
  "model":"vega-image-1.0-flash",
  "status":"succeeded",
  "progress":100,
  "result":{
    "created":1792598400,
    "model":"vega-image-1.0-flash",
    "task_id":"img_示例任务ID",
    "data":[{"url":"https://example.com/generated.png","expires_at":"2026-10-23T00:00:00Z","size":"1920x1080"}]
  }
}
```

`expires_at` 和 `size` 仅在供应商返回相应信息时出现。链接为供应商临时结果，请及时下载保存；本站不承诺永久有效。不支持取消图片任务。

### 兼容同步生图

`POST /v1/images/generations` 接受相同参数和必填幂等键，服务端提交后等待原任务完成，成功直接返回 `created / model / task_id / data`。超过等待时间返回 `image_task_pending`，错误详情中的 `taskId` 可继续通过异步查询接口读取，不要重复创建。

### 参数说明

| 字段 | 说明 |
|---|---|
| `model` | 上表本站别名，必填 |
| `prompt` | 最多2000字符；无参考图时必填 |
| `image` | URL / Data URL 字符串或数组，可省略 |
| `n` | 默认1，按上表限制 |
| `size` | 默认 `1K`，可选 `1K / 2K / 4K`；也兼容接入文档中的 `1080P` 和固定像素预设，如 `1024x1024 / 1920x1080 / 2048x2048 / 3840x2160`，不支持任意像素值 |
| `aspect_ratio` | 默认 `1:1`；支持 `1:1 / 2:3 / 3:2 / 3:4 / 4:3 / 9:16 / 16:9 / 21:9`；传像素预设时不能与其比例冲突 |
| `response_format` | 仅 `url`，默认 `url`，不支持 `b64_json` |
| `watermark` | 可选布尔值，映射供应商 LogoAdd；不传则沿用上游默认，不代表保证无隐形标识 |
| `stream` | 仅允许 `false` 或省略，不提供图片流式返回 |

不支持 `quality / style / seed / tools` 等其他供应商专属参数。提交时 `n` 是期望张数，实际输出张数以成功响应的 `data` 为准。

## Vega-VL 模型

| 本站 model | 纯文本 | 图片 / 视频 / 音频 / 文件 | JSON / SSE |
|---|---|---|---|
| `wand-vega-vl-1.0-lite` | 支持 | 支持 | 支持 |
| `wand-vega-vl-1.0-flash` | 支持 | 支持 | 支持 |
| `wand-vega-vl-1.0-pro` | 不支持，至少输入一种媒体 | 支持 | 支持 |

仅支持 `POST /v1/chat/completions`，不支持 `/v1/responses`。`model` 使用表中的完整别名。

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"wand-vega-vl-1.0-pro","messages":[{"role":"user","content":[{"type":"text","text":"描述图片的主体和场景"},{"type":"image_url","image_url":{"url":"https://example.com/photo.jpg"}}]}],"stream":false}'
```

### 多模态 Part 格式

一个消息的 `content` 可以是字符串或以下 Part 数组。URL 须能被上游读取；本站不代为下载远程素材。单个媒体建议小于100MB，内联媒体硬限制为解码后100 MiB，仍需满足供应商的实际限制。单次最多10个视频。

```json
[
  {"type":"text","text":"请分析这些素材"},
  {"type":"image_url","image_url":{"url":"https://example.com/photo.jpg","detail":"auto"}},
  {"type":"video_url","video_url":{"url":"https://example.com/clip.mp4"}},
  {"type":"input_audio","input_audio":{"url":"https://example.com/voice.mp3"}},
  {"type":"file","file":{"file_url":"https://example.com/report.pdf"}}
]
```

图片、视频和音频 URL 也可采用相应媒体 MIME 的 Base64 Data URL。音频另支持 `{"type":"input_audio","input_audio":{"data":"不含前缀的Base64","format":"mp3"}}`，`format` 仅为 `mp3 / wav`。内联文件使用 `{"type":"file","file":{"file_data":"data:application/pdf;base64,...","file_name":"report.pdf"}}`；不要将 `file_url` 放到 Part 顶层。

### 思考、流式与会话

- 可选参数：`thinking_enabled`、`reasoning_effort`（`none / minimal / low / medium / high / xhigh`）、`reasoning_split`、`temperature`（0～2）、`max_tokens`、`max_completion_tokens`、`tools`、`tool_choice`、`response_format`。其他供应商参数不一定适用。
- `reasoning_effort` 优先于 `thinking_enabled`；按供应商文档，`max_tokens` 优先于 `max_completion_tokens`，限制口径包含输入和输出。服务端不静默改写这些参数。
- 设 `stream:true` 使用 SSE；可传 `stream_options:{"include_usage":true}` 请求末尾真实用量。保留上游 `reasoning_content / reasoning_details`，业务侧应将思考与最终回答分开处理。
- 可选请求头 `Tx-User-Session-Id`（1～256字符）用于会话缓存。服务端按项目及业务 Key 派生隔离值，不会把不同客户的同名会话混用。
- 上游 Token 尚未同步、模型未开通或余额不足时会返回明确错误；客户不要改传腾讯云 API Token 来绕过本站绑定。

## 价格与用量

最终以项目的 `GET /v1/pricing?model=模型别名` 和账单为准，下面仅说明初始参考价格，不代表项目已启用计费。

Vega-Image 国内站输出：Lite ¥0.162/张、Flash ¥0.45/张、Pro ¥0.95/张。Lite、Flash 输入不收费；Pro 前3张输入免费，超过部分 ¥0.10/张。按上游实际成功输出张数计量；Pro 超额输入须有供应商确认数量。所给文档没有国际站图片价格，系统不擅自换算，需管理员补齐；缺价或缺用量进入待计价，不按零元结算。

Vega-VL 刊例价（每百万 Token；缓存输入单独计价，不再重复计算普通输入）：

| 模型 | 国内输入 / 输出 / 缓存输入，CNY | 国际输入 / 输出 / 缓存输入，USD |
|---|---|---|
| Lite | 0.7 / 2.6 / 0.14 | 0.14 / 0.45 / 0.028 |
| Flash | 3 / 15 / 0.6 | 0.44 / 2.21 / 0.088 |
| Pro | 8 / 40 / 1 | 1.25 / 6.25 / 0.15 |

只采集真实返回的 `usage`。`cached_tokens` 与 `cache_read_tokens` 若同时返回，视为重叠统计，不相加；普通输入计量为输入总量减缓存命中量。供应商可能额外返回 `video_tokens / reasoning_tokens` 等明细，响应中保留，但不另行重复加收。缺少必要用量或流式响应未完成时留待核对，不伪造为零。

国际站参考价使用2026-10-22的固定汇率快照 `1 USD = 6.689327 CNY` 初始化为人民币，不是实时换汇；管理员后续可统一调整。开启计费、余额控制和项目限额仍由管理员配置，新模型不会自动开启项目计费。
