# 语音与音频

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

所有音频接口使用星辰平台业务 Key 与公开模型别名，不提交语音 AppID、Access Token、Cluster 或资源 ID。需要音色或模型时请联系管理员开通。

## 语音合成

`POST /v1/audio/speech`

请求：JSON。成功响应：音频二进制。

语音合成字段：

| 字段 | 必填 | 默认值与约束 |
|---|---:|---|
| `model` | 是 | 必须为可用的 `doubao-seed-tts-2.0` 别名 |
| `input` | 是 | 1～10000 个字符 |
| `voice` | 是 | 当前语音项目已开通的 TTS 2.0 音色 ID，最长 128 个字符 |
| `response_format` | 否 | 默认 `mp3`；可选 `mp3`、`pcm`、`ogg_opus` |
| `sample_rate` | 否 | 默认 `24000`；可选 `8000`、`16000`、`22050`、`24000`、`32000`、`44100`、`48000` |
| `speed` | 否 | 默认 `0`；范围 `-50`～`100` 的整数 |

语音合成成功时直接返回音频二进制，Content-Type 分别为 `audio/mpeg`、`audio/L16` 或 `audio/ogg`，响应头包含 `X-Request-Id`，不要把响应体按 JSON 解析。

语音合成示例（`voice` 必须是当前语音项目已开通的 TTS 2.0 音色 ID）：

```bash
curl "$BASE_URL/v1/audio/speech" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"doubao-seed-tts-2.0",
    "input":"欢迎使用星辰平台创作空间",
    "voice":"zh_female_vv_uranus_bigtts",
    "response_format":"mp3"
  }' \
  --output speech.mp3
```

## 创建录音识别任务

`POST /v1/audio/transcriptions`

请求：JSON（音频 URL），不是文件 multipart。成功返回 `202`，然后查询任务。

录音识别字段：

| 字段 | 必填 | 默认值与约束 |
|---|---:|---|
| `model` | 是 | 必须为可用的 `doubao-seedasr-2.0` 别名 |
| `url` | 是 | 公网可访问的 HTTPS 音频 URL，最长 2048 个字符 |
| `language` | 否 | 语言提示；省略时由供应商处理 |
| `enable_speaker_info` | 否 | 默认 `false`，是否返回说话人信息 |

录音识别创建成功返回 `202`。创建和查询都必须使用同一枚业务 Key；`Idempotency-Key` 可选，见[幂等与断线恢复](errors.md#幂等与断线恢复)。任务响应固定包含 `id`、`object=audio.transcription`、`model`、`status` 和 `created_at`；成功后增加 `text` 和可用时的 `duration`，失败时增加 `error.code` 与 `error.message`。

录音识别只接受公网可访问的 HTTPS 音频 URL，并使用异步任务：

```bash
curl "$BASE_URL/v1/audio/transcriptions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: asr-order-001" \
  -d '{"model":"doubao-seedasr-2.0","url":"https://example.com/meeting.mp3"}'
```

保存 `202` 响应中的 `id`，作为下文的 `TASK_ID`；不要使用示例 ID 查询自己的任务。

## 查询录音识别任务

`GET /v1/audio/transcriptions/{taskId}`

任务状态为 `queued`、`running`、`succeeded` 或 `failed`；成功时响应包含 `text` 和供应商返回的真实 `duration`。不要将创建返回 `202` 当成识别完成。

将创建返回的 `id` 设置为环境变量 `TASK_ID`，使用创建时的同一枚业务 Key 每 5～10 秒查询，直到终态：

```bash
curl "$BASE_URL/v1/audio/transcriptions/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

```json
{
  "id": "asr_example",
  "object": "audio.transcription",
  "model": "doubao-seedasr-2.0",
  "status": "succeeded",
  "created_at": 1792108800,
  "text": "欢迎使用星辰平台。",
  "duration": 2.5
}
```

## 音频生成

`POST /v1/audio/generations`

请求、响应：JSON。

音频生成字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `model` | 是 | 必须为可用的 `doubao-seed-audio-1.0` 别名 |
| `prompt` | 是 | 1～4000 个字符 |
| `speaker` | 否 | 供应商支持的音色或说话人参数 |
| `audio_url` / `audio_data` | 否 | 可选音频参考输入 |
| `image_url` / `image_data` | 否 | 可选图片参考输入 |
| `duration` | 否 | 期望时长，由供应商校验 |
| `format` | 否 | 期望输出格式，由供应商校验 |

音频生成成功响应包含 `created`、公开模型别名 `model` 和 `data` 数组；`data[0]` 可能包含 `url`、`audio`、`duration`、`original_duration` 或 `subtitle`，只返回供应商实际提供的字段，响应头包含 `X-Request-Id`。

音频生成示例：

```bash
curl "$BASE_URL/v1/audio/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-audio-1.0","prompt":"雨夜咖啡馆，轻柔爵士乐与窗外雨声","format":"mp3"}'
```

响应可能包含临时 `url` 或音频 Base64。临时 URL 由供应商托管并可能过期，调用方应及时下载；中转站不会自动归档媒体。
