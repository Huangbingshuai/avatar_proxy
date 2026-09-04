# Star Proxy 模型中转接口

本文档面向接入 Star Proxy 的服务端应用，例如 RichiDrama，是 [CLIENT_API.md](CLIENT_API.md) 中模型接口的快速接入版。公开路径、字段、响应和错误规则如有疑问，以 `CLIENT_API.md` 为准；模型实时可用性和能力以当前业务 Key 调用 `/v1/models` 的结果为准。RichiDrama 侧的具体改造项和验收清单见 [RICHIDRAMA_RELAY_ALIGNMENT.md](RICHIDRAMA_RELAY_ALIGNMENT.md)。

## 1. 接入信息

生产地址：

```text
https://api.richbest.cn
```

所有模型接口均使用 Star Proxy 签发的业务 API Key：

```http
Authorization: Bearer vap_live_xxx
Content-Type: application/json
```

调用方不得提交火山方舟 Key，也不得在请求中传递 `provider`、`channel`、`channel_id`、`base_url`、`api_key`、`project` 或 `project_name`。服务端根据业务 Key 确定客户项目、可用模型、供应商渠道和加密凭证。

每次响应都会包含 `X-Request-Id`。排查失败时应保存该值和响应正文，但不要记录或发送完整业务 Key。

## 2. 模型发现与别名

```http
GET /v1/models
```

客户端必须以该接口的响应作为当前业务 Key 的可用模型清单，不应自行展示未返回的模型。

```bash
curl "https://api.richbest.cn/v1/models" \
  -H "Authorization: Bearer $API_KEY"
```

响应示例：

```json
{
  "object": "list",
  "data": [
    {
      "id": "doubao-seedream-5.0",
      "object": "model",
      "owned_by": "richbest",
      "display_name": "Seedream 5.0",
      "modality": "image",
      "capabilities": {
        "generations": true,
        "imageInput": true,
        "maxInputImages": 10,
        "maxInputImageBytes": 10485760,
        "maxN": 1
      }
    }
  ]
}
```

`data[].id` 是 Star Proxy 对外稳定别名。调用方只传该别名，不能传火山完整 Model ID。当前内置模型总表见 [CLIENT_API.md 的“可用模型”](CLIENT_API.md#131-可用模型)；某个业务 Key 实际可用的子集仍只以 `/v1/models` 为准。

别名由 Star Proxy 映射到固定的真实上游模型。模型升级、渠道轮换和供应商差异由中转站管理，调用方不依赖真实 Model ID。

## 3. 文本与视觉理解

支持 OpenAI 兼容接口：

```text
POST /v1/chat/completions
POST /v1/responses
```

Chat Completions 示例：

```bash
curl "https://api.richbest.cn/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2.1-turbo",
    "messages": [
      {"role": "user", "content": "把这段剧情概括成三个镜头"}
    ],
    "stream": false
  }'
```

视觉理解模型可在 `messages[].content` 中使用 OpenAI 图片内容结构：

```json
{
  "model": "doubao-seed-2.1-turbo",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "描述图片中的人物"},
        {"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}}
      ]
    }
  ]
}
```

是否支持流式输出和图片输入以 `/v1/models` 返回的 `capabilities` 为准。

## 4. Seedream 图片生成

```http
POST /v1/images/generations
```

```bash
curl "https://api.richbest.cn/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: image-order-001" \
  -d '{
    "model": "doubao-seedream-5.0",
    "prompt": "电影感室内场景，暖色灯光",
    "image": ["https://example.com/reference.png"],
    "size": "2K",
    "n": 1,
    "response_format": "url",
    "watermark": false
  }'
```

主要字段：

| 字段 | 说明 |
|---|---|
| `model` | 必须使用 `/v1/models` 返回的图片模型别名 |
| `prompt` | 必填，非空字符串 |
| `image` | 可选，单个 URL/Data URL 或数组；数量以模型能力为准 |
| `size` | 输出尺寸，例如 `2K` 或模型支持的宽高值 |
| `n` | 1～15，且不能超过模型的 `maxN` |
| `response_format` | `url` 或 `b64_json` |
| `output_format` | 部分 Seedream 模型支持 |
| `sequential_image_generation` | 部分 Seedream 模型支持组图 |
| `watermark` | 是否添加水印 |
| `seed`、`guidance_scale` | 仅在对应模型能力支持时使用 |

Seedream 参考图支持公网 HTTP(S) URL 或 `data:image/*;base64,...`。Base64 按解码后的真实文件大小校验，当前单张上限为 10 MiB、最多 10 张；公网 URL 由火山读取并进行最终校验。

以下兼容字段不会转发给火山 Seedream，因此调用方不应将其展示为有效控制项：

```text
quality
style
user
```

`negative_prompt` 不属于当前公开契约，传入会返回 `422 image_parameter_unsupported`。调用方应把负向要求直接写入 `prompt`，而不是发送该字段。

成功响应遵循 OpenAI 图片响应结构，供应商 URL 可能过期，中转站不会自动转存到 TOS。

## 5. Seedance 与多供应商视频

视频接口采用火山方舟兼容任务路径：

```text
POST   /api/v3/contents/generations/tasks
GET    /api/v3/contents/generations/tasks/{taskId}
DELETE /api/v3/contents/generations/tasks/{taskId}
```

创建示例：

```bash
curl -X POST "https://api.richbest.cn/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: video-order-001" \
  -d '{
    "model": "doubao-seedance-2.0",
    "content": [
      {"type": "text", "text": "人物走向镜头，电影感运镜"},
      {
        "type": "image_url",
        "image_url": {"url": "asset://asset-example"},
        "role": "reference_image"
      }
    ],
    "ratio": "16:9",
    "resolution": "720p",
    "duration": 5,
    "generate_audio": true,
    "watermark": false
  }'
```

允许的创建字段为：

```text
model, content, duration, frames, resolution, ratio, generate_audio,
draft, seed, camera_fixed, watermark, return_last_frame,
service_tier, execution_expires_after, task_type
```

只使用 `ratio`，不要同时发送 `aspect_ratio`。不同模型的素材类型、分辨率、时长和参数能力不同，调用方必须根据 `/v1/models` 的 `capabilities` 控制表单和请求。

火山 Seedance 可按模型能力使用 HTTP(S)、当前项目可访问的 `asset://`，以及合法的图片/音频 Data URL。`wan3.0-video` 和 `minimax-h3` 当前只接受 HTTP(S) 图片引用。

创建成功只返回中转站任务 ID：

```json
{"id": "vid_0123456789abcdef"}
```

查询示例：

```bash
curl "https://api.richbest.cn/api/v3/contents/generations/tasks/vid_0123456789abcdef" \
  -H "Authorization: Bearer $API_KEY"
```

任务状态为 `queued`、`running`、`succeeded`、`failed` 或 `cancelled`。任务只能由创建它的同一枚业务 Key 查询和取消。同项目的另一枚 Key 也不能读取任务。

火山任务支持取消；未完成取消适配验证的其他供应商会返回 `422 video_cancel_unsupported`，不会伪装成取消成功。

## 6. 向量与音频

```text
POST /v1/embeddings
POST /v1/embeddings/multimodal
POST /v1/audio/speech
POST /v1/audio/transcriptions
GET  /v1/audio/transcriptions/{taskId}
POST /v1/audio/generations
```

`doubao-embedding-vision` 使用项目的火山方舟渠道。`doubao-seed-tts-2.0`、`doubao-seedasr-2.0` 和 `doubao-seed-audio-1.0` 使用独立豆包语音渠道，调用方仍只持有瑞池业务 Key，不接触语音供应商凭证。完整字段、响应结构和 curl 示例见 [CLIENT_API.md 的“向量与音频接口”](CLIENT_API.md#136-向量与音频接口)。

语音合成直接返回音频二进制；录音识别为异步任务，必须使用提交任务时的同一枚业务 Key 查询。语音模型调用会产生真实费用，不应使用渠道测试按钮自动探测。

## 7. 幂等与重试

图片和视频创建可发送长度 1～128 的 `Idempotency-Key`：

```http
Idempotency-Key: video-generation-12345
```

同一业务 Key、同一操作、相同幂等键和相同请求体会复用已有结果；相同键对应不同请求体返回：

```text
409 idempotency_key_conflict
```

调用方自身仍应维护任务状态。发生网络超时时，应先使用原幂等键重试，不要立即生成新键。

## 8. 错误格式

`/v1/*` 错误遵循 OpenAI 风格：

```json
{
  "error": {
    "message": "当前项目未启用该模型或渠道不可用",
    "type": "invalid_request_error",
    "param": null,
    "code": "model_not_allowed"
  },
  "request_id": "req_xxx"
}
```

`/api/v3/*` 错误格式：

```json
{
  "error": {
    "code": "video_parameter_unsupported",
    "message": "视频请求包含火山兼容接口不支持的字段",
    "fields": ["aspect_ratio"]
  }
}
```

常见状态：

| HTTP | 说明 |
|---:|---|
| `401` | 业务 Key 缺失、错误或已禁用 |
| `403` | Key 无权访问项目或模型 |
| `404` | 模型或任务不存在 |
| `409` | 幂等请求冲突、仍在执行或此前失败 |
| `422` | 参数、素材类型或模型能力不支持 |
| `429` | 项目或 Key 额度/限流触发；可恢复时读取 `Retry-After` |
| `502` / `504` | 上游供应商拒绝、异常或超时 |

## 9. RichiDrama 对接要求

1. 将文本、图片和视频服务的 Base URL 设置为 `https://api.richbest.cn`。
2. `Authorization` 使用 Star Proxy 的 `vap_live_*`，不要使用火山方舟 Key。
3. 启动或进入配置页面时调用 `/v1/models`，按 `modality` 和 `capabilities` 展示模型。
4. 请求中的 `model` 使用 `data[].id`，不要继续发送 `doubao-...-版本号` 等上游 ID。
5. Seedream 隐藏或删除 `quality` 和 `negative_prompt`；视频只发送 `ratio`。
6. 没有被 `/v1/models` 返回的模型必须隐藏，不能尝试绕过中转站模型权限。
7. RichiDrama 如需改用中转站语音接口，只提交 `/v1/models` 返回的音频模型别名和瑞池业务 Key，不提交 AppID、Access Token 或 Cluster。
8. 不在日志中记录完整业务 Key、上游 Key、用户提示词、TTS 文本或素材 Data URL。

## 10. 接口边界

- 中转站不向调用方暴露供应商凭证、真实渠道 ID、项目名或真实上游任务 ID。
- 图片和视频结果 URL 不自动进入素材库，也不保证永久有效。
- 素材库上传与 Seedream 参考图是两条独立链路。素材库可上传本地文件到 TOS 后登记，也可直接登记公网 URL。
- 向量接口使用 `/v1/embeddings` 或 `/v1/embeddings/multimodal`；音频接口使用 `/v1/audio/speech`、`/v1/audio/transcriptions` 或 `/v1/audio/generations`。
- 生产环境不开放交互式 API 文档，本文档与 `/v1/models` 是调用方的契约来源。
