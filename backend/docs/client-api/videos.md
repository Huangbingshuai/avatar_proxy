# 异步视频生成

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

## 视频任务流程

所有视频模型统一使用以下任务接口。请求使用星辰平台业务 Key 和公开模型名称；创建后通过返回的任务 ID 查询结果：

```text
POST   /api/v3/contents/generations/tasks
GET    /api/v3/contents/generations/tasks/{taskId}
DELETE /api/v3/contents/generations/tasks/{taskId}
```

调用方仍使用星辰平台业务 API Key，不提交供应商 API Key。`model` 必须填写 `/v1/models` 返回的稳定别名，例如 `doubao-seedance-2.0`、`wan3.0-video` 或 `minimax-h3`；服务端会把别名转换为固定的上游模型 ID，并使用该项目绑定渠道的加密凭证请求对应供应商。客户端不能覆盖真实模型 ID、供应商、渠道、项目或 Base URL。

## 创建任务

`POST /api/v3/contents/generations/tasks`

```bash
curl -X POST "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: video-order-20260903-001" \
  -d '{
    "model": "doubao-seedance-2.0",
    "content": [
      {"type": "text", "text": "海边日出，镜头缓慢向前推进"},
      {
        "type": "image_url",
        "image_url": {"url": "asset://asset-example"},
        "role": "reference_image"
      }
    ],
    "task_type": "i2v",
    "ratio": "16:9",
    "resolution": "720p",
    "duration": 5,
    "generate_audio": true,
    "watermark": false
  }'
```

`content` 支持文本以及模型能力允许的图片、视频和音频引用。国内 Seedance 模型可使用 HTTP(S) URL、当前项目可访问的 `asset://` ID，以及合法的图片或音频 Data URL；阿里百炼和 MiniMax 当前只接受 HTTP(S) 图片 URL。图片角色为 `first_frame`、`last_frame` 或 `reference_image`，视频角色为 `reference_video`，音频角色为 `reference_audio`。阿里 `wan3.0-video` 当前最多接受一张 `first_frame` 图片。各模型可用素材类型、条目数量、分辨率和时长以 `/v1/models` 返回的能力为准。

可选字段包括 `duration`、`frames`、`resolution`、`ratio`、`generate_audio`、`draft`、`seed`、`camera_fixed`、`watermark`、`return_last_frame`、`service_tier`、`execution_expires_after`、`task_type` 和 `output_format`。不支持或不属于兼容契约的字段返回 `422`，不会盲目转发。

成功响应只返回中转站任务 ID：

```json
{"id": "vid_0123456789abcdef"}
```

相同业务 Key 使用相同 `Idempotency-Key` 和相同请求体会复用同一任务；同一个键对应不同请求体时返回 `409 idempotency_key_conflict`。

## 渠道与模型参数

对外路径保持一致，但不同供应商实际支持的素材和参数不同。客户端应先调用 `/v1/models`，只使用当前项目实际返回的模型。

| 模型 | `content` | 支持的创建参数 | 当前默认值 |
|---|---|---|---|
| `doubao-seedance-*` | 文本；能力允许的图片、视频、音频 | `duration`、`frames`、`resolution`、`ratio`、`generate_audio`、`draft`、`seed`、`camera_fixed`、`watermark`、`return_last_frame`、`service_tier`、`execution_expires_after`、`task_type`；具体以模型能力为准 | 由对应 Seedance 模型决定 |
| `dreamina-seedance-2.5` | 文本、图片、视频、音频 | `duration`（4～30 或 -1）、`resolution`（480p/720p/1080p）、`ratio`、`generate_audio`、`watermark`、`return_last_frame`、`service_tier=default`、`execution_expires_after`、`output_format`（mp4/mov） | 默认由上游决定；可省略时长 |
| `dreamina-seedance-2.0` | 文本、图片、视频；参考音频需搭配参考图或视频 | `duration`（4～15 或 -1）、`resolution`（480p/720p/1080p）、`ratio`、`generate_audio`、`watermark`、`service_tier=default`、`execution_expires_after` | 默认由上游决定 |
| `dreamina-seedance-2.0-fast`、`dreamina-seedance-2.0-mini` | 同海外 2.0 | 同海外 2.0，但分辨率仅 480p/720p | 默认由上游决定 |
| `wan3.0-video` | 文本；最多一张 HTTP(S) 首帧图片，角色必须为 `first_frame` | `duration`、`resolution`、`ratio`、`generate_audio`、`watermark` | `resolution=1080P`、`ratio=adaptive`、`generate_audio=true`；服务端固定启用提示词扩写 |
| `minimax-h3` | 文本和 HTTP(S) 图片；总计不超过 20 项 | `duration`、`resolution`、`ratio`、`seed`、`watermark` | `resolution=768P`、`ratio=adaptive` |

公共字段不代表所有模型都支持。比如给 `wan3.0-video` 传 `seed`，或给 `minimax-h3` 传 `generate_audio`，会返回 `422 video_parameter_unsupported`，不会把未知参数直接传给供应商。

海外视频不接受 `seed`、`camera_fixed`、`frames`、`draft` 或 `service_tier=flex`。2.5 全能参考最多 30 张图片、10 个视频、10 段音频；2.0 系列最多 9 张图片、3 个视频、3 段音频；首末帧不能与全能参考混用。仅填写末帧而缺少首帧会返回 `422`。本系统素材库中的国内素材库的 `asset://` ID 不能直接用于海外模型，请传海外服务可访问的 HTTP(S) 素材地址、合法的图片/音频 Data URL，或海外同一账号可用的素材 ID。

海外视频示例（更换 `model` 即可使用另外三款，参数需在对应能力范围内）：

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: dreamina-order-001" \
  -d '{
    "model": "dreamina-seedance-2.5",
    "content": [{"type": "text", "text": "晨光下的海面，镜头缓慢推进"}],
    "duration": 5,
    "resolution": "720p",
    "ratio": "16:9",
    "generate_audio": true
  }'
```

阿里百炼示例：

```bash
curl -X POST "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: wan-video-order-001" \
  -d '{
    "model": "wan3.0-video",
    "content": [
      {"type": "text", "text": "海边日出，镜头缓慢推进"},
      {
        "type": "image_url",
        "image_url": {"url": "https://example.com/first-frame.jpg"},
        "role": "first_frame"
      }
    ],
    "resolution": "1080P",
    "ratio": "16:9",
    "duration": 8,
    "generate_audio": false,
    "watermark": false
  }'
```

MiniMax 示例：

```bash
curl -X POST "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: minimax-video-order-001" \
  -d '{
    "model": "minimax-h3",
    "content": [
      {"type": "text", "text": "人物向镜头走来，电影感运镜"}
    ],
    "resolution": "768P",
    "ratio": "adaptive",
    "duration": 6,
    "seed": 12,
    "watermark": false
  }'
```

供应商参数转换在中转站内部完成。客户不能也不需要提交阿里的 `input` / `parameters`、MiniMax 的真实任务路径或任何供应商 API Key。

## 查询任务

`GET /api/v3/contents/generations/tasks/{taskId}`

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

成功任务示例：

```json
{
  "id": "vid_0123456789abcdef",
  "model": "doubao-seedance-2.0",
  "status": "succeeded",
  "created_at": 1788422400,
  "resolution": "720p",
  "ratio": "16:9",
  "duration": 5,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  },
  "usage": {
    "completion_tokens": 1200,
    "total_tokens": 1200
  }
}
```

状态为 `queued`、`running`、`succeeded`、`failed` 或 `cancelled`。只有创建任务的同一枚业务 Key 可以查询；同项目的另一枚 Key 也不能读取该任务。供应商结果 URL 可能过期，中转站不会自动归档，请及时下载。

所有渠道都使用星辰平台返回的任务 ID 和上述统一响应结构查询，不应使用该 ID 直接访问供应商。

`succeeded` 任务如返回 `usage.completion_tokens`，其值为上游真实输出 Token，不能由客户端按时长伪造。Seedance 按输出 Token 和对应维度计价；其他供应商以 `/v1/pricing` 的 `metric` 为准。同一响应中的 `resolution` 用于确定适用维度。供应商可能额外返回本系统未承诺的字段，调用方应只解析本文档列出的字段并忽略其余内容。

## 取消任务

`DELETE /api/v3/contents/generations/tasks/{taskId}`

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

国内 Seedance 和海外 BytePlus 渠道任务取消成功返回 `204 No Content`。中转站会向原任务固定渠道发送取消请求，不会因渠道凭证后续轮换而改用其他渠道。阿里百炼和 MiniMax 当前未开放经过本系统验证的取消适配，调用取消接口会返回 `422 video_cancel_unsupported`，且不会把仍可能在上游执行的任务伪装为已取消。海外上游仅允许取消排队中的任务，运行中任务可能被上游拒绝取消。

## ModelTop 视频

标准的 `dreamina-seedance-2.5`、`dreamina-seedance-2.0`、`dreamina-seedance-2.0-fast`、`dreamina-seedance-2.0-mini`，以及各自的 `-filter-off` 别名均使用相同的创建和查询接口。标准别名可能绑定 BytePlus 或 ModelTop；以下差异仅适用于 ModelTop 渠道。

对上述八个视频模型，调用 `POST /api/v3/contents/generations/tasks`，分别替换以下 `model`：

```json
{"model":"dreamina-seedance-2.5","content":[{"type":"text","text":"一艘红色纸船缓缓漂过池塘"}],"duration":4,"resolution":"480p","ratio":"16:9","generate_audio":false}
```

用同一业务 Key 查询 `GET /api/v3/contents/generations/tasks/{taskId}`，`succeeded` 才表示成功。2.5 支持4～30秒，其他4～15秒，均支持 `duration=-1`。2.5支持480p/720p/1080p；2.0另支持 `4k`；Fast/Mini仅480p/720p。参考素材使用 `content` 的 `image_url/video_url/audio_url` 及对应 role；2.5最多30图/10视频/10音频，其他9图/3视频/3音频。首末帧不能与全能参考混用，2.0系列的音频须搭配图或视频。当前不开放取消、草稿、回调或联网工具；素材ID不能保证跨供应商复用，结果URL可能过期。

## 参数与轮询注意事项

- `model` 和 `content` 必填；`content` 是内容数组，至少包含模型允许的文本或参考素材。
- 画幅只使用 `ratio`，不使用 `aspect_ratio`。首帧、末帧、全能参考的角色不能随意混用。
- `duration=-1` 只适用于声明支持智能时长的模型；最终时长、Token 以任务结果为准。
- 国内 1.0 Pro / Pro Fast 的时长能力为 2～12 秒；2.0 系列为 4～15 秒，2.5 为 4～30 秒。可选分辨率以 `/v1/models` 的 `resolutions` 为准。
- 创建成功只表示收到任务 ID。保存 `vid_*`，使用创建任务的同一业务 Key，每 5～10 秒查询一次，直到终态。
- 视频没有 `/v1/videos` 接口。查询与取消使用中转站 ID，不使用上游 ID。
- 海外视频 URL 有效期通常为 24 小时，上游任务记录一般只能查询最近 7 天；请及时保存结果。
- 创建返回未知结果时不要自动提交第二个任务；见[幂等与断线恢复](errors.md#幂等与断线恢复)。
