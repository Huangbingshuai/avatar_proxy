# RichiDrama 对接 Star Proxy 改造说明

本文档用于指导 RichiDrama 将文本、图片和视频生成从“直接调用供应商”切换为统一调用 Star Proxy。本文档只规定 RichiDrama 侧的改造和验收，不重新定义中转站接口；完整公开路径、请求字段、响应结构和错误码以 [CLIENT_API.md](CLIENT_API.md) 为准，[MODEL_RELAY_API.md](MODEL_RELAY_API.md) 仅作为模型中转快速接入说明。

本文档基于 RichiDrama `main@de5cdc36a75950b48b8f95a2242e1b56dd745bf3`（2026-09-04）重新核对。RichiDrama 后续代码发生变化时，应重新检查本文列出的调用点。

当前审计结论：RichiDrama 已通过 `richbest_asset_v3` 接入 Star Proxy 素材库，但文本、图片和视频生成仍使用原有供应商配置与调用路径，尚未完成模型中转切换。素材接入和模型中转是两套配置；可以使用同一枚业务 Key，但不能把素材服务类型直接当成模型供应商实现。

## 1. 对接目标

目标调用链：

```text
RichiDrama 浏览器
  → RichiDrama 后端
  → Star Proxy（https://api.richbest.cn）
  → Star Proxy 为项目绑定的火山方舟、阿里百炼或 MiniMax 渠道
```

对接完成后应满足：

- RichiDrama 前端用户只选择模型，不接触供应商 Key、火山项目或真实 Model ID。
- RichiDrama 后端只保存一枚 Star Proxy 生产业务 Key，例如 `vap_live_xxx`。
- 整套 ToC 漫剧系统对应一个 Star Proxy 客户项目，不按终端用户创建火山项目或业务 Key。
- 文本、图片和视频请求中的 `model` 直接使用 Star Proxy 返回的稳定别名。
- 真实供应商、渠道、上游凭证、火山 ProjectName 和真实模型版本全部由 Star Proxy 决定。
- RichiDrama 继续维护自己的用户、积分、订单、生成记录和内部计费；Star Proxy 用量按漫剧项目汇总，不负责识别漫剧终端用户。

以下内容不属于本次对接：

- TTS 语音合成仍使用 RichiDrama 原有语音服务，不调用 Star Proxy。
- 素材库接口仍按 [CLIENT_API.md](CLIENT_API.md) 接入，不要和图片生成接口混为一条链路。
- 漫剧微信支付回调与模型中转相互独立。

## 2. 当前差异摘要

对 RichiDrama 审计版本的检查结果如下：

| 当前行为 | 对接影响 | 目标行为 |
|---|---|---|
| 目前只有素材服务使用 `richbest_asset_v3`，模型配置仍要求供应商 Key 和真实模型 ID | 模型生成继续依赖火山账号和具体版本 | 为文本、图片和视频增加独立 `richbest` 分支，只配置 Star Proxy 业务 Key |
| 视频连接测试拿视频模型请求 `/chat/completions`，且部分非 `401/403` 错误也会被当作联通 | 可能把模型类型错误误报为测试成功 | 使用 `GET /v1/models` 做无费用验证 |
| Seedream 已把 `negative_prompt` 合并进主提示词，但仍会发送 `quality` | 负向词处理已经符合中转站要求；`quality` 对 Seedream 不生效 | 保留负向词合并逻辑，Star Proxy 分支不发送 `negative_prompt`、`quality` |
| 经典 Seedance 请求同时发送 `ratio` 和 `aspect_ratio` | 中转站返回 `422` | 只发送 `ratio` |
| 非官方 `volcengine_omni` 默认使用 `/v1/videos/generations` | 创建路径与中转站不一致 | 固定使用 `/api/v3/contents/generations/tasks` |
| `VOLC_MODEL_ALIASES` 会把部分展示名转换成火山真实 ID | 绕过中转站稳定别名治理 | `richbest` 分支原样提交 `/v1/models` 返回的 `id` |
| 前端模型选项从 `ai_service_configs.model` 汇总 | 无法自动感知中转站授权、下线和别名变化 | 后端拉取 `/v1/models` 并向前端返回动态目录 |
| 图片和视频请求未传递 HTTP `Idempotency-Key` | 网络超时重试时存在重复生成、重复费用风险 | 使用漫剧内部生成记录 ID 构造稳定幂等键 |

这些差异需要在 RichiDrama 修复，中转站不再为漫剧保留另一套私有路径、火山 Model ID 或无效参数兼容。

## 3. 统一接入配置

RichiDrama 应为文本、图片和视频增加独立供应商类型 `richbest`，不要继续用 `volcengine` 表示 Star Proxy。现有 `richbest_asset_v3` 只负责素材上传、素材组和素材状态，不应复用为模型生成协议。这样可以防止代码误用火山默认域名、真实模型 ID 映射或供应商专属探测逻辑。

统一配置：

```ini
provider=richbest
base_url=https://api.richbest.cn
api_key=vap_live_xxx
```

各服务路径：

| 服务 | 创建或调用路径 | 查询路径 |
|---|---|---|
| 模型目录 | `GET /v1/models` | 不适用 |
| 文本 | `POST /v1/chat/completions` | 同步或 SSE 流式返回 |
| 图片 | `POST /v1/images/generations` | 同步返回 |
| 视频 | `POST /api/v3/contents/generations/tasks` | `GET /api/v3/contents/generations/tasks/{taskId}` |
| 取消视频 | `DELETE /api/v3/contents/generations/tasks/{taskId}` | 不适用 |
| 素材库 | `/api/asset*`、`/api/asset-group*` | 继续使用现有 `richbest_asset_v3` 适配 |

所有请求统一携带：

```http
Authorization: Bearer vap_live_xxx
Content-Type: application/json
```

业务 Key 只能保存在 RichiDrama 后端 Secret 或数据库受保护配置中，不得下发浏览器、写入前端构建变量、提交 Git 或打印到日志。

## 4. 模型目录必须以中转站为准

RichiDrama 后端在保存配置、测试连接或刷新模型选择项时调用：

```http
GET https://api.richbest.cn/v1/models
Authorization: Bearer vap_live_xxx
```

响应中的：

- `data[].id`：提交请求时使用的模型值。
- `data[].display_name`：前端展示名称。
- `data[].modality`：区分文本、图片和视频。
- `data[].capabilities`：控制参考图、数量、分辨率、时长等界面能力。

RichiDrama 不应：

- 维护另一套火山真实 Model ID 作为中转站请求值；
- 将 `doubao-seedance-2.0` 再转换为 `doubao-seedance-2-0-260128`；
- 展示 `/v1/models` 未返回的模型；
- 根据模型名字猜测供应商或自行拼接上游 URL；
- 要求终端用户理解“漫剧别名”和“中转站别名”两套名称。

前端只展示一套模型名称：界面显示 `display_name`，内部保存并提交对应的 `id`。

当前内置模型总表见 [CLIENT_API.md 的“可用模型”](CLIENT_API.md#131-可用模型)。RichiDrama 不复制维护该列表；某个模型是否可用，最终取决于当前业务 Key 所属项目的模型授权、渠道状态和 `/v1/models` 实时响应。

建议模型目录缓存 1～5 分钟，并提供管理员主动刷新入口。接口暂时失败时可以保留最近一次成功目录，但不能凭空恢复已被明确撤销的模型。

## 5. 文本与视觉理解改造

请求路径：

```http
POST /v1/chat/completions
```

RichiDrama 当前 OpenAI Chat Completions 请求结构可以保留，主要修改如下：

1. Base URL 和 Key 改为 Star Proxy 配置。
2. `model` 原样使用 `/v1/models` 返回的 `id`。
3. 不再把模型映射成火山完整版本号。
4. 识图请求继续使用 OpenAI `image_url` 内容结构，但只允许 `capabilities.imageInput=true` 的模型。
5. 流式响应可继续使用 SSE；需要用量时保留 `stream_options.include_usage=true`。
6. 连接测试改为调用 `/v1/models`，不能再用视频模型探测 `/chat/completions`。

示例：

```json
{
  "model": "doubao-seed-2.1-turbo",
  "messages": [
    {"role": "system", "content": "你是短剧分镜助手"},
    {"role": "user", "content": "把剧情拆成三个镜头"}
  ],
  "stream": false
}
```

连接测试不要再使用“拿视频模型请求 `/chat/completions`”的方式。视频模型调用文本接口会发生模型类型不匹配，并不能证明视频能力可用。所有服务统一用 `GET /v1/models` 验证：

- Key 是否有效；
- 指定模型是否在返回列表；
- 模型类型和能力是否满足当前配置。

该检查不发起生成，不产生模型生成费用。

## 6. Seedream 图片改造

请求路径：

```http
POST /v1/images/generations
```

建议请求：

```json
{
  "model": "doubao-seedream-5.0",
  "prompt": "电影感室内场景，暖色灯光，不要拼贴画面",
  "image": ["https://example.com/reference.png"],
  "size": "2K",
  "n": 1,
  "response_format": "url",
  "watermark": false
}
```

RichiDrama 最新代码已经把 Seedream 的负向要求合并进主提示词；进入 `richbest` 分支后必须继续保持该行为，不得发送：

```text
negative_prompt
```

该字段不属于 Star Proxy 当前 Seedream 契约，发送会返回 `422 image_parameter_unsupported`。原有负向要求应合并进 `prompt`。

以下字段即使被兼容接收，也不会传到火山 Seedream，不能继续在界面中宣传为有效控制项：

```text
quality
style
user
```

因此 RichiDrama 对 Seedream 应隐藏 `quality`，且构造 Star Proxy 请求时不要携带该字段。`quality` 仍可用于 RichiDrama 自己压缩本地参考图，但不能混同为生成质量参数。当前 `imageClient.js` 的通用请求体仍会在 `quality` 非空时发送它，这一分支需要按 `richbest`/Seedream 显式过滤。

参考图规则：

- 使用 `image`，可以是单个 URL/Data URL 或数组。
- 最多数量读取 `capabilities.maxInputImages`，当前 Seedream 通常最多 10 张。
- Base64 图片按解码后的实际文件大小计算，当前单张上限 10 MiB。
- 公网 URL 由火山最终拉取和校验。
- 不要在 RichiDrama 增加比中转站更小的固定 1.5MB 限制。
- 本地图片需要转 Data URL 时应限制并发和内存；能使用稳定公网 URL 时优先使用 URL。

图片成功响应中的 URL 可能过期。RichiDrama 如需长期保存，应在收到成功响应后下载并写入自己的媒体存储。

## 7. Seedance 与其他视频模型改造

### 7.1 路径

统一使用：

```text
POST   /api/v3/contents/generations/tasks
GET    /api/v3/contents/generations/tasks/{taskId}
DELETE /api/v3/contents/generations/tasks/{taskId}
```

不要使用以下旧中转路径：

```text
/v1/videos
/v1/videos/generations
/video/generations
/v1/videos/generations/async/{taskId}
```

### 7.2 创建字段

标准创建示例：

```json
{
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
}
```

视频请求只发送 `ratio`，不得同时发送 `aspect_ratio`。截至本次审计，RichiDrama 的经典视频请求体仍同时构造两个字段；必须在 `richbest` 分支删除 `aspect_ratio`，否则返回 `422 video_parameter_unsupported`。漫剧数据库或界面内部继续使用 `aspect_ratio` 作为业务字段不受影响，限制只针对发送给 Star Proxy 的 HTTP 请求体。

允许字段以 [MODEL_RELAY_API.md](MODEL_RELAY_API.md) 为准。不同模型的字段能力不完全相同，RichiDrama 应读取 `/v1/models` 的 `capabilities`，不要因为统一表单中存在某个选项就向所有模型发送。

素材引用要求：

- Seedance 可按能力接收 HTTP(S)、Data URL 和 `asset://`。
- `asset://` 必须原样发送，不能先当作公网 URL 校验并拒绝。
- `asset://` 必须属于 Star Proxy 业务 Key 对应的同一项目，并且仍可用。
- 图片角色根据模型使用 `first_frame`、`last_frame` 或 `reference_image`。
- 视频和音频参考分别使用 `reference_video`、`reference_audio`。
- `wan3.0-video` 和 `minimax-h3` 当前只接受 HTTP(S) 图片引用；具体限制读取模型能力。

### 7.3 异步任务

创建成功返回：

```json
{"id": "vid_0123456789abcdef"}
```

RichiDrama 必须保存这个中转站任务 ID，不要保存或猜测真实上游任务 ID。后续查询成功示例：

```json
{
  "id": "vid_0123456789abcdef",
  "model": "doubao-seedance-2.0",
  "status": "succeeded",
  "resolution": "720p",
  "ratio": "16:9",
  "duration": 5,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

状态统一为：

```text
queued → running → succeeded / failed / cancelled
```

任务只能由创建它的同一枚 Star Proxy 业务 Key 查询或取消，同项目另一枚 Key 也不行。因此：

- RichiDrama 的视频任务记录要保存创建时使用的 AI 配置 ID或 Key 版本标识；
- 轮询不能根据“当前默认模型”重新选择另一套配置；
- 仍有未完成任务时不要禁用或删除旧业务 Key；
- 更换 Key 时先停止新任务、等待旧任务结束，再完成切换。

成功视频 URL 可能过期，RichiDrama 应及时下载到自己的媒体存储。

## 8. 幂等与重试

图片和视频首次创建可以不发送幂等键，但为了避免网络超时重试造成重复生成和重复费用，建议 RichiDrama 使用自身已经存在的生成记录 ID：

```http
Idempotency-Key: image-{image_generation_id}
Idempotency-Key: video-{video_generation_id}
```

要求：

- 同一条漫剧生成记录的网络重试始终复用同一幂等键。
- 用户明确点击“重新生成”时创建新的漫剧记录和新幂等键。
- 不能让相同幂等键对应不同请求体，否则中转站返回 `409 idempotency_key_conflict`。
- RichiDrama 自身仍负责防止按钮连点、任务状态流转和数据库重复提交；中转站幂等是额外的费用保护，不替代漫剧本地事务。

如果 RichiDrama 能保证创建请求绝不自动重试，第一阶段可以暂缓发送该请求头，但必须明确接受网络超时后无法安全判断是否已产生上游任务的风险。

## 9. 错误处理与日志

RichiDrama 应完整保存以下排障信息：

- HTTP 状态码；
- 响应中的错误 `code` 和 `message`；
- 响应头 `X-Request-Id` 或响应体 `request_id`；
- 漫剧自己的生成记录 ID；
- 模型别名和任务 ID。

禁止记录：

- 完整 `vap_live_*`；
- 供应商 Key；
- 完整 Base64 素材；
- 完整用户提示词或剧本正文；
- 完整上游响应正文中的隐私字段。

可记录业务 Key 后 4～6 位用于人工核对，但不能记录前缀加大段正文。

建议处理：

| HTTP | RichiDrama 行为 |
|---:|---|
| `401` | 标记平台配置失效并通知管理员，不要求终端用户填写 Key |
| `403` | 模型未授权或项目不匹配，刷新 `/v1/models` 并提示管理员 |
| `404` | 模型或任务不存在；任务场景检查是否换了 Key 或使用了错误任务 ID |
| `409` | 幂等冲突或既有请求仍在执行，不创建第二条上游任务 |
| `422` | 显示参数或素材不支持，不进行原样无限重试 |
| `429` | 按 `Retry-After` 退避；没有该头时使用指数退避并设置最大次数 |
| `502` / `504` | 保存 Request ID；创建请求只有在复用同一幂等键时才能自动重试 |

连接测试必须把所有非 2xx 都视为明确结果，不能把除 `401/403` 之外的错误一律当作“联通成功”。

## 10. RichiDrama 当前代码改造点

以下是基于审计版本的主要修改位置，文件重构后以实际调用链为准：

| 文件 | 需要修改 |
|---|---|
| `backend-node/src/services/aiConfigService.js` | 在现有 `richbest_asset_v3` 之外增加模型供应商 `richbest`；连接测试改为 `GET /v1/models`；禁止为 Star Proxy 拼供应商探测路径 |
| `backend-node/src/services/aiClient.js` | 使用中转站模型别名和统一路径；保留 OpenAI Chat Completions/SSE 格式 |
| `backend-node/src/services/imageClient.js` | 保留现有负向词合并逻辑；`richbest`/Seedream 请求不发送 `negative_prompt`、`quality`；参考图限制与模型能力一致 |
| `backend-node/src/services/videoClient.js` | 为 `richbest` 固定 `/api/v3/contents/generations/tasks`；请求体只发送 `ratio`；不把别名转换为火山 Model ID；查询和取消使用同一 Key |
| `backend-node/src/routes/aiConfig.js` | 返回动态模型目录；保存时验证所选模型属于当前 Key |
| `frontweb/src/components/AIConfigContent.vue` | 在现有“Richbest 多类型素材 API v3”之外增加“瑞池模型中转”；按模型目录显示名称和能力；不向普通用户展示业务 Key |
| `frontweb/src/composables/useModelOptions.js` | 不再只从本地 `ai_service_configs.model` 汇总；使用 `/v1/models` 的 `data[].id` 作为唯一提交值，删除硬编码火山版本号兜底 |

RichiDrama 当前 `VOLC_MODEL_ALIASES` 只适用于直连火山。进入 `richbest` 分支后不得调用该映射；否则会把中转站稳定别名重新变成真实上游 ID，破坏中转站的版本治理。

## 11. 配置迁移建议

1. 在 Star Proxy 为整个 RichiDrama 生产系统准备一个客户项目。
2. 为该项目绑定所需模型和供应商渠道。
3. 签发一枚生产业务 Key，存入 RichiDrama 后端受保护配置。
4. 在 RichiDrama 新增 `richbest` 配置，不直接覆盖旧火山配置。
5. 调用 `/v1/models` 完成无费用连接测试和模型同步。
6. 先用测试项目验证文本、图片和视频完整链路。
7. 将 RichiDrama 默认模型切换为中转站返回的别名。
8. 等待旧直连火山的异步任务全部结束。
9. 禁用旧直连配置，但保留一段观察期用于回滚。
10. 验收完成后再移除旧火山 Key；不要在任务执行中途删除。

终端用户不参与上述配置，也不需要一人一项目或一人一 Key。RichiDrama 若需要按用户收费，应以自己的生成记录、成功状态和内部价格表结算。

## 12. 验收清单

### P0：上线前必须通过

- [ ] RichiDrama 后端可以使用业务 Key 获取 `/v1/models`。
- [ ] 素材继续走 `richbest_asset_v3`，模型生成走独立 `richbest` 分支，两者没有混用协议。
- [ ] 前端只展示接口返回的模型，提交值为 `data[].id`。
- [ ] 浏览器网络请求和前端资源中不存在业务 Key。
- [ ] 文本同步和流式请求成功，返回模型名仍为稳定别名。
- [ ] Seedream 文生图成功。
- [ ] Seedream 单图、多图参考成功，未发送 `negative_prompt`。
- [ ] Seedance 文生视频成功。
- [ ] Seedance 使用公网 URL 参考图成功。
- [ ] Seedance 使用同项目 `asset://` 成功。
- [ ] 视频请求中只有 `ratio`，没有 `aspect_ratio`。
- [ ] 创建响应保存 `vid_*`，查询使用同一业务 Key 并最终得到视频 URL。
- [ ] 未授权模型不会出现在界面，强行提交时能正确展示 `403`。
- [ ] 参数错误不会无限重试；429 会读取 `Retry-After`。
- [ ] 日志不包含完整 Key、Base64 图片和提示词正文。

### P1：建议在正式放量前完成

- [ ] 图片和视频创建传递稳定 `Idempotency-Key`。
- [ ] 模型目录支持短时缓存、主动刷新和变更后的界面降级。
- [ ] 视频任务记录绑定创建时的配置版本，Key 切换不会误查。
- [ ] 成功图片和视频及时转存到 RichiDrama 自己的媒体存储。
- [ ] 监控 401、403、422、429、502、504 的数量及 Request ID。

## 13. 最终边界

对接完成后，职责划分如下：

| RichiDrama 负责 | Star Proxy 负责 |
|---|---|
| ToC 用户、权限、积分、订单和内部账单 | 客户项目、业务 Key 和模型授权 |
| 生成表单、提示词和素材选择 | 稳定模型别名到真实上游模型的映射 |
| 本地任务记录、按钮防重和结果持久化 | 供应商渠道、凭证加密和上游任务适配 |
| 使用同一业务 Key创建和查询异步任务 | 项目级用量、限流、审计和供应商调用 |
| 向终端用户展示业务结果 | 向 RichiDrama 返回统一接口结果和 Request ID |

RichiDrama 不再决定真实上游模型版本；Star Proxy 也不接管漫剧终端用户和订单体系。双方以业务 Key、`/v1/models` 和本文列出的公开接口作为唯一边界。
