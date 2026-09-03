# 瑞池 AI 模型与素材 API 接入文档

版本：5.0

更新日期：2026-09-03
正式地址：`https://api.richbest.cn`

本文档面向直接通过 HTTP API 接入的客户，不依赖控制台或其他前端页面。当前文档描述素材上传、方舟素材库管理、OpenAI 兼容文本与图片接口，以及火山方舟兼容的 Seedance 视频任务接口。

客户业务 API 不返回模型价目、项目折扣、账单或支付信息。项目计费由管理员在内部控制台统一配置，不需要也不支持客户为每个 API Key 单独设置；内部管理接口另见 [管理端计费账单 API 文档](ADMIN_BILLING_API.md)。

## 1. 鉴权

除 `/health` 外，请求都必须携带瑞池签发的业务 API Key：

```http
Authorization: Bearer vap_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Accept: application/json
```

JSON 请求还需携带 `Content-Type: application/json`。

业务 API Key 已在服务端绑定火山项目。请求中不需要、也不能覆盖 `projectName`。请只在服务端保存 API Key，不要写入网页代码、公开仓库、日志或 URL。

## 2. 支持的素材规格

| 素材类型 | `assetType` | 扩展名 | MIME 类型 | 大小及媒体要求 |
|---|---|---|---|---|
| 图片 | `Image` | jpg、jpeg、png、webp、bmp、tif、tiff、gif、heic、heif | `image/jpeg`、`image/png`、`image/webp`、`image/bmp`、`image/tiff`、`image/gif`、`image/heic`、`image/heif` | 小于 30 MB；宽高分别大于 300px 且小于 6000px；宽高比大于 0.4 且小于 2.5 |
| 视频 | `Video` | mp4、mov | `video/mp4`、`video/quicktime` | 不超过 200 MB；2～30 秒；24～60 FPS；宽高分别为 300～6000px；宽高比为 0.4～2.5；总像素数为 407,696～8,295,044 |
| 音频 | `Audio` | wav、mp3 | `audio/wav`、`audio/mpeg` | 不超过 15 MB；2～30 秒 |

服务端会检查真实媒体内容，而不只检查扩展名或请求声明的 MIME。空文件、损坏文件、伪造 MIME、扩展名不匹配以及超出规格的媒体都会在上传阶段被拒绝。

## 3. 推荐接入流程

1. 调用 `/api/auth/me` 验证业务 API Key；
2. 调用 `/api/asset-group/create` 创建素材组并保存素材组 ID；
3. 调用 `/api/asset/upload-file` 上传本地文件，保存 `url`、`uploadId` 和 `assetType`；
4. 调用 `/api/asset/create`，使用上一步的三个字段登记素材；
5. 使用 `/api/asset/get` 或 `/api/asset/list` 轮询方舟处理状态；
6. 状态为 `Active` 后再使用该素材；状态为 `Failed` 时读取方舟返回的失败信息；
7. 不再使用时调用 `/api/asset/delete` 删除素材。

上传文件和登记素材是两个独立步骤。只调用上传接口不会自动创建方舟素材。

方舟登记是异步处理。`CreateAsset` 请求成功只代表方舟已接收任务，不代表素材已经可用。素材可能经历 `Processing`，最终变为 `Active` 或 `Failed`。

## 4. 基础接口

### 4.1 健康检查

```bash
curl "https://api.richbest.cn/health"
```

该接口无需鉴权。

### 4.2 验证 API Key

```bash
export BASE_URL="https://api.richbest.cn"
export API_KEY="vap_live_xxx"

curl "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $API_KEY"
```

成功响应示例：

```json
{
  "authenticated": true,
  "apiKeyId": "3ee92a25-4dd8-42c6-9af5-b8d74891f870",
  "projectName": "customer_project"
}
```

## 5. 上传本地素材

接口为 `POST /api/asset/upload-file`，请求类型是 `multipart/form-data`，表单字段名固定为 `file`。不要手动填写 multipart boundary，应交给 HTTP 客户端生成。

### 5.1 上传图片

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./portrait.heic;type=image/heic"
```

### 5.2 上传视频

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./reference.mp4;type=video/mp4"
```

### 5.3 上传音频

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./voice.mp3;type=audio/mpeg"
```

图片成功响应示例：

```json
{
  "url": "https://cdn.example.com/avatar-assets/customer_project/xxx-portrait.png",
  "uploadId": "upload_0123456789abcdef",
  "objectKey": "avatar-assets/customer_project/xxx-portrait.png",
  "assetType": "Image",
  "contentType": "image/png",
  "size": 284931,
  "mediaMetadata": {
    "width": 1024,
    "height": 1024,
    "frames": 1
  },
  "etag": "xxxxxxxx",
  "requestId": "xxxxxxxx"
}
```

视频的 `mediaMetadata` 包含 `width`、`height`、`duration` 和 `fps`；音频包含 `duration`。

未成功登记的上传文件会按照服务端清理规则回收。后续登记时建议始终同时传递 `url`、`uploadId` 和 `assetType`。

## 6. 素材组

### 6.1 创建素材组

```bash
curl -X POST "$BASE_URL/api/asset-group/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "客户素材",
    "description": "图片、视频和音频参考素材"
  }'
```

请保存响应中的素材组 ID，例如 `group-xxxxxxxx`。

### 6.2 查询素材组列表

```bash
curl "$BASE_URL/api/asset-group/list?pageNumber=1&pageSize=20" \
  -H "Authorization: Bearer $API_KEY"
```

可选参数包括 `name` 和可重复传递的 `groupIds`。

### 6.3 查询、修改和删除素材组

```bash
curl "$BASE_URL/api/asset-group/get?groupId=group-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"

curl -X PUT "$BASE_URL/api/asset-group/update" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"groupId":"group-xxxxxxxx","name":"已审核素材"}'

curl -X DELETE "$BASE_URL/api/asset-group/delete?groupId=group-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

## 7. 登记素材

接口：`POST /api/asset/create`

| 字段 | 必填 | 说明 |
|---|---:|---|
| `groupId` | 是 | 目标素材组 ID |
| `url` | 是 | HTTP(S) 素材地址；本地上传时使用上传响应中的 `url` |
| `uploadId` | 否 | 上传响应中的关联 ID；本地上传的新客户端建议必传 |
| `assetType` | 建议必传 | 只允许 `Image`、`Video`、`Audio`；省略时兼容旧客户端并默认 `Image` |
| `name` | 否 | 素材名称，最多 64 个字符 |

当提供 `uploadId` 时，服务端会校验它属于当前项目和当前 API Key，`url` 与上传记录完全一致，并且 `assetType` 与服务端识别出的真实素材类型一致。

### 7.1 登记图片

```bash
curl -X POST "$BASE_URL/api/asset/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "groupId": "group-xxxxxxxx",
    "url": "https://cdn.example.com/avatar-assets/customer_project/xxx-portrait.png",
    "uploadId": "upload_image_xxx",
    "assetType": "Image",
    "name": "人物正面照"
  }'
```

### 7.2 登记视频

```bash
curl -X POST "$BASE_URL/api/asset/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "groupId": "group-xxxxxxxx",
    "url": "https://cdn.example.com/avatar-assets/customer_project/xxx-reference.mp4",
    "uploadId": "upload_video_xxx",
    "assetType": "Video",
    "name": "动作参考视频"
  }'
```

### 7.3 登记音频

```bash
curl -X POST "$BASE_URL/api/asset/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "groupId": "group-xxxxxxxx",
    "url": "https://cdn.example.com/avatar-assets/customer_project/xxx-voice.mp3",
    "uploadId": "upload_audio_xxx",
    "assetType": "Audio",
    "name": "角色声音"
  }'
```

也可以不经过上传接口，直接登记符合方舟要求且可公网访问的 HTTP(S) URL。此时不传 `uploadId`，但必须正确传递 `assetType`。

## 8. 轮询状态

### 8.1 查询单个素材

```bash
curl "$BASE_URL/api/asset/get?assetId=asset-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

建议每 2～5 秒查询一次，不要高频并发轮询：

- `Processing`：仍在方舟处理，暂不可用于后续任务；
- `Active`：处理完成，可以使用；
- `Failed`：处理失败，不应继续使用该素材 ID。

如果 `CreateAsset` 成功后立即使用素材，可能收到 `The asset is still processing and is not available yet`。这表示异步处理尚未结束，不是人工审核入口缺失。

### 8.2 查询素材列表

```bash
curl "$BASE_URL/api/asset/list?groupId=group-xxxxxxxx&pageNumber=1&pageSize=20" \
  -H "Authorization: Bearer $API_KEY"
```

可选参数：`name`、可重复传递的 `statuses`、`sortBy` 和 `sortOrder`。

## 9. 修改和删除素材

```bash
curl -X PUT "$BASE_URL/api/asset/update" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assetId":"asset-xxxxxxxx","name":"新素材名称"}'

curl -X DELETE "$BASE_URL/api/asset/delete?assetId=asset-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

修改后的素材名称最多 64 个字符。删除成功后，本系统会同时清理与该登记记录关联的 TOS 对象；删除操作可能无法恢复。

## 10. Seedance 视频生成

视频接口采用火山方舟与漫剧一致的任务路径和请求结构，但鉴权、模型名称和任务 ID 由本中转站管理：

```text
POST   /api/v3/contents/generations/tasks
GET    /api/v3/contents/generations/tasks/{taskId}
DELETE /api/v3/contents/generations/tasks/{taskId}
```

调用方仍使用瑞池业务 API Key，不提交火山 API Key。`model` 必须填写 `/v1/models` 返回的稳定别名，例如 `seedance-2.0`；服务端会把别名转换为固定的火山 Model ID，并使用该项目绑定渠道的加密凭证请求火山。客户端不能覆盖真实模型 ID、供应商、渠道、项目或 Base URL。

### 10.1 创建任务

```bash
curl -X POST "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: video-order-20260903-001" \
  -d '{
    "model": "seedance-2.0",
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

`content` 支持文本以及模型能力允许的图片、视频和音频引用。素材 URL 可使用 HTTP(S) URL 或当前项目可访问的 `asset://` ID；图片和音频还支持合法 Data URL。图片角色为 `first_frame`、`last_frame` 或 `reference_image`，视频角色为 `reference_video`，音频角色为 `reference_audio`。各模型可用素材类型、条目数量、分辨率和时长以 `/v1/models` 返回的能力为准。

可选字段包括 `duration`、`frames`、`resolution`、`ratio`、`generate_audio`、`draft`、`seed`、`camera_fixed`、`watermark`、`return_last_frame`、`service_tier`、`execution_expires_after` 和 `task_type`。不支持或不属于兼容契约的字段返回 `422`，不会盲目转发。

成功响应只返回中转站任务 ID：

```json
{"id": "vid_0123456789abcdef"}
```

相同业务 Key 使用相同 `Idempotency-Key` 和相同请求体会复用同一任务；同一个键对应不同请求体时返回 `409 idempotency_key_conflict`。

### 10.2 查询任务

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

成功任务示例：

```json
{
  "id": "vid_0123456789abcdef",
  "model": "seedance-2.0",
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

状态为 `queued`、`running`、`succeeded`、`failed` 或 `cancelled`。只有创建任务的同一枚业务 Key 可以查询；同项目的另一枚 Key 也不能读取该任务。供应商结果 URL 可能过期，中转站不会自动转存 TOS，请及时下载。

### 10.3 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

取消成功返回 `204 No Content`。中转站会向原任务固定的火山渠道发送取消请求，不会因渠道凭证后续轮换而改用其他渠道。

## 11. 错误处理

本系统校验错误示例：

```json
{
  "error": {
    "code": "upload_asset_type_mismatch",
    "message": "assetType 与已上传文件的真实类型不匹配"
  }
}
```

| HTTP 状态 | 错误码 | 说明 |
|---:|---|---|
| 400 | `empty_file` | 文件为空 |
| 400 | `invalid_file_extension` | 扩展名与声明格式不匹配 |
| 400 | `invalid_media_content` | 文件损坏或不是真实的受支持媒体 |
| 400 | `media_type_mismatch` | 真实内容与声明 MIME 不一致 |
| 400 | `invalid_image_dimensions` / `invalid_image_ratio` | 图片规格不符合要求 |
| 400 | `invalid_video_dimensions` / `invalid_video_ratio` / `invalid_video_pixels` | 视频画面规格不符合要求 |
| 400 | `invalid_video_duration` / `invalid_video_fps` | 视频时长或帧率不符合要求 |
| 400 | `invalid_audio_duration` | 音频时长不符合要求 |
| 401 | `missing_api_key` / `invalid_api_key` | API Key 缺失或无效 |
| 404 | `upload_not_found` | `uploadId` 不存在或不属于当前 API Key |
| 409 | `upload_url_mismatch` | `uploadId` 与 `url` 不一致 |
| 409 | `upload_asset_type_mismatch` | `assetType` 与真实上传类型不一致 |
| 413 | `file_too_large` | 文件超过对应类型的大小上限 |
| 415 | `unsupported_media_type` | 不支持该 MIME 类型 |
| 429 | `quota_exceeded` / `rate_limit_exceeded` | 项目或 API Key 额度不足 |

方舟返回的错误响应会原样透传，包括 `ResponseMetadata.Error.Code`、`ResponseMetadata.Error.Message` 和 `RequestId`。排查问题时请保留完整响应以及 `RequestId`，但不要提供业务 API Key。

## 12. 接口总览

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/auth/me` | 验证 API Key |
| `POST` | `/api/asset/upload-file` | 上传图片、视频或音频 |
| `POST` | `/api/asset-group/create` | 创建素材组 |
| `GET` | `/api/asset-group/list` | 查询素材组列表 |
| `GET` | `/api/asset-group/get` | 查询单个素材组 |
| `PUT` | `/api/asset-group/update` | 修改素材组 |
| `DELETE` | `/api/asset-group/delete` | 删除素材组 |
| `POST` | `/api/asset/create` | 登记图片、视频或音频 |
| `GET` | `/api/asset/list` | 查询素材列表和状态 |
| `GET` | `/api/asset/get` | 查询单个素材和状态 |
| `PUT` | `/api/asset/update` | 修改素材名称 |
| `DELETE` | `/api/asset/delete` | 删除素材 |
| `GET` | `/v1/models` | 查询当前业务 Key 可用模型 |
| `POST` | `/v1/chat/completions` | OpenAI 兼容文本对话，支持 JSON/SSE |
| `POST` | `/v1/responses` | OpenAI 兼容 Responses，支持 JSON/SSE |
| `POST` | `/v1/images/generations` | OpenAI 兼容图片生成 |
| `POST` | `/api/v3/contents/generations/tasks` | 创建 Seedance 异步视频任务 |
| `GET` | `/api/v3/contents/generations/tasks/{taskId}` | 查询 Seedance 视频任务 |
| `DELETE` | `/api/v3/contents/generations/tasks/{taskId}` | 取消 Seedance 视频任务 |

## 13. 多供应商 OpenAI 兼容模型接口

该能力由管理员按客户项目启用。管理员完成“供应商渠道 → 项目模型绑定”后，该项目下所有有效的 `vap_live_*` 都能调用项目已启用的模型，无需逐 Key 授权或重新签发 Key。客户不能在请求中指定供应商、渠道、项目、Base URL 或真实上游模型 ID。

### 13.1 可用模型

```bash
curl "$BASE_URL/v1/models" \
  -H "Authorization: Bearer $API_KEY"
```

只返回当前 Key 所属项目已绑定且渠道处于启用状态的模型。内置别名如下；实际是否可用以该接口返回为准：

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

| 对外模型别名 | 能力 | 供应商 | 发起请求接口 | 响应方式或结果接口 |
|---|---|---|---|---|
| `deepseek-v4-flash` | 文本对话 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `glm-5.2` | 文本对话 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `doubao-seed-2.1-pro` | 文本、识图 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `doubao-seed-2.1-turbo` | 文本、识图 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `doubao-seed-2.0-pro` | 文本、识图 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `doubao-seed-2.0-lite` | 文本、识图 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `doubao-seed-2.0-mini` | 文本、识图 | 火山方舟 | `POST /v1/chat/completions`<br>`POST /v1/responses` | JSON 或 SSE 流式响应 |
| `seedream-5.0-pro` | 生图、参考图改图；最多 10 张参考图，单次 1 张结果 | 火山方舟 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 |
| `seedream-5.0-lite` | 生图、参考图改图、组图；最多 10 张参考图、15 张结果 | 火山方舟 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 |
| `seedream-5.0` | 生图、参考图改图；最多 10 张参考图，单次 1 张结果 | 火山方舟 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 |
| `seedream-4.5` | 生图、参考图改图、组图；最多 10 张参考图、15 张结果 | 火山方舟 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 |
| `seedream-4.0` | 生图、参考图改图、组图；最多 10 张参考图、15 张结果 | 火山方舟 | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 |
| `image2.0` | 生图；单次 1 张结果 | OpenAI | `POST /v1/images/generations` | 同步 JSON；结果为 URL 或 Base64 |
| `seedance-2.5` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| `seedance-2.0` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| `seedance-2.0-fast` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| `seedance-2.0-mini` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| `seedance-1.5-pro` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| `seedance-1.0-pro` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| `seedance-1.0-pro-fast` | 异步视频 | 火山方舟 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |

创建、查询和取消视频任务必须使用同一枚业务 API Key。`wan3.0-video` 和 `minimax-h3` 不属于当前火山兼容视频接口的公开范围。

模型是否已经对当前项目开放，以 `/v1/models` 的实时返回结果为准。请求未开通的模型会返回 `403 model_not_allowed`，请联系管理员确认项目授权和供应商渠道状态。

### 13.2 Chat Completions 与 Responses

接口分别为：

```text
POST /v1/chat/completions
POST /v1/responses
```

请求格式兼容对应的 OpenAI JSON/SSE 习惯，`model` 必须使用 `/v1/models` 返回的别名。示例：

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5.2",
    "messages": [{"role": "user", "content": "请用三句话介绍产品"}],
    "stream": false
  }'
```

流式调用把 `stream` 设置为 `true`，响应类型为 `text/event-stream`。每个公开模型别名由服务端固定映射到一个真实上游模型，客户和管理员都不能在请求或项目绑定中覆盖该 ID；中转层会把响应中的真实模型 ID 改回稳定别名。供应商没有返回 `usage` 时，系统不会伪造 Token 数。

流式示例（`-N` 用于关闭 curl 输出缓冲）：

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "用一句话介绍杭州"}],
    "stream": true,
    "stream_options": {"include_usage": true}
  }'
```

服务端逐段透传标准 SSE 数据，并以供应商的结束事件为准。客户端应逐行消费 `data:` 事件，不能等待整个响应完成后再一次性解析。流式连接中断后，服务端不会自动重放写请求；供应商没有返回最终 `usage` 时，用量字段保持未知。

Responses 示例：

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5.2",
    "input": "列出三条新品发布检查项",
    "stream": false
  }'
```

文本接口会拒绝未列入兼容白名单的顶层字段，并返回 `422 text_parameter_unsupported`。请求中出现 `provider`、`channel`、`base_url`、`api_key`、`project` 或 `project_name` 等内部路由字段时返回 `422 route_override_forbidden`。

识图模型使用 OpenAI 兼容的图文消息，例如：

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2.0-lite",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://customer.example.com/product.jpg"}},
        {"type": "text", "text": "描述图片中的商品和可见文字"}
      ]
    }],
    "stream": false
  }'
```

只有 `/v1/models` 返回的 `capabilities.imageInput=true` 模型接受图片内容；其他文本模型传入图片会返回 `model_image_input_unsupported`。

### 13.3 图片生成

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: image-order-20260902-001" \
  -d '{
    "model": "seedream-5.0-lite",
    "prompt": "白色背景上的东方瓷器产品摄影",
    "image": "https://customer.example.com/reference.jpg",
    "n": 1,
    "response_format": "url"
  }'
```

`image` 可填写单个 HTTP(S) 图片 URL、图片 Data URL 或 URL 数组，具体数量由 `/v1/models` 的 `maxInputImages` 决定。`n` 必须是 1～15 的整数，并且不能超过该模型返回的 `maxN`；`n>1` 只在支持组图的 Seedream 模型上生效，中转层会转换为方舟组图参数。还可按模型能力使用 `size`、`output_format`、`watermark`、`sequential_image_generation`、`sequential_image_generation_options`、`optimize_prompt_options` 和 `tools`。不支持的模型能力会返回明确的 `422`，不会盲目透传。

图片接口不会把 OpenAI 的 `quality`、`style`、`user` 等供应商无关字段转发给方舟。当前公开接口只提供非流式 JSON 响应；传入 `stream=true` 会返回 `image_stream_unsupported`。返回 URL 属于供应商临时资源，本系统不会自动转存到 TOS，请在供应商有效期内下载。

成功响应示例：

```json
{
  "created": 1788336000,
  "model": "seedream-5.0-lite",
  "data": [
    {"url": "https://provider.example.com/result.png"}
  ],
  "usage": {
    "generated_images": 1
  }
}
```

以实际响应为准：供应商没有返回的 `usage` 字段不会被补零。使用 `url` 时应及时下载结果；使用 `b64_json` 时，响应体可能明显增大。

### 13.4 Seedance 视频

Seedance 不使用 OpenAI `/v1/videos` 路径；创建、查询和取消统一使用第 10 节的火山兼容 `/api/v3/contents/generations/tasks` 接口。请求中的 `model` 仍使用中转站稳定别名，服务端负责转换为当前固定的火山 Model ID。

### 13.5 幂等与错误

图片和视频创建支持 `Idempotency-Key`，长度为 1～128 个字符：

- 同一业务 Key、同一操作、相同 Idempotency-Key 和相同请求体：返回已有结果或任务，不重复创建；
- 相同 Idempotency-Key 但请求体不同：返回 `409 idempotency_key_conflict`；
- 已有相同图片请求仍在处理中或此前失败：返回 `409`，避免不确定地重复计费。

`/v1/*` 使用 OpenAI 风格错误并附带请求 ID：

```json
{
  "error": {
    "message": "当前项目未启用该模型或渠道不可用",
    "type": "invalid_request_error",
    "param": null,
    "code": "model_not_allowed"
  },
  "request_id": "req_0123456789abcdef"
}
```

常见错误：

| HTTP | 错误码 | 说明 |
|---:|---|---|
| `401` | `missing_api_key` / `invalid_api_key` | 业务 Key 缺失、无效或已禁用 |
| `403` | `model_not_allowed` | Key 未授权、项目未绑定或渠道已禁用 |
| `409` | `idempotency_key_conflict` | 幂等键被用于不同请求体 |
| `422` | `model_modality_mismatch` | 模型与文本、图片或视频接口不匹配 |
| `422` | `model_image_input_unsupported` | 当前文本或生图模型不接受参考图片 |
| `422` | `image_input_required` | 当前图片编辑模型缺少必需的参考图片 |
| `422` | `image_input_invalid` / `image_input_count_invalid` | 参考图片格式或数量不符合模型能力 |
| `422` | `image_count_unsupported` / `image_sequence_unsupported` | 当前图片模型不支持请求的单次数量或组图参数 |
| `422` | `image_stream_unsupported` | 当前中转图片接口不提供流式响应 |
| `422` | `text_parameter_unsupported` / `image_parameter_unsupported` | 请求包含当前接口未开放的字段 |
| `422` | `stream_parameter_invalid` | `stream` 不是布尔值 |
| `422` | `idempotency_key_invalid` | 幂等键为空或超过 128 个字符 |
| `422` | `video_input_required` / `video_content_invalid` | 视频请求缺少 `content` 或条目格式无效 |
| `422` | `video_parameter_unsupported` / `video_duration_invalid` / `video_resolution_invalid` | 当前 Seedance 模型不支持请求参数 |
| `422` | `route_override_forbidden` | 请求试图覆盖内部路由字段 |
| `404` | `video_task_not_found` | 任务不存在，或任务不属于当前业务 Key |
| `502` | `provider_unreachable` / `provider_request_failed` | 供应商不可达或拒绝请求 |
| `503` | `multi_provider_disabled` | 多供应商功能尚未启用 |

排查 `/v1/*` 时请保留响应体中的 `request_id`；排查 `/api/v3/*` 时请保留响应头 `X-Request-Id`。不要提供业务 Key、供应商 Key 或完整图片/视频私有 URL。
