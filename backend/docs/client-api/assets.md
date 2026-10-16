# 素材接口

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

## 素材接口概览

素材接口归属火山引擎，在目录的“火山引擎 → 素材接口”下查阅。原有接口全部保留：上传 1 项、素材组管理 5 项、素材管理 5 项。接口使用星辰平台业务 Key，素材范围由 Key 所属项目确定，不随项目的模型供应商渠道切换。

素材登记进入火山引擎素材库，`asset://` ID 不能默认跨供应商复用。给 BytePlus、ModelTop 等其他供应商的模型传入参考素材时，应使用目标供应商可访问的媒体 URL 或该模型明确支持的输入格式；不能把火山素材 ID 当作通用文件地址。

素材组和素材管理响应保留 `ResponseMetadata` 和返回结果结构，字段区分大小写。HTTP `2xx` 表示请求已接收；登记素材还需查询状态。保留 `ResponseMetadata.RequestId` 用于排查。上传接口使用下文单独列出的 JSON 结构。

### 支持的素材规格

| 素材类型 | `assetType` | 扩展名 | MIME 类型 | 大小及媒体要求 |
|---|---|---|---|---|
| 图片 | `Image` | jpg、jpeg、png、webp、bmp、tif、tiff、gif、heic、heif | `image/jpeg`、`image/png`、`image/webp`、`image/bmp`、`image/tiff`、`image/gif`、`image/heic`、`image/heif` | 小于 30 MiB；宽高分别大于 300px 且小于 6000px；宽高比大于 0.4 且小于 2.5 |
| 视频 | `Video` | mp4、mov | `video/mp4`、`video/quicktime` | 不超过 200 MiB；2～30 秒；24～60 FPS；宽高分别为 300～6000px；宽高比为 0.4～2.5；总像素数为 407,696～8,295,044 |
| 音频 | `Audio` | wav、mp3 | `audio/wav`、`audio/mpeg` | 不超过 15 MiB；2～30 秒 |

`1 MiB = 1,048,576` 字节。以上为类型上限；实际上传还受服务端单文件上限及项目/Key 额度约束，达到限制时返回 `413` 或 `429`。

服务端会检查真实媒体内容，而不只检查扩展名或请求声明的 MIME。空文件、损坏文件、伪造 MIME、扩展名不匹配以及超出规格的媒体都会在上传阶段被拒绝。

### 素材库流程

1. 调用 `/api/asset-group/create` 创建素材组并保存素材组 ID；
2. 调用 `/api/asset/upload-file` 上传本地文件，保存 `url`、`uploadId` 和 `assetType`；
3. 调用 `/api/asset/create`，使用上一步的三个字段登记素材；
4. 使用 `/api/asset/get` 或 `/api/asset/list` 轮询素材处理状态；
5. 状态为 `Active` 后再使用该素材；状态为 `Failed` 时读取返回的失败信息；
6. 视频请求通过 `asset://<assetId>` 引用素材，并根据素材类型填写正确的 `content.type` 和 `role`；
7. 不再使用时调用 `/api/asset/delete` 删除素材。

上传文件和登记素材是两个独立步骤。只调用上传接口不会自动登记素材。

素材登记是异步处理。登记请求成功只代表任务已接收，不代表素材已经可用。素材可能经历 `Processing`，最终变为 `Active` 或 `Failed`。

## 上传本地素材

接口为 `POST /api/asset/upload-file`，请求类型是 `multipart/form-data`，表单字段名固定为 `file`。不要手动填写 multipart boundary，应交给 HTTP 客户端生成。

### 上传图片

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./portrait.heic;type=image/heic"
```

### 上传视频

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./reference.mp4;type=video/mp4"
```

### 上传音频

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

## 创建素材组

`POST /api/asset-group/create`

请求类型：JSON。

| 字段 | 必填 | 约束 |
|---|---:|---|
| `name` | 是 | 1～128 个字符 |
| `description` | 否 | 最多 1000 个字符；省略时为空字符串 |

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

## 查询素材组列表

`GET /api/asset-group/list`

请求参数放在 URL 查询字符串中。

```bash
curl "$BASE_URL/api/asset-group/list?pageNumber=1&pageSize=20" \
  -H "Authorization: Bearer $API_KEY"
```

| 查询参数 | 必填 | 默认值与约束 |
|---|---:|---|
| `pageNumber` | 否 | 默认 `1`，最小为 `1` |
| `pageSize` | 否 | 默认 `20`，范围为 `1`～`100` |
| `name` | 否 | 按名称筛选 |
| `groupIds` | 否 | 可重复传递，例如 `groupIds=g1&groupIds=g2` |

## 查询单个素材组

`GET /api/asset-group/get`

| 查询参数 | 必填 | 类型与约束 |
|---|---|---|
| `groupId` | 是 | 非空字符串；需要查询的素材组 ID |

```bash
curl "$BASE_URL/api/asset-group/get?groupId=group-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

成功返回素材组详情。读取响应中的结果对象，并保留 `ResponseMetadata.RequestId`。

## 修改素材组

`PUT /api/asset-group/update`

请求类型：JSON。

| 字段 | 必填 | 类型与约束 |
|---|---|---|
| `groupId` | 是 | 非空字符串 |
| `name` | 至少提供一项 | 字符串，1～128 个字符 |
| `description` | 至少提供一项 | 字符串，最多 1000 个字符 |

`name`、`description` 至少提供一项；省略的字段不修改。

```bash
curl -X PUT "$BASE_URL/api/asset-group/update" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"groupId":"group-xxxxxxxx","name":"已审核素材"}'
```

以 HTTP `2xx` 判断修改是否成功，响应保留素材服务的 JSON 结构。

## 删除素材组

`DELETE /api/asset-group/delete`

| 查询参数 | 必填 | 类型与约束 |
|---|---|---|
| `groupId` | 是 | 非空字符串；需要删除的素材组 ID |

```bash
curl -X DELETE "$BASE_URL/api/asset-group/delete?groupId=group-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

删除操作可能无法恢复。是否允许删除由服务端素材状态决定；失败时检查 HTTP 状态与返回的错误，不要把请求发出视为已删除。

## 登记素材

接口：`POST /api/asset/create`

| 字段 | 必填 | 说明 |
|---|---:|---|
| `groupId` | 是 | 目标素材组 ID |
| `url` | 是 | HTTP(S) 素材地址，最长 2048 个字符；本地上传时使用上传响应中的 `url` |
| `uploadId` | 否 | 上传响应中的关联 ID，1～64 个字符；本地上传的新客户端建议必传 |
| `assetType` | 建议必传 | 只允许 `Image`、`Video`、`Audio`；省略时兼容旧客户端并默认 `Image` |
| `name` | 否 | 素材名称，最多 64 个字符 |

当提供 `uploadId` 时，服务端会校验它属于当前项目和当前 API Key，`url` 与上传记录完全一致，并且 `assetType` 与服务端识别出的真实素材类型一致。

### 登记图片

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

### 登记视频

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

### 登记音频

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

也可以不经过上传接口，直接登记符合素材规格且可公网访问的 HTTP(S) URL。此时不传 `uploadId`，但必须正确传递 `assetType`。

## 查询单个素材

`GET /api/asset/get`

| 查询参数 | 必填 | 类型与约束 |
|---|---|---|
| `assetId` | 是 | 非空字符串；需要查询的素材 ID |


```bash
curl "$BASE_URL/api/asset/get?assetId=asset-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

建议每 2～5 秒查询一次，不要高频并发轮询：

- `Processing`：仍在处理，暂不可用于后续任务；
- `Active`：处理完成，可以使用；
- `Failed`：处理失败，不应继续使用该素材 ID。

如果 `CreateAsset` 成功后立即使用素材，可能收到 `The asset is still processing and is not available yet`。这表示异步处理尚未结束，不是人工审核入口缺失。

## 查询素材列表

`GET /api/asset/list`


```bash
curl "$BASE_URL/api/asset/list?groupId=group-xxxxxxxx&pageNumber=1&pageSize=20" \
  -H "Authorization: Bearer $API_KEY"
```

| 查询参数 | 必填 | 默认值与约束 |
|---|---:|---|
| `groupId` | 是 | 目标素材组 ID，不能为空 |
| `pageNumber` | 否 | 默认 `1`，最小为 `1` |
| `pageSize` | 否 | 默认 `20`，范围为 `1`～`100` |
| `name` | 否 | 按素材名称筛选 |
| `statuses` | 否 | 可重复传递，例如 `statuses=Active&statuses=Failed` |
| `sortBy` | 否 | 默认 `CreateTime`，按素材服务规则排序 |
| `sortOrder` | 否 | 默认 `Desc`，按素材服务规则排序 |

列表响应使用素材服务的分页结构，素材可用状态以返回的 `Status` 为准，不要从上传成功推断素材已处理完成。

## 修改素材名称

`PUT /api/asset/update`

请求类型：JSON。

| 字段 | 必填 | 类型与约束 |
|---|---|---|
| `assetId` | 是 | 非空字符串 |
| `name` | 是 | 字符串，1～64 个字符 |

```bash
curl -X PUT "$BASE_URL/api/asset/update" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assetId":"asset-xxxxxxxx","name":"新素材名称"}'
```

该接口只修改名称，不替换媒体文件。以 HTTP `2xx` 判断请求是否成功，响应保留素材服务 JSON 结构。

## 删除素材

`DELETE /api/asset/delete`

| 查询参数 | 必填 | 类型与约束 |
|---|---|---|
| `assetId` | 是 | 非空字符串；需要删除的素材 ID |

```bash
curl -X DELETE "$BASE_URL/api/asset/delete?assetId=asset-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

删除成功后会同时清理关联的上传文件，操作可能无法恢复。不要删除仍被生成任务引用的素材；外部 URL 对应的客户源文件不由本接口管理。
