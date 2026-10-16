# 错误处理、幂等与安全重试

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [模型目录](models.md)

## 错误格式

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
| `403` | `model_not_allowed` | 项目未开通模型、未绑定渠道或渠道已禁用 |
| `409` | `idempotency_key_conflict` | 幂等键被用于不同请求体 |
| `422` | `model_modality_mismatch` | 模型与文本、图片或视频接口不匹配 |
| `422` | `model_image_input_unsupported` | 当前文本或生图模型不接受参考图片 |
| `422` | `image_input_required` | 当前图片编辑模型缺少必需的参考图片 |
| `422` | `image_input_invalid` / `image_input_count_invalid` | 参考图片格式或数量不符合模型能力 |
| `422` | `image_input_too_large` | Base64 参考图解码后的真实大小超过当前模型限制 |
| `422` | `image_count_unsupported` / `image_sequence_unsupported` | 当前图片模型不支持请求的单次数量或组图参数 |
| `422` | `image_stream_unsupported` | 当前中转图片接口不提供流式响应 |
| `422` | `text_parameter_unsupported` / `image_parameter_unsupported` | 请求包含当前接口未开放的字段 |
| `422` | `stream_parameter_invalid` | `stream` 不是布尔值 |
| `422` | `idempotency_key_invalid` | 幂等键为空或超过 128 个字符 |
| `422` | `video_input_required` / `video_content_invalid` | 视频请求缺少 `content` 或条目格式无效 |
| `422` | `video_parameter_unsupported` / `video_duration_invalid` / `video_resolution_invalid` | 当前视频模型不支持请求参数 |
| `422` | `video_cancel_unsupported` | 当前视频供应商未开放经过验证的任务取消适配 |
| `422` | `route_override_forbidden` | 请求试图覆盖内部路由字段 |
| `404` | `video_task_not_found` | 任务不存在，或任务不属于当前业务 Key |
| `502` | `provider_unreachable` / `provider_request_failed` | 供应商不可达或拒绝请求 |
| `503` | `multi_provider_disabled` | 多供应商功能尚未启用 |

排查 `/v1/*` 时请保留响应体中的 `request_id`；排查 `/api/v3/*` 时请保留响应头 `X-Request-Id`。不要提供业务 Key、供应商 Key 或完整图片/视频私有 URL。

## 上传与额度错误

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

额度错误分为两种客户可见格式：

- `/api/*` 与 `/api/v3/*` 会在 `error` 中返回 `metric`、`scope`、`limit`、`used`、`resetAt` 和 `requestId`；
- `/v1/*` 保持 OpenAI 风格错误，返回 `error.code=quota_exceeded` 和顶层 `request_id`，不返回上述额度明细。

`scope` 为 `project` 或 `api_key`。按分钟或按日自动恢复的限制会同时返回 `Retry-After` 响应头；素材总量、存储总量等没有固定恢复时间的限制不会返回该响应头，`resetAt` 为 `null`。所有接口还会返回 `X-Request-Id` 响应头，联系支持时应优先提供该值。

`/api/*` 或 `/api/v3/*` 的额度错误示例：

```json
{
  "error": {
    "code": "quota_exceeded",
    "message": "额度已用尽",
    "metric": "writeQpm",
    "scope": "project",
    "limit": 100,
    "used": 100,
    "resetAt": "2026-09-11T10:31:00+08:00",
    "requestId": "req_0123456789abcdef"
  }
}
```

素材服务的错误可能使用 `ResponseMetadata` 结构，包括 `ResponseMetadata.Error.Code`、`ResponseMetadata.Error.Message` 和 `RequestId`。排查问题时请保留完整响应以及 `RequestId`，但不要提供业务 API Key。

## 幂等与断线恢复

图片和视频创建支持 `Idempotency-Key`，长度为 1～128 个字符：

- 同一业务 Key、同一操作、相同 Idempotency-Key 和相同请求体：返回已有结果或任务，不重复创建；
- 相同 Idempotency-Key 但请求体不同：返回 `409 idempotency_key_conflict`；
- 已有相同图片请求仍在处理中或此前失败：返回 `409`，避免不确定地重复计费。

### 等待时间

同步生图、非流式文本/音频及视频提交不再套用普通查询的 30 秒响应等待。默认模型连接等待 10 秒，生成响应的读取等待 1800 秒；流式响应默认允许连续 300 秒没有数据，持续有输出时不限制总生成时长。客户端应分别配置连接和读取等待，不能仍用 30 秒总超时。具体等待上限可由服务方配置；更长等待不保证供应商必定成功。

图片生成请求务必在发起前保存唯一 `Idempotency-Key`、原始请求体及业务 Key 对应关系。不要用 SDK 的自动重试或换一个幂等键重发超时请求。示例：

```bash
curl --connect-timeout 10 --max-time 1900 "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-image-order-001" \
  -d '{"model":"gpt-image-2","prompt":"白色背景上的蓝色杯子","n":1}'
```

浏览器或客户端断线不代表已提交的生图被取消。在当前服务进程仍正常运行时，中转站会继续等待上游，保存成功结果和真实用量。使用**同一业务 Key、同一幂等键、完全相同请求体**再次调用图片接口时：

- 已完成：返回缓存的原结果，不重新调用供应商，也不重复登记用量。
- 仍在执行：返回 `409 idempotency_request_in_progress`；稍后手动查询原请求，不能换键创建另一份。
- 结果不确定：返回 `409 idempotency_outcome_unknown`；请联系管理员核对供应商记录，不能假设没有扣费。
- 同一幂等键配不同请求体：返回 `409 idempotency_key_conflict`。

服务重启无法恢复供应商的同步 HTTP 连接。未完成的生图会保留为结果待核对，不自动重放；未知用量不会按零元处理。没有提供幂等键的请求无法通过上述方式找回，请联系管理员并提供响应中的 `request_id` 或 `X-Request-Id`。

错误区分如下：

| HTTP / 错误码 | 含义与处理 |
|---|---|
| `504 provider_connect_timeout` | 未能及时连接供应商，不等同于模型权限不足 |
| `504 provider_response_timeout` | 响应或请求传输等待超时；检查 `error.details.outcomeUnknown`，为 `true` 时上游可能仍在执行 |
| `502 provider_unreachable` | 连接或响应传输故障；同样检查结果是否未知，不能自动重放 |
| `503 model_capacity_exceeded` | 中转站生图并发已满，本次尚未调用供应商，可按 `Retry-After` 使用原幂等键稍后重试 |

`/v1/*` 错误的 `error.details` 可包含 `phase`（connect/read/write/pool）、`outcomeUnknown` 和 `automaticRetry=false`，不会包含供应商 Key。视频兼容接口的同类错误详情直接位于 `error` 内。网关断开时也可能返回非 JSON 的 502/504；此时按结果未知处理，保留原请求信息，不自动重试。

## 流式错误

流式响应在 HTTP 头发送后发生上游异常，会通过 SSE `data:` 发送含 `error.code`、`error.message` 的事件。客户端必须处理该错误；未收到正常结束标记而连接断开时，仅视为收到部分内容，不能当作完整成功。

## 排查顺序

| 现象 | 首先检查 | 是否直接重试 |
|---|---|---|
| `401` | Key 是否有效，Bearer 格式是否正确 | 先修正鉴权 |
| `403 model_not_allowed` | `/v1/models` 是否包含该模型，联系管理员检查项目 | 不重试未开通模型 |
| `422` | 字段白名单、格式和当前模型能力 | 修正请求后再发起 |
| `429` | 额度、`Retry-After` | 按恢复时间处理 |
| `409` | 幂等键对应请求及结果状态 | 不换键盲目重发 |
| `502/504` 或连接断开 | 请求 ID、结果是否未知 | 先核对，不能自动重放付费请求 |

联系管理员时提供时间、模型别名、HTTP 状态、错误码和请求 ID。不要发送完整业务 Key、供应商凭证、私有媒体 URL 或 Data URL。
