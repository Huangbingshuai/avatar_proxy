# Seedance 国内 API 接口文档

> 本文档描述如何直接调用火山引擎方舟中国区 Seedance 视频生成 API，与本仓库现有系统、业务 API Key、控制台和后端封装均无关。
>
> 文档中的 Key、模型 ID、任务 ID 和素材 URL 均为占位符。请勿将真实凭证写入代码或提交到 Git。

## 目录

1. [接入信息](#1-接入信息)
2. [模型选择](#2-模型选择)
3. [接口总览](#3-接口总览)
4. [创建视频生成任务](#4-创建视频生成任务)
5. [查询单个任务](#5-查询单个任务)
6. [查询任务列表](#6-查询任务列表)
7. [取消或删除任务](#7-取消或删除任务)
8. [完整代码示例](#8-完整代码示例)
9. [回调接入](#9-回调接入)
10. [错误处理与重试](#10-错误处理与重试)
11. [生产环境建议](#11-生产环境建议)
12. [与本仓库现有系统的边界](#12-与本仓库现有系统的边界)
13. [常见问题](#13-常见问题)
14. [官方资料](#14-官方资料)

## 1. 接入信息

| 项目 | 内容 |
| --- | --- |
| 服务 | 火山引擎方舟视频生成 API |
| 中国区 Base URL | `https://ark.cn-beijing.volces.com/api/v3` |
| 鉴权方式 | HTTP Bearer API Key |
| 请求格式 | `application/json` |
| 执行方式 | 异步任务：创建任务后轮询查询，或配置回调地址 |

在[火山方舟 API Key 管理页](https://console.volcengine.com/ark/region:ark+cn-beijing/apikey)创建 Key，并确保它有权访问准备调用的模型或推理接入点。

### 1.1 开通前检查

开始编码前依次确认：

1. 火山引擎账号已完成要求的实名认证。
2. 方舟控制台已开通目标 Seedance 模型。
3. 已创建中国北京区域的方舟 API Key。
4. API Key 权限范围包含目标模型或目标推理接入点。
5. 若 API Key 开启了 IP 白名单，调用服务器的公网出口 IP 已加入白名单。
6. 账号余额、模型额度、并发和 RPM 能满足本次调用。
7. 调用机器能够通过 HTTPS 访问 `ark.cn-beijing.volces.com:443`。

### 1.2 鉴权规则

所有接口都通过以下请求头传递方舟 API Key：

```http
Authorization: Bearer YOUR_ARK_API_KEY
```

创建任务还必须发送：

```http
Content-Type: application/json
```

注意：

- `YOUR_ARK_API_KEY` 是火山方舟原生 Key，不是 AccessKey/SecretKey，也不是其他平台签发的业务 Key。
- 请求路径中不需要额外携带账号 ID 或项目名称；Key 自身所属项目和权限决定可访问范围。
- Key 不应出现在 URL 查询参数、前端 JavaScript、浏览器网络请求或日志中。
- Bearer 与 Key 之间必须有一个空格。

建议通过环境变量保存凭证：

```bash
export ARK_API_KEY="替换为你的方舟API_KEY"
export MODEL_ID="替换为模型ID或推理接入点ID"
```

PowerShell：

```powershell
$env:ARK_API_KEY = "替换为你的方舟API_KEY"
$env:MODEL_ID = "替换为模型ID或推理接入点ID"
```

### 1.3 最小连通性检查

视频生成会产生真实调用和费用。可以先用任务列表接口验证域名、TLS 和 API Key 是否可用：

```bash
curl --request GET \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks?page_num=1&page_size=1" \
  --header "Authorization: Bearer $ARK_API_KEY"
```

结果判断：

- 返回 `200` 和 JSON：基础连通及鉴权正常。
- 返回 `401`：Key 缺失、错误、失效或格式不正确。
- 返回 `403`：重点检查模型/项目权限以及 API Key 的 IP 白名单。
- 连接超时或 DNS 失败：检查服务器网络、代理、防火墙和域名解析。
- 返回 `429`：账号当前配额或排队任务数可能已达到限制。

## 2. 模型选择

创建任务时，`model` 必须填写方舟控制台中可用的模型 ID 或推理接入点 ID，不能填写展示名称。

### 2.1 Model ID 与 Endpoint ID 的区别

| 类型 | 常见格式 | 特点 | 适合场景 |
| --- | --- | --- | --- |
| Model ID | `doubao-seedance-...` | 直接指定模型及版本 | 希望快速调用公开模型 |
| Endpoint ID | `ep-...` | 指向已创建的在线推理接入点 | 希望单独配置接入点限流、权限或资源治理 |

两者都填写在请求体的 `model` 字段中。使用 Endpoint ID 时，任务列表接口的 `filter.model` 也应填写 Endpoint ID；任务响应里的 `model` 通常是实际模型名称及版本，二者含义不同。

官方文档中可见的模型 ID 示例：

| 模型 | 模型 ID 示例 |
| --- | --- |
| Seedance 2.0 | `doubao-seedance-2-0-260128` |
| Seedance 2.0 Fast | `doubao-seedance-2-0-fast-260128` |
| Seedance 1.5 Pro | `doubao-seedance-1-5-pro-251215` |

模型版本、开放范围和 ID 可能调整。尤其是 Seedance 2.5，请在方舟控制台的模型列表或在线推理接入点详情中复制当前真实 ID，不要根据模型名称自行拼接。

### 2.2 常见能力差异

下表用于接入时快速避坑，最终以模型详情页为准：

| 能力 | Seedance 2.0 | Seedance 2.0 Fast | Seedance 1.5 Pro |
| --- | --- | --- | --- |
| `duration` | 4–15 秒或 `-1` | 4–15 秒或 `-1` | 4–12 秒或 `-1` |
| 默认画面比例 | `adaptive` | `adaptive` | `adaptive` |
| `frames` | 不支持 | 不支持 | 不支持 |
| `generate_audio` | 支持 | 支持 | 支持 |
| `1080p` | 以控制台能力为准 | 不支持 | 以控制台能力为准 |
| `service_tier=flex` | 不支持 | 不支持 | 以控制台能力为准 |
| 固定摄像头 `camera_fixed` | 不支持 | 不支持 | 参考图场景不支持 |

这里的 `-1` 表示由模型决定合适时长，并不等于无限时长。

## 3. 接口总览

| 操作 | 方法 | 路径 |
| --- | --- | --- |
| 创建视频任务 | `POST` | `/contents/generations/tasks` |
| 查询单个任务 | `GET` | `/contents/generations/tasks/{task_id}` |
| 查询任务列表 | `GET` | `/contents/generations/tasks` |
| 取消或删除任务 | `DELETE` | `/contents/generations/tasks/{task_id}` |

## 4. 创建视频生成任务

### 4.1 文生视频

```bash
curl --request POST \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks" \
  --header "Authorization: Bearer $ARK_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
      {
        "type": "text",
        "text": "清晨的海边，一辆复古汽车沿海岸公路行驶，电影感，镜头平稳推进"
      }
    ],
    "resolution": "720p",
    "ratio": "16:9",
    "duration": 5,
    "generate_audio": true,
    "watermark": false,
    "return_last_frame": false
  }'
```

### 4.2 参考图生成视频

素材 URL 必须能够被火山方舟服务访问。不要使用仅在内网、本机或需要登录 Cookie 才能访问的地址。

```bash
curl --request POST \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks" \
  --header "Authorization: Bearer $ARK_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
      {
        "type": "text",
        "text": "人物缓慢转身看向镜头，衣服和人物身份保持一致，背景有轻微风动"
      },
      {
        "type": "image_url",
        "image_url": {
          "url": "https://example.com/reference.png"
        },
        "role": "reference_image"
      }
    ],
    "resolution": "720p",
    "ratio": "adaptive",
    "duration": 5,
    "generate_audio": true,
    "watermark": false
  }'
```

不同模型支持的输入组合不同。官方接口可表达文本、图片、视频和音频等内容项，但实际能否使用以及 `role` 的取值必须以所选模型的能力说明为准。

### 4.3 图片、视频、音频联合参考

Seedance 2.0 系列可以在同一个 `content` 数组中组织多种参考素材。下面展示请求结构，不代表每个账号或模型版本都默认开放全部能力：

```bash
curl --request POST \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks" \
  --header "Authorization: Bearer $ARK_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
      {
        "type": "text",
        "text": "保持图片中的产品外观，参考视频的运镜节奏，并使用参考音频作为背景音乐，生成一段8秒商品广告"
      },
      {
        "type": "image_url",
        "image_url": {"url": "https://example.com/product.png"},
        "role": "reference_image"
      },
      {
        "type": "video_url",
        "video_url": {"url": "https://example.com/camera-reference.mp4"},
        "role": "reference_video"
      },
      {
        "type": "audio_url",
        "audio_url": {"url": "https://example.com/background.mp3"},
        "role": "reference_audio"
      }
    ],
    "resolution": "720p",
    "ratio": "16:9",
    "duration": 8,
    "generate_audio": true,
    "watermark": false,
    "safety_identifier": "sha256-of-your-end-user-id"
  }'
```

`content` 元素结构：

| `type` | 内容字段 | 常用 `role` | 用途 |
| --- | --- | --- | --- |
| `text` | `text` | 无 | 描述主体、动作、场景、镜头、声音和限制条件 |
| `image_url` | `image_url.url` | `reference_image` | 提供人物、产品、场景、风格等视觉参考 |
| `video_url` | `video_url.url` | `reference_video` | 提供动作、构图或运镜参考 |
| `audio_url` | `audio_url.url` | `reference_audio` | 提供配乐、节奏、声音或音色参考 |

输入顺序建议：先写文本指令，再依次放入文本中所说的图片、视频和音频。提示词中使用“图片1”“视频1”“音频1”等明确编号，避免多个素材之间指代不清。

### 4.4 使用方舟可信素材 Asset ID

对于已经录入方舟可信素材库的素材，可以使用 `asset://` URI，而不是公网 URL：

```json
{
  "type": "image_url",
  "image_url": {
    "url": "asset://asset-xxxxxxxxxxxxxxxx"
  },
  "role": "reference_image"
}
```

使用要求：

- Asset ID 必须真实存在并处于可用状态。
- 素材必须属于当前 API Key 有权访问的方舟项目或授权范围。
- 真人素材需要完成平台要求的认证和授权；上传成功不等于一定可以用于视频生成。
- 若资产不可用、未授权或跨项目访问，创建任务会被方舟拒绝。

### 4.5 公网素材 URL 要求

当使用 `https://...` 素材地址时，建议满足：

- 使用 HTTPS，证书链完整且未过期。
- 无需 Cookie、登录态、自定义请求头或临时浏览器会话即可下载。
- 不使用 `localhost`、`127.0.0.1`、局域网 IP 或企业内网域名。
- URL 在任务创建及方舟拉取期间保持有效，不要设置过短的签名过期时间。
- 正确返回 `Content-Type`，不要返回 HTML 登录页、302 到鉴权页面或防盗链 403。
- 文件扩展名、响应类型和真实文件签名一致。
- 生产环境优先使用受控对象存储，并限制 URL 的可访问时长和权限。

提交前可从一台不携带 Cookie 的公网机器测试：

```bash
curl --location --head "https://example.com/reference.png"
```

至少应确认最终响应为 `200`，且 `Content-Type` 与素材类型一致。

### 4.6 创建成功响应

```json
{
  "id": "cgt-xxxxxxxxxxxxxxxx"
}
```

保存返回的 `id`，后续查询、取消或删除任务都需要它。方舟任务记录有保留期限，不应把方舟任务列表当作永久业务数据库。

### 4.7 完整创建参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model` | string | 是 | 模型 ID 或推理接入点 ID |
| `content` | array | 是 | 文本以及模型支持的图片、视频、音频等输入 |
| `resolution` | string | 否 | 常见值：`480p`、`720p`、`1080p`；支持范围依模型而定 |
| `ratio` | string | 否 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` |
| `duration` | integer | 否 | 视频时长；Seedance 2.0/2.0 Fast 通常支持 4–15 秒或 `-1`，具体以模型文档为准 |
| `frames` | integer | 否 | 按帧数指定长度；与 `duration` 二选一，并非所有模型支持 |
| `seed` | integer | 否 | 随机种子；允许范围为 `-1` 到 `2^32-1` |
| `generate_audio` | boolean | 否 | 是否生成音频；仅部分模型支持 |
| `watermark` | boolean | 否 | 是否添加水印 |
| `return_last_frame` | boolean | 否 | 成功后是否在查询结果中返回尾帧 |
| `callback_url` | string | 否 | 状态变化回调地址，必须能被公网访问 |
| `safety_identifier` | string | 否 | 最多 64 字符；建议传稳定、不可逆的终端用户标识 |
| `service_tier` | string | 否 | `default` 为在线推理，`flex` 为离线推理；并非所有模型支持 `flex` |
| `execution_expires_after` | integer | 否 | 排队或执行过期时间，范围 3600–259200 秒，默认 172800 秒 |

参数补充说明：

#### `resolution`

- 传枚举字符串，例如传 `"720p"`，不要传 `1280x720`。
- 分辨率越高，生成耗时、用量和费用通常越高。
- 不同模型、输入模式和时长组合可能有不同限制。

#### `ratio`

- `adaptive` 会根据输入素材选择适合比例，适用于参考图或多模态输入。
- 纯文本生成且交付平台明确时，建议显式指定比例，例如竖屏短视频使用 `9:16`。
- 输入素材比例与目标比例差距过大时，模型可能重构画面或裁切主体。

#### `duration` 与 `frames`

- 两者二选一即可；同时传递时 `frames` 优先。
- Seedance 2.0、2.0 Fast 和 1.5 Pro 当前不支持 `frames`，应使用 `duration`。
- 旧版支持 `frames` 的模型按 24 FPS 计算，并要求帧数处于官方限定范围。

#### `generate_audio`

- `true` 表示要求生成与画面同步的音频。
- 即使模型支持音频，也不能假设每次生成一定包含对白、音乐或特定声音；应在提示词中明确描述。
- 若同时提供参考音频，应在提示词中说明它是背景音乐、节奏参考、音色参考还是完整音轨。

#### `return_last_frame`

- 设置为 `true` 后，成功查询结果可包含尾帧图片。
- 官方说明尾帧为 PNG、尺寸与视频一致且不带水印。
- 适合连续分镜生成：将上一段尾帧作为下一段的视觉参考。

#### `execution_expires_after`

- 控制任务排队或运行的最长容忍时间，并非 HTTP 请求超时。
- 接口创建请求仍应使用较短的网络超时，例如 30 秒。
- 过期任务状态为 `expired`，需要重新创建任务。

#### `safety_identifier`

- 建议填写经过哈希的稳定终端用户 ID。
- 同一用户多次调用应保持一致，便于安全治理。
- 不要直接传手机号、身份证号、邮箱等个人敏感信息。

兼容性提示：

- Seedance 2.0/2.0 Fast 不支持 `frames`。
- Seedance 2.0 Fast 不支持 `1080p`。
- Seedance 2.0/2.0 Fast 不支持 `service_tier=flex`。
- `camera_fixed` 在参考图场景及 Seedance 2.0/2.0 Fast 中不可用。
- 模型能力会更新，生产接入前应再次核对对应模型页面。

### 4.8 建议的提示词结构

视频提示词可按以下顺序编写：

```text
主体与身份 + 场景与时间 + 动作时间线 + 镜头语言 + 视觉风格
+ 光线与色彩 + 声音/对白 + 必须保持的元素 + 禁止出现的元素
```

示例：

```text
0-2秒：图片1中的白色运动鞋放在黑色镜面展台上，冷色轮廓光；
2-5秒：镜头沿鞋底低角度环绕，保持Logo、鞋带和鞋底纹理完全一致；
5-8秒：鞋子被水花托起，镜头快速拉远，结尾定格产品正面。
电影广告质感，16:9，不出现额外文字、人物、其他品牌标识。
背景音乐为低沉电子节拍，水花出现时加入清晰冲击音效。
```

提示词建议：

- 用明确时间段描述动作，减少“先……然后……”的歧义。
- 对必须一致的主体特征逐项说明，不只写“保持一致”。
- 将运镜描述与主体动作分开，例如“人物向前走，镜头平稳后退跟拍”。
- 多参考素材必须编号，并在提示词中明确各自用途。
- 不要堆叠互相冲突的镜头、风格和动作要求。

## 5. 查询单个任务

```bash
curl --request GET \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-xxxxxxxxxxxxxxxx" \
  --header "Authorization: Bearer $ARK_API_KEY"
```

成功任务响应示例：

```json
{
  "id": "cgt-xxxxxxxxxxxxxxxx",
  "model": "doubao-seedance-2-0-260128",
  "status": "succeeded",
  "created_at": 1788100000,
  "updated_at": 1788100120,
  "content": {
    "video_url": "https://example-output-url/video.mp4"
  },
  "usage": {
    "completion_tokens": 100000,
    "total_tokens": 100000
  }
}
```

失败任务响应示例：

```json
{
  "id": "cgt-xxxxxxxxxxxxxxxx",
  "status": "failed",
  "error": {
    "code": "ERROR_CODE",
    "message": "错误说明"
  }
}
```

任务状态：

| 状态 | 含义 |
| --- | --- |
| `queued` | 等待执行 |
| `running` | 正在生成 |
| `cancelled` | 已取消 |
| `succeeded` | 生成成功 |
| `failed` | 生成失败 |
| `expired` | 任务已过期 |

### 5.1 查询响应字段

| 字段 | 说明 |
| --- | --- |
| `id` | 视频生成任务 ID |
| `model` | 实际执行任务的模型名称及版本 |
| `status` | 当前任务状态 |
| `created_at` | 创建时间，Unix 秒级时间戳 |
| `updated_at` | 最近更新时间，Unix 秒级时间戳 |
| `content.video_url` | 成功任务的视频结果地址 |
| `content.last_frame_url` | 请求返回尾帧且任务成功时可能出现的尾帧地址 |
| `error.code` | 失败任务的上游错误码 |
| `error.message` | 失败任务的错误说明 |
| `resolution` | 实际生成分辨率 |
| `ratio` | 实际生成比例 |
| `duration` | 实际视频时长；与 `frames` 通常只返回一个 |
| `frames` | 实际生成帧数；与 `duration` 通常只返回一个 |
| `framespersecond` | 实际视频帧率 |
| `generate_audio` | 输出是否包含同步音频 |
| `seed` | 本次任务实际使用的随机种子 |
| `service_tier` | 实际使用的服务等级 |
| `execution_expires_after` | 本次任务的过期阈值 |
| `safety_identifier` | 创建任务时传入的终端用户标识 |
| `usage.completion_tokens` | 输出视频折算的用量 token |
| `usage.total_tokens` | 任务总 token；是否返回取决于当前接口版本和模型 |

客户端必须允许响应增加新字段，不要因为出现未知字段就反序列化失败。

### 5.2 推荐轮询策略

```text
创建任务
  ↓
保存 task_id
  ↓
等待 3～5 秒后首次查询
  ↓
queued/running ──等待并再次查询──┐
  │                              │
  ├─ succeeded → 下载结果并落库  │
  ├─ failed    → 记录错误并结束  │
  ├─ cancelled → 标记取消并结束  │
  └─ expired   → 标记过期并结束  │
```

实践建议：

- 不要每秒持续轮询；普通业务可从 5 秒间隔开始。
- 长时间排队时逐步增加到 10～30 秒。
- 每次查询设置网络超时，并对临时网络错误进行有限重试。
- 达到业务方最大等待时间后，可以停止前台轮询，但不要擅自将方舟任务标记为失败。
- 后台仍可继续查询，或依赖回调补齐最终状态。
- 终态任务不再轮询。

生成成功后应尽快下载 `video_url` 对应文件并保存到自己的对象存储；不要将结果 URL 当作永久地址。

### 5.3 下载生成结果

```bash
curl --location \
  --fail \
  --retry 3 \
  --output "seedance-output.mp4" \
  "替换为查询结果中的video_url"
```

下载后建议：

1. 校验 HTTP 状态码和文件大小。
2. 检查文件头及 `Content-Type`，避免把 JSON 错误页保存成 MP4。
3. 计算 SHA-256，用于完整性检查和去重。
4. 上传到自己的 TOS/OSS，并保存永久对象地址。
5. 数据库同时保留方舟 `task_id`、原始结果 URL、永久地址和下载时间。

## 6. 查询任务列表

```bash
curl --request GET \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks?page_num=1&page_size=20&filter.status=succeeded" \
  --header "Authorization: Bearer $ARK_API_KEY"
```

常用查询参数：

| 参数 | 说明 |
| --- | --- |
| `page_num` | 页码，范围 1–500 |
| `page_size` | 每页数量，范围 1–500 |
| `filter.status` | `queued`、`running`、`cancelled`、`succeeded` 或 `failed` |
| `filter.task_ids` | 按任务 ID 筛选，可重复传递 |
| `filter.model` | 按推理接入点 ID 精确筛选 |
| `filter.service_tier` | `default` 或 `flex` |

响应示例：

```json
{
  "items": [
    {
      "id": "cgt-xxxxxxxxxxxxxxxx",
      "status": "succeeded"
    }
  ],
  "total": 1
}
```

### 6.1 多任务 ID 查询

多个 `filter.task_ids` 需要重复传递参数，而不是使用逗号拼接：

```bash
curl --get \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks" \
  --header "Authorization: Bearer $ARK_API_KEY" \
  --data-urlencode "page_num=1" \
  --data-urlencode "page_size=100" \
  --data-urlencode "filter.task_ids=cgt-task-id-1" \
  --data-urlencode "filter.task_ids=cgt-task-id-2"
```

### 6.2 分页读取

```text
page_num = 1
循环：
  请求当前页
  保存 items
  如果累计数量 >= total 或 items 为空：结束
  否则 page_num += 1
```

页码和每页数量最大均为 500，因此不能假设单次请求能返回账号下全部任务。正式业务应把任务 ID 在创建时就保存到自己的数据库，列表接口只用于补偿、核对和运维查询。

## 7. 取消或删除任务

```bash
curl --request DELETE \
  --url "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-xxxxxxxxxxxxxxxx" \
  --header "Authorization: Bearer $ARK_API_KEY"
```

成功响应：

```json
{}
```

平台会根据任务状态执行取消或删除。排队中的任务可以取消；已取消的任务记录会在一段时间后自动清理。调用方应以接口返回结果为准，不要仅根据本地状态判断操作成功。

## 8. 完整代码示例

### 8.1 Python：创建、轮询并下载

安装依赖：

```bash
pip install requests
```

```python
import os
import pathlib
import time
import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
API_KEY = os.environ["ARK_API_KEY"]
MODEL_ID = os.environ["MODEL_ID"]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

create_response = requests.post(
    f"{BASE_URL}/contents/generations/tasks",
    headers=headers,
    json={
        "model": MODEL_ID,
        "content": [
            {
                "type": "text",
                "text": "雨后的未来城市，霓虹灯倒映在路面，镜头缓慢向前移动",
            }
        ],
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 5,
        "watermark": False,
    },
    timeout=30,
)
create_response.raise_for_status()
task_id = create_response.json()["id"]
print("task_id:", task_id)

poll_interval = 5
while True:
    response = requests.get(
        f"{BASE_URL}/contents/generations/tasks/{task_id}",
        headers=headers,
        timeout=30,
    )

    if response.status_code == 429:
        time.sleep(poll_interval)
        poll_interval = min(poll_interval * 2, 60)
        continue

    response.raise_for_status()
    task = response.json()
    status = task["status"]
    print("status:", status)

    if status == "succeeded":
        video_url = task["content"]["video_url"]
        print("video_url:", video_url)

        with requests.get(video_url, stream=True, timeout=120) as download:
            download.raise_for_status()
            output_path = pathlib.Path(f"{task_id}.mp4")
            with output_path.open("wb") as output:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        print("saved:", output_path.resolve())
        break

    if status in {"failed", "cancelled", "expired"}:
        raise RuntimeError(task.get("error") or f"task ended: {status}")

    time.sleep(poll_interval)
```

### 8.2 Node.js：创建与轮询

以下示例要求 Node.js 18 或更高版本，以使用内置 `fetch`：

```javascript
const BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";
const API_KEY = process.env.ARK_API_KEY;
const MODEL_ID = process.env.MODEL_ID;

if (!API_KEY || !MODEL_ID) {
  throw new Error("请设置 ARK_API_KEY 和 MODEL_ID 环境变量");
}

const headers = {
  Authorization: `Bearer ${API_KEY}`,
  "Content-Type": "application/json",
};

async function parseResponse(response) {
  const body = await response.text();
  let data;
  try {
    data = JSON.parse(body);
  } catch {
    data = { raw: body };
  }

  if (!response.ok) {
    const error = new Error(`Ark HTTP ${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function createTask() {
  const response = await fetch(`${BASE_URL}/contents/generations/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      model: MODEL_ID,
      content: [
        {
          type: "text",
          text: "夜晚的城市天台，一只橘猫看向远处霓虹灯，镜头缓慢靠近",
        },
      ],
      resolution: "720p",
      ratio: "16:9",
      duration: 5,
      watermark: false,
    }),
  });
  return parseResponse(response);
}

async function getTask(taskId) {
  const response = await fetch(
    `${BASE_URL}/contents/generations/tasks/${encodeURIComponent(taskId)}`,
    { headers },
  );
  return parseResponse(response);
}

async function main() {
  const created = await createTask();
  console.log("task_id:", created.id);

  let waitMs = 5000;
  while (true) {
    await sleep(waitMs);

    try {
      const task = await getTask(created.id);
      console.log("status:", task.status);

      if (task.status === "succeeded") {
        console.log("video_url:", task.content.video_url);
        return;
      }
      if (["failed", "cancelled", "expired"].includes(task.status)) {
        throw new Error(JSON.stringify(task.error ?? task));
      }
    } catch (error) {
      if (error.status === 429 || error.status >= 500) {
        waitMs = Math.min(waitMs * 2, 60000);
        continue;
      }
      throw error;
    }
  }
}

main().catch((error) => {
  console.error(error.data ?? error);
  process.exitCode = 1;
});
```

### 8.3 Postman 配置

如果使用 Postman：

1. 新建环境变量 `base_url`，值为 `https://ark.cn-beijing.volces.com/api/v3`。
2. 新建秘密变量 `ark_api_key`，值为方舟 API Key。
3. Authorization 选择 `Bearer Token`，Token 填 `{{ark_api_key}}`。
4. 创建任务请求选择 `POST`，地址为 `{{base_url}}/contents/generations/tasks`。
5. Body 选择 `raw` → `JSON`，粘贴本文创建任务请求体。
6. 在 Tests 中保存任务 ID：

```javascript
const data = pm.response.json();
if (data.id) {
  pm.environment.set("task_id", data.id);
}
```

7. 查询请求使用 `GET {{base_url}}/contents/generations/tasks/{{task_id}}`。

不要导出或分享包含真实 `ark_api_key` 当前值的 Postman Environment 文件。

## 9. 回调接入

创建任务时可传入：

```json
{
  "callback_url": "https://your-domain.example.com/callbacks/seedance"
}
```

方舟会在任务状态变化时向该地址发送 `POST` 请求，消息结构与查询任务返回结构一致。成功或失败通知在短时间内投递失败时，平台会有限次重试。

回调接收接口应快速完成校验和入队，不要在回调 HTTP 请求中同步下载大视频或执行长事务。推荐流程：

```text
方舟 POST 回调
  ↓
校验 JSON 与 task_id
  ↓
查询方舟任务接口复核状态
  ↓
按 task_id 幂等更新本地记录
  ↓
写入下载队列
  ↓
返回 HTTP 2xx
```

建议：

1. 回调接口使用 HTTPS。
2. 收到回调后按任务 ID 再调用查询接口确认最终状态。
3. 以任务 ID 做幂等，避免重复通知造成重复入库或重复结算。
4. 不在回调 URL 中携带 API Key。
5. 回调处理失败时返回非 2xx，成功落库后再返回 2xx。

官方视频任务文档没有在上述回调字段中声明业务方可直接使用的签名字段，因此不要只凭回调正文认定任务成功。最稳妥的办法是使用服务端保存的方舟 API Key，按回调中的 `task_id` 再查询一次官方任务接口。

## 10. 错误处理与重试

视频生成可能返回输入或输出安全审核错误，例如：

| HTTP | 官方错误码示例 | 说明 |
| --- | --- | --- |
| `400` | `InputTextSensitiveContentDetected` | 输入文本触发安全审核 |
| `400` | `InputImageSensitiveContentDetected` | 输入图片触发安全审核 |
| `400` | `OutputVideoSensitiveContentDetected` | 生成结果触发安全审核 |
| `429` | `QuotaExceeded` | 配额或并发限制 |

### 10.1 HTTP 状态处理

| HTTP 状态 | 是否建议重试 | 处理方式 |
| --- | --- | --- |
| `200` | 不适用 | 解析 JSON；仍需检查任务自身 `status` |
| `400` | 否 | 修正请求字段、素材或审核问题后重新创建 |
| `401` | 否 | 检查 Bearer 格式、Key 是否失效 |
| `403` | 否 | 检查项目、模型、接入点权限及 IP 白名单 |
| `404` | 否 | 检查任务 ID、Key 所属项目以及任务是否已过保留期 |
| `409` | 视错误语义 | 避免重复操作，先查询现有状态 |
| `429` | 是 | 根据响应提示等待，并使用指数退避 |
| `500`、`502`、`503`、`504` | 是 | 有限重试并增加随机抖动；持续失败时记录请求 ID 并报障 |

### 10.2 重试边界

查询接口是读取操作，可以安全地进行有限重试。创建任务可能产生费用，重试前必须区分：

- **连接尚未建立就失败**：通常可以重试。
- **服务端明确返回失败状态**：按 HTTP 状态和错误码决定是否重试。
- **请求已发出但读取响应超时**：服务端可能已经创建成功，不能立即无脑重发。

生产系统应为每次业务生成请求创建自己的 `client_request_id`，并在本地数据库中记录“准备提交、提交中、已取得 task_id”等状态。这里的业务请求号用于本地防重，不要把它当作方舟官方幂等参数。

指数退避示例：

```text
第1次失败：等待约 2 秒
第2次失败：等待约 4 秒
第3次失败：等待约 8 秒
第4次失败：等待约 16 秒
上限：30～60 秒，并增加少量随机抖动
```

处理建议：

- `400` 参数或审核错误：不要原样无限重试，应修正输入后重新创建任务。
- `401/403` 鉴权错误：检查 API Key、项目、模型权限、IP 白名单和接入点授权。
- `429`：按指数退避重试，避免立即高频重放。
- `5xx` 或网络超时：使用同一业务请求号控制重试，防止创建重复任务。
- 创建接口发生读取超时时，先查询业务侧是否已经保存任务 ID；不要盲目重复扣费调用。
- 记录响应头中的请求 ID，便于向火山技术支持排查。

### 10.3 常见排查清单

#### API Key forbidden by IP whitelist

1. 在实际调用服务器上查询公网出口 IP。
2. 注意容器、NAT 网关、代理或负载均衡可能改变出口 IP。
3. 将实际 `clientIP` 加入方舟 API Key 白名单。
4. 保存配置后等待生效，再从同一服务器重试。

#### 素材 URL 返回 403

1. 用无 Cookie 的 `curl` 请求素材 URL。
2. 检查对象存储是否为私有桶。
3. 私有桶应生成有效期足够长的签名 URL。
4. 检查防盗链 Referer、User-Agent 限制和 CDN 鉴权。
5. 检查 URL 是否在方舟真正拉取前已经过期。

#### 返回 429

1. 查看是否达到模型并发、接入点并发、RPM 或排队任务限制。
2. 降低本地提交并发，不能只提高重试频率。
3. 查询已有任务是否长期停留在 `queued` 或 `running`。
4. 确有业务需要时在方舟控制台调整接入点限流或申请扩容。

#### 返回成功但效果不符合预期

1. 确认调用的实际模型版本，而不是只看请求中的 Endpoint ID。
2. 明确标注每个参考素材的用途。
3. 缩短单次叙事，减少同一条提示词里的冲突动作。
4. 使用固定种子做 A/B 对比，但不要认为相同种子一定输出完全相同结果。
5. 先用低成本配置验证构图，再生成正式规格。

## 11. 生产环境建议

- API Key 仅保存在服务端环境变量或密钥管理系统中，不下发到浏览器和移动端。
- 按客户或业务项目拆分方舟项目、API Key 和推理接入点，方便权限隔离及用量分析。
- 为 API Key 配置最小模型权限；有固定服务器出口 IP 时可启用 IP 白名单。
- 在调用端设置并发、QPM、每日任务量和异常费用告警。
- 保存 `task_id`、业务请求号、模型 ID、状态、创建时间、最终 URL、用量和上游请求 ID。
- 对公网图片、视频和音频 URL 做域名、协议、大小和内容类型校验，防止 SSRF 和恶意文件。
- 不记录完整 API Key；日志最多保留不可逆摘要或末尾少量字符。

### 11.1 计费与用量

视频生成任务成功后，查询结果中的 `usage.completion_tokens` 可用于记录该次任务的输出用量。基础估算公式为：

```text
预估模型费用 = completion_tokens ÷ 1,000,000 × 当前模型单价
```

截至本文更新时间，方舟产品页展示的 Seedance 2.0 系列参考单价如下：

| 模型 | 含视频输入 | 无视频输入 |
| --- | ---: | ---: |
| Doubao-Seedance-2.0 | 28 元/百万 tokens | 46 元/百万 tokens |
| Doubao-Seedance-2.0-fast | 22 元/百万 tokens | 37 元/百万 tokens |
| Doubao-Seedance-2.0-mini | 14 元/百万 tokens | 23 元/百万 tokens |

价格属于时间敏感信息，只能作为 2026-08-31 的文档快照。结算、折扣、权益包和新模型价格必须以[火山方舟产品价格页](https://www.volcengine.com/product/ark)以及账号账单为准。

计费注意事项：

- API 调试器发起的真实生成也可能产生费用。
- 创建成功并不等于最终一定产生与成功视频相同的用量，应以账单和用量统计为准。
- 业务侧可以按任务保存 token，但不能仅凭自行计算的数据替代火山正式账单。
- 使用 TOS 长期存储结果时，还可能产生对象存储和公网流量费用，这不属于 Seedance 模型推理费。
- 失败重试可能创建新任务并产生额外费用，因此必须限制次数并做业务防重。

### 11.2 推荐本地任务表

至少保存以下字段：

```text
client_request_id       业务侧唯一请求号
ark_task_id             方舟任务 ID
model_requested         请求中的 Model ID 或 Endpoint ID
model_actual            查询结果返回的实际模型版本
status                  本地同步的方舟任务状态
prompt_hash             提示词摘要，不一定保存完整敏感提示词
source_refs             输入素材引用，敏感 URL 应脱敏或加密
resolution
ratio
duration
generate_audio
completion_tokens
video_url_original      方舟临时结果地址
video_object_key        自有对象存储路径
error_code
error_message
upstream_request_id
created_at
updated_at
completed_at
```

对 `ark_task_id` 建唯一索引，对 `client_request_id` 建唯一索引，可以降低回调重复和业务重复提交造成的数据不一致。

### 11.3 并发控制

建议同时控制：

- 创建任务 QPS/RPM；
- 当前 `queued + running` 任务数；
- 单个客户或业务项目并发；
- 结果下载并发；
- 每日生成任务量或 token 用量；
- 连续失败率和 429 比例。

本地并发上限应略低于方舟或接入点上限，留出人工调试、补偿任务和平台统计延迟的余量。

### 11.4 监控指标

推荐监控：

| 指标 | 目的 |
| --- | --- |
| 创建请求量、成功率和延迟 | 发现入口异常 |
| `queued` 数量及排队时长 | 发现容量不足 |
| `running` 数量及执行时长 | 发现任务卡住或模型变慢 |
| `succeeded/failed/expired` 比例 | 衡量生成稳定性 |
| 400 审核错误数量 | 发现素材或提示词风险 |
| 401/403 数量 | 发现凭证、权限或白名单错误 |
| 429 数量 | 发现并发或配额不足 |
| token 用量 | 成本统计和异常消耗预警 |
| 下载成功率与文件大小 | 防止结果丢失或空文件 |
| 回调延迟与重复次数 | 发现回调链路问题 |

### 11.5 上线验收清单

- [ ] Key 未进入前端包、Git、日志和错误响应。
- [ ] 使用真实服务器出口 IP 验证白名单。
- [ ] 文生视频任务能够创建、查询并下载。
- [ ] 参考图/视频/音频按目标模型分别验证。
- [ ] `failed`、`expired`、`cancelled` 都有明确本地状态。
- [ ] 429 会退避，不会形成重试风暴。
- [ ] 创建超时不会自动无限重复创建任务。
- [ ] 回调重复到达不会重复入账或重复下载。
- [ ] 结果会转存到自有对象存储。
- [ ] 已建立用量、失败率和排队时长告警。
- [ ] 人像及版权素材已获得所需授权。

## 12. 与本仓库现有系统的边界

本文档中的请求：

- 直接访问 `ark.cn-beijing.volces.com`；
- 使用火山方舟原生 API Key；
- 不访问本项目部署域名；
- 不使用本系统签发的业务 API Key；
- 不经过本系统的项目、额度、素材账本、管理员认证或代理接口。

因此，这份文档可以单独交付给只需要调用火山方舟 Seedance 原生接口的开发人员。

## 13. 常见问题

### 13.1 可以直接在浏览器前端调用吗？

技术上浏览器可以发 HTTP 请求，但生产环境不应这样做，因为方舟 API Key 会暴露给终端用户。正确方式是由自己的服务端保管 Key，再由前端调用自己的受控业务接口。

### 13.2 创建任务接口能直接上传本地文件吗？

不能把本地文件二进制直接塞进上述 JSON。应先将素材上传至可访问的对象存储，获得 HTTPS URL；或先将素材录入方舟素材库，再传 `asset://...`。

### 13.3 一个方舟 API Key 能否调用多个模型？

可以，只要该 Key 的权限范围包含这些 Model ID 或 Endpoint ID。Key 的权限与接入点绑定的模型是两个概念：一个接入点通常指向一个模型，但一枚 Key 可以被授权访问多个模型或多个接入点。

### 13.4 是否必须创建推理接入点？

`model` 支持 Model ID 或 Endpoint ID。能否直接使用 Model ID 以及是否要求创建接入点，以目标模型当前的开通方式和控制台提示为准。需要独立接入点限流和治理时可使用 Endpoint ID。

### 13.5 如何限制并发为 1？

可以在自建服务中按 Key、客户或模型设置并发信号量为 1；如果方舟推理接入点页面提供接入点限流，也可以把接入点并发设置为 1。生产环境通常同时保留本地限流，因为它可以在请求到达方舟前阻止超额提交。

### 13.6 为什么同一个 Key 能创建任务，却查询不到另一个任务？

重点检查任务是否由同一个账号、项目和权限范围下的 Key 创建，任务 ID 是否完整，以及任务记录是否超过平台保留期。不要用客户提交的任意任务 ID 直接查询，应在业务数据库中校验任务归属。

### 13.7 为什么使用相同 `seed` 结果仍可能不同？

`seed` 用于控制随机性，但模型版本、服务实现、素材处理和其他参数变化都可能影响结果。它适合提高可复现性，不应当作输出逐字节一致的保证。

### 13.8 如何获取准确费用？

单个任务可记录查询结果中的 token 用量；账号级真实费用应查看方舟用量统计和火山引擎账单。业务侧估算适合预警和客户报表，不替代云厂商结算。

### 13.9 有没有完全不产生费用的生成测试？

任务列表接口可用于免费验证基础鉴权和网络，但无法验证模型生成能力。API Explorer 和真实创建任务都可能产生费用。生成测试应选择较短时长和适当分辨率，并在执行前确认最新价格。

### 13.10 Seedance 2.5 的 `model` 应该填什么？

在方舟模型列表或目标在线推理接入点详情中复制当前 Model ID/Endpoint ID。不要照着展示名称猜测字符串；模型发布日期和 ID 后缀可能变化。

## 14. 官方资料

- [视频生成 API 总览](https://www.volcengine.com/docs/82379/1520758?lang=zh)
- [创建视频生成任务](https://api.volcengine.com/api-docs/view?action=CreateContentsGenerationsTasks&serviceCode=ark&version=2024-01-01)
- [查询视频生成任务](https://api.volcengine.com/api-docs/view?action=GetContentsGenerationsTask&serviceCode=ark&version=2024-01-01)
- [查询视频生成任务列表](https://api.volcengine.com/api-docs/view?action=ListContentsGenerationsTasks&serviceCode=ark&version=2024-01-01)
- [取消或删除视频生成任务](https://api.volcengine.com/api-docs/view?action=DeleteContentsGenerationsTasks&serviceCode=ark&version=2024-01-01)
- [Seedance 2.0 提示词指南](https://www.volcengine.com/docs/82379/2222480?lang=zh)
- [Seedance 2.0 系列教程](https://www.volcengine.com/docs/82379/2291680?lang=zh)
- [方舟可信素材库说明](https://www.volcengine.com/docs/82379/2315856?lang=zh)
- [方舟模型列表](https://www.volcengine.com/docs/82379/1799865?lang=zh)
- [火山方舟产品与价格](https://www.volcengine.com/product/ark)
- [方舟 API Key 管理](https://console.volcengine.com/ark/region:ark+cn-beijing/apikey)

---

更新时间：2026-08-31。模型能力、限流和计费规则可能调整，正式上线前请以火山引擎方舟控制台及对应模型的最新官方文档为准。
