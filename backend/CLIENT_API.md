# 瑞池多类型素材 API 接入文档

版本：4.0
正式地址：`https://api.richbest.cn`

本文档面向直接通过 HTTP API 接入的客户，不依赖控制台或其他前端页面。当前文档描述素材上传、方舟素材库管理、Seedance 聚合用量查询及可选的多供应商 OpenAI 兼容模型接口。

## 1. 鉴权

除 `/health` 外，请求都必须携带瑞池签发的业务 API Key：

```http
Authorization: Bearer vap_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Accept: application/json
```

JSON 请求还需携带 `Content-Type: application/json`。

业务 API Key 已在服务端绑定火山项目。请求中不需要、也不能覆盖 `projectName`。请只在服务端保存 API Key，不要写入网页代码、公开仓库、日志或 URL。

`/api/video/ark-usage` 还需要通过 `X-Ark-Api-Key` 请求头携带客户自己的方舟 API Key。服务端会实时校验该方舟 Key 是否真实存在、处于可用状态，并且与业务 API Key 绑定的是同一个火山项目；方舟 Key 不得放在 URL 中。

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

## 10. 使用方舟 API Key 查询 Seedance 用量

```bash
curl "$BASE_URL/api/video/ark-usage?start=2026-08-01&end=2026-08-18&interval=Day" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Ark-Api-Key: $ARK_API_KEY"
```

参数：

- `start`、`end`：必填，格式为 `YYYY-MM-DD`，单次跨度不能超过 31 天；
- `interval`：可选，`Day` 或 `Hour`，默认 `Day`；
- `Authorization` 必须传瑞池签发的业务 API Key；
- 方舟 API Key 必须放在 `X-Ark-Api-Key` 请求头，不得放入 URL；
- 两枚 Key 绑定的火山项目不一致时返回 `403 ark_key_project_mismatch`；
- 方舟 Key 已禁用或不可用时返回 `403 ark_key_inactive`。

成功响应：

```json
{
  "source": "volcengine_ark",
  "scope": "ark_api_key",
  "keySuffix": "123456789abc",
  "start": "2026-08-01",
  "end": "2026-08-18",
  "interval": "Day",
  "dataDelayMinutes": {"min": 5, "max": 30},
  "billingAmountIncluded": false,
  "summary": {
    "inputTokens": 0,
    "outputTokens": 35800,
    "totalTokens": 35800,
    "requestCount": 2,
    "metrics": {}
  },
  "records": [
    {
      "date": "2026-08-18",
      "modelName": "doubao-seedance-2-5",
      "endpointId": "ep-xxxxxxxx",
      "requestCount": 2,
      "inputTokens": 0,
      "outputTokens": 35800,
      "totalTokens": 35800
    }
  ]
}
```

安全与统计口径：

- 完整方舟 Key 只在当前请求内用于火山用量过滤，不落库、不写业务日志，响应只显示末 12 位；
- 服务端使用 IAM AK/SK 签名查询，并按照方舟 Key 末 12 位过滤 `AuthToken`；AK/SK 不会返回给客户；
- 仅能查到与服务端 IAM 身份处于同一火山账号范围、且该 IAM 身份有权读取的用量；
- 只返回模型名包含 `seedance` 的记录；
- 聚合用量通常延迟 5～30 分钟，不能用于实时限流；
- `billingAmountIncluded: false` 表示不含人民币账单金额；
- 零用量只表示查询区间暂无匹配记录，不能单独证明 Key 一定有效。

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
| `GET` | `/api/video/ark-usage` | 使用业务 Key 鉴权并校验同项目后，查询客户方舟 Key 的 Seedance 聚合用量 |
| `GET` | `/v1/models` | 查询当前业务 Key 可用模型 |
| `POST` | `/v1/chat/completions` | OpenAI 兼容文本对话，支持 JSON/SSE |
| `POST` | `/v1/responses` | OpenAI 兼容 Responses，支持 JSON/SSE |
| `POST` | `/v1/images/generations` | OpenAI 兼容图片生成 |
| `POST` | `/v1/videos` | 创建异步视频任务 |
| `GET` | `/v1/videos/{taskId}` | 查询异步视频任务 |
| `GET` / `HEAD` | `/v1/videos/{taskId}/content` | 获取成功视频的供应商结果地址 |

## 13. 多供应商 OpenAI 兼容模型接口

该能力由管理员按客户项目启用。管理员完成“供应商渠道 → 项目模型绑定”后，该项目下所有有效的 `vap_live_*` 都能调用项目已启用的模型，无需逐 Key 授权或重新签发 Key。客户不能在请求中指定供应商、渠道、项目、Base URL 或真实上游模型 ID。

### 13.1 可用模型

```bash
curl "$BASE_URL/v1/models" \
  -H "Authorization: Bearer $API_KEY"
```

只返回当前 Key 所属项目已绑定且渠道处于启用状态的模型。内置别名如下；实际是否可用以该接口返回为准：

| 对外模型别名 | 类型 | 初始供应商 |
|---|---|---|
| `deepseek-v4-flash` | 文本 | 火山方舟 |
| `glm-5.2` | 文本 | 火山方舟 |
| `doubao-seed-2.1-pro` | 文本、识图 | 火山方舟 |
| `doubao-seed-2.0-pro` | 文本、识图 | 火山方舟 |
| `doubao-seed-2.0-lite` | 文本、识图 | 火山方舟 |
| `doubao-seed-2.0-mini` | 文本、识图 | 火山方舟 |
| `seedream-5.0-pro` | 生图、参考图改图 | 火山方舟 |
| `seedream-5.0-lite` | 生图、参考图改图、组图 | 火山方舟 |
| `seedream-4.5` | 生图、参考图改图、组图 | 火山方舟 |
| `seedream-4.0` | 生图、参考图改图、组图 | 火山方舟 |
| `seedance-2.5` | 异步视频 | 火山方舟 |
| `seedance-2.0` | 异步视频 | 火山方舟 |
| `seedance-2.0-fast` | 异步视频 | 火山方舟 |
| `seedance-2.0-mini` | 异步视频 | 火山方舟 |
| `seedance-1.5-pro` | 异步视频 | 火山方舟 |
| `seedance-1.0-pro` | 异步视频 | 火山方舟 |
| `seedance-1.0-pro-fast` | 异步视频 | 火山方舟 |
| `wan3.0-video` | 异步视频 | 阿里百炼 |
| `minimax-h3` | 异步视频 | MiniMax |
| `image2.0` | 图片 | OpenAI，真实模型由管理员配置 |

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

`image` 可填写单个 HTTP(S) 图片 URL、图片 Data URL 或 URL 数组，具体数量由 `/v1/models` 的 `maxInputImages` 决定。`n>1` 只在支持组图的 Seedream 模型上生效，中转层会转换为方舟组图参数。还可按模型能力使用 `size`、`output_format`、`watermark`、`sequential_image_generation`、`sequential_image_generation_options`、`optimize_prompt_options` 和 `tools`。不支持的模型能力会返回明确的 `422`，不会盲目透传。

图片接口不会把 OpenAI 的 `quality`、`style`、`user` 等供应商无关字段转发给方舟。当前公开接口只提供非流式 JSON 响应；传入 `stream=true` 会返回 `image_stream_unsupported`。返回 URL 属于供应商临时资源，本系统不会自动转存到 TOS，请在供应商有效期内下载。

### 13.4 异步视频

创建任务：

```bash
curl "$BASE_URL/v1/videos" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: video-order-20260902-001" \
  -d '{
    "model": "wan3.0-video",
    "prompt": "海边日出，镜头缓慢向前推进",
    "image": "https://customer.example.com/first-frame.jpg",
    "duration": 8,
    "response_format": "url",
    "metadata": {
      "resolution": "1080P",
      "ratio": "16:9",
      "prompt_extend": true
    }
  }'
```

成功提交返回 HTTP `202` 和本系统任务 ID。查询及获取结果：

```bash
curl "$BASE_URL/v1/videos/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"

curl -I "$BASE_URL/v1/videos/$TASK_ID/content" \
  -H "Authorization: Bearer $API_KEY"
```

统一状态为 `queued`、`running`、`succeeded`、`failed`、`canceled`。`content` 在成功后返回 `307` 到供应商结果 URL；查询任务必须使用创建该任务的同一枚业务 Key。

视频字段支持 `model`、`prompt`、`image`、`duration`、`width`、`height`、`fps`、`seed`、`n=1`、`response_format=url`、`user` 和 `metadata`。`metadata` 只允许模型适配器声明的白名单字段，不能放入凭证、Base URL 或自定义转发参数。

方舟 Seedance 模型使用统一的任务创建与查询接口。基础测试可直接使用顶层 `prompt`、`image` 和 `duration`；高级输入可通过 `metadata.content` 传入方舟原生的文本、图片、视频或音频条目，但中转层仍会根据具体模型能力过滤。支持的方舟元数据字段为 `resolution`、`ratio`、`generate_audio`、`watermark`、`camera_fixed`、`return_last_frame`、`service_tier`、`content`、`draft`、`frames` 和 `execution_expires_after`。

| 模型 | 输入能力 | 时长 | 分辨率 | 特殊限制 |
|---|---|---|---|---|
| `seedance-2.5` | 文本、图片、视频、音频 | 4～30 秒或 `-1` | 480p / 720p / 1080p | 最多 50 项参考内容，支持生成音频 |
| `seedance-2.0` | 文本、图片、视频、音频 | 4～15 秒或 `-1` | 480p / 720p / 1080p | 支持生成音频，不支持 `flex` |
| `seedance-2.0-fast` | 文本、图片、视频、音频 | 4～15 秒或 `-1` | 480p / 720p | 支持生成音频，不支持 1080p 和 `flex` |
| `seedance-2.0-mini` | 文本、图片、视频、音频 | 4～15 秒或 `-1` | 480p / 720p | 轻量低成本，不支持 1080p |
| `seedance-1.5-pro` | 文本、图片 | 4～12 秒或 `-1` | 480p / 720p / 1080p | 支持生成音频和 `draft` |
| `seedance-1.0-pro` | 文本、图片 | 2～12 秒 | 480p / 720p / 1080p | 支持 `frames` |
| `seedance-1.0-pro-fast` | 文本、图片 | 2～12 秒 | 480p / 720p / 1080p | 支持 `frames` |

Seedance 1.0 Lite T2V/I2V 已停止服务，不再出现在模型目录，也不能创建新绑定；升级旧数据库时只保留历史任务引用。

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
| `422` | `route_override_forbidden` | 请求试图覆盖内部路由字段 |
| `502` | `provider_unreachable` / `provider_request_failed` | 供应商不可达或拒绝请求 |
| `503` | `multi_provider_disabled` | 多供应商功能尚未启用 |

排查时请保留响应体中的 `request_id`，但不要提供业务 Key、供应商 Key 或完整图片/视频私有 URL。
