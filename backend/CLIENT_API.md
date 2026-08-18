# Avatar Proxy 客户 API 接入文档

版本：1.2
适用对象：通过程序、脚本或自动化任务调用素材库与 Seedance 视频生成服务的客户。

> 结论：客户不需要运行或操作任何前端。服务方签发一枚 `vap_live_...` 业务 API Key 后，客户即可通过本文件中的 HTTP API 完成鉴权、素材管理、图片上传、视频生成、任务轮询、取消、历史查询和用量查询。

## 1. 接入信息

正式环境应由服务方提供 HTTPS 地址，例如：

```text
BASE_URL=https://api.example.com
API_KEY=vap_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

当前服务器的临时验收地址是 `http://101.96.224.33:8088`。该地址没有 HTTPS，API Key 会以明文方式经过网络，不应作为客户生产地址。

除 `/health` 和 `/api/video/ark-usage` 外，本文客户接口均使用服务方签发的业务 API Key：

```http
Authorization: Bearer vap_live_xxx
Accept: application/json
```

发送 JSON 时增加：

```http
Content-Type: application/json
```

业务 API Key 与内部管理员令牌完全不同：

- 客户只使用 `vap_live_...`，不得接触 `X-Admin-Token`。
- API Key 只在创建时完整显示一次，应放在服务器环境变量或密钥管理系统中。
- 每枚 API Key 绑定一个项目；服务端会自动注入项目标识。
- 客户传入的 `ProjectName` 或 `projectName` 会被忽略，不能跨项目访问素材。
- API Key 被禁用或删除后，所有客户接口立即返回 `401`。

`/api/video/ark-usage` 是一个独立的火山方舟用量查询入口。该接口的 Bearer Token 是客户自己的方舟 API Key，而不是 `vap_live_...` 业务 API Key；详细规则见 7.3。

## 2. 五分钟快速接入

### 2.1 验证 API Key

```bash
curl "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $API_KEY"
```

成功响应：

```json
{
  "authenticated": true,
  "apiKeyId": "3ee92a25-4dd8-42c6-9af5-b8d74891f870"
}
```

### 2.2 创建视频任务

```bash
curl -X POST "$BASE_URL/api/video/generate" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
      {"type": "text", "text": "一只橘猫坐在窗边看雨，电影感镜头"}
    ],
    "ratio": "16:9",
    "duration": 5,
    "resolution": "720p",
    "generateAudio": true,
    "returnLastFrame": false
  }'
```

成功时返回 Seedance 任务，其中最重要的字段是：

```json
{
  "id": "cgt-xxxxxxxx",
  "model": "doubao-seedance-2-0-260128",
  "status": "queued",
  "created_at": 1786377600
}
```

### 2.3 轮询任务

```bash
curl "$BASE_URL/api/video/task/cgt-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

持续轮询，直到 `status` 进入终态。常见状态包括 `queued`、`running`、`succeeded`、`failed`、`cancelled`。成功时从响应的 `content.video_url`、`output.video_url` 或顶层 `video_url` 读取视频地址。

建议轮询间隔为 5～10 秒，并设置总超时；不要无间隔循环请求。

## 3. 接口总览

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 服务健康检查，无需 API Key |
| `GET` | `/api/auth/me` | 验证业务 API Key |
| `POST` | `/api/asset-group/create` | 创建素材组 |
| `GET` | `/api/asset-group/list` | 分页查询素材组 |
| `GET` | `/api/asset-group/get` | 查询单个素材组 |
| `PUT` | `/api/asset-group/update` | 更新素材组 |
| `DELETE` | `/api/asset-group/delete` | 删除素材组 |
| `POST` | `/api/asset/create` | 从公网图片 URL 或已上传文件创建素材 |
| `GET` | `/api/asset/list` | 分页查询素材 |
| `GET` | `/api/asset/get` | 查询单个素材 |
| `PUT` | `/api/asset/update` | 修改素材名称 |
| `DELETE` | `/api/asset/delete` | 删除素材 |
| `POST` | `/api/asset/upload-file` | 上传本地图片到 TOS |
| `POST` | `/api/video/generate` | 创建 Seedance 视频任务 |
| `GET` | `/api/video/task/{taskId}` | 查询视频任务 |
| `POST` | `/api/video/task/{taskId}/cancel` | 取消视频任务 |
| `GET` | `/api/video/history` | 查询当前 API Key 的任务历史 |
| `POST` | `/api/video/history/import` | 导入旧任务记录 |
| `DELETE` | `/api/video/history/{taskId}` | 从历史中隐藏单个任务 |
| `DELETE` | `/api/video/history` | 清空当前 API Key 的可见历史 |
| `GET` | `/api/video/usage` | 查询视频 Token 用量 |
| `GET` | `/api/video/ark-usage` | 使用方舟 API Key 查询火山侧 Seedance 聚合用量 |

## 4. 素材组接口

素材组与素材接口将请求转发给火山引擎素材库，响应 JSON 保持上游格式，并带有响应头：

```http
X-Upstream-Service: volcengine-ark
```

上游常见响应结构为：

```json
{
  "ResponseMetadata": {"RequestId": "..."},
  "Result": {}
}
```

### 4.1 创建素材组

`POST /api/asset-group/create`

```json
{
  "name": "主要角色",
  "description": "批量视频使用的人物素材"
}
```

约束：`name` 1～128 字符，`description` 最多 1000 字符。服务端固定创建 `AIGC` 类型素材组。

### 4.2 查询素材组

`GET /api/asset-group/list`

| 查询参数 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|
| `pageNumber` | 否 | `1` | 页码，从 1 开始 |
| `pageSize` | 否 | `20` | 每页 1～100 条 |
| `name` | 否 |  | 名称筛选 |
| `groupIds` | 否 |  | 可重复传递，例如 `groupIds=a&groupIds=b` |

### 4.3 查询单个素材组

`GET /api/asset-group/get?groupId=<GROUP_ID>`

### 4.4 更新素材组

`PUT /api/asset-group/update`

```json
{
  "groupId": "group-xxxxxxxx",
  "name": "新名称",
  "description": "新描述"
}
```

`name` 与 `description` 至少提供一个。

### 4.5 删除素材组

`DELETE /api/asset-group/delete?groupId=<GROUP_ID>`

删除前应确认上游对组内素材的处理规则；不要把删除请求作为批量清理的默认动作。

## 5. 素材接口

### 5.1 从公网 URL 创建图片素材

`POST /api/asset/create`

```json
{
  "groupId": "group-xxxxxxxx",
  "url": "https://assets.example.com/person.png",
  "name": "人物正面照"
}
```

`url` 必须以 `http://` 或 `https://` 开头，最长 2048 字符。生产环境建议只使用稳定的 HTTPS 公网地址。

如果图片刚刚由本系统的 `/api/asset/upload-file` 上传，应同时传回响应中的 `uploadId`：

```json
{
  "groupId": "group-xxxxxxxx",
  "url": "https://assets.example.com/avatar-assets/project/uuid-person.png",
  "uploadId": "upload_0123456789abcdef",
  "name": "人物正面照"
}
```

`uploadId` 只能由上传它的同一枚 API Key 使用，并且同时提交的 `url` 必须与上传接口返回的 URL 完全一致；不一致时返回 `409 upload_url_mismatch`。旧客户端可以继续只传 `url`；建议新客户端保留并回传 `uploadId`，以便服务端可靠关联素材与 TOS 对象，在删除素材时同步释放存储。

### 5.2 查询素材列表

`GET /api/asset/list`

| 查询参数 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|
| `groupId` | 是 |  | 素材组 ID |
| `pageNumber` | 否 | `1` | 页码 |
| `pageSize` | 否 | `20` | 每页 1～100 条 |
| `name` | 否 |  | 名称筛选 |
| `statuses` | 否 |  | 可重复传递的状态筛选 |
| `sortBy` | 否 | `CreateTime` | 排序字段 |
| `sortOrder` | 否 | `Desc` | `Asc` 或 `Desc` |

示例：

```bash
curl "$BASE_URL/api/asset/list?groupId=group-xxx&pageNumber=1&pageSize=100&statuses=Active" \
  -H "Authorization: Bearer $API_KEY"
```

### 5.3 查询、更新和删除单个素材

```http
GET    /api/asset/get?assetId=<ASSET_ID>
DELETE /api/asset/delete?assetId=<ASSET_ID>
```

更新名称：

```http
PUT /api/asset/update
Content-Type: application/json
```

```json
{
  "assetId": "asset-xxxxxxxx",
  "name": "新的素材名称"
}
```

### 5.4 上传本地图片

`POST /api/asset/upload-file`

请求格式为 `multipart/form-data`，字段名必须是 `file`：

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./person.png"
```

支持 JPEG、PNG、WebP。默认最大 10 MiB，实际限制由服务端配置决定。服务端会校验 MIME 类型与文件内容签名。

成功响应：

```json
{
  "url": "https://assets.example.com/avatar-assets/project/uuid-person.png",
  "uploadId": "upload_0123456789abcdef",
  "objectKey": "avatar-assets/project/uuid-person.png",
  "contentType": "image/png",
  "size": 123456,
  "etag": "...",
  "requestId": "..."
}
```

如果需要将上传文件注册为素材，继续把响应中的 `url` 和 `uploadId` 一起传给 `POST /api/asset/create`。未注册成功的上传文件保留 48 小时，之后由服务端自动清理。

## 6. 视频生成接口

视频接口响应来自 Seedance，并带有：

```http
X-Upstream-Service: volcengine-seedance
```

### 6.1 创建视频任务

`POST /api/video/generate`

完整请求字段：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `model` | 是 | string | 模型 ID，推荐 `doubao-seedance-2-0-260128` |
| `content` | 是 | array | 至少一项非空文本，可附带最多 9 张参考图 |
| `callbackUrl` | 否 | string | 上游任务回调 URL，必须是 HTTP(S) |
| `returnLastFrame` | 否 | boolean | 是否返回末帧 |
| `generateAudio` | 否 | boolean | 是否生成音频 |
| `ratio` | 否 | string | 如 `16:9`、`9:16`、`1:1`、`4:3`、`3:4` |
| `duration` | 否 | integer | 1～60 秒；省略时由模型决定 |
| `resolution` | 否 | string | 如 `720p`、`1080p`，以模型能力为准 |
| `seed` | 否 | integer | 随机种子 |
| `cameraFixed` | 否 | boolean | 是否固定相机 |
| `watermark` | 否 | boolean | 是否添加水印 |
| `serviceTier` | 否 | string | 上游服务等级 |
| `metadata` | 否 | object | 只用于本服务保存任务历史，不发送给 Seedance |

纯文本生成：

```json
{
  "model": "doubao-seedance-2-0-260128",
  "content": [
    {"type": "text", "text": "雨夜中的未来城市，镜头缓慢向前推进"}
  ],
  "ratio": "16:9",
  "duration": 5,
  "resolution": "720p",
  "generateAudio": true,
  "returnLastFrame": false
}
```

使用素材库参考图：

```json
{
  "model": "doubao-seedance-2-0-260128",
  "content": [
    {"type": "text", "text": "图片1中的人物拿起图片2中的产品"},
    {
      "type": "image_url",
      "image_url": {"url": "asset://asset-xxxxxxxx"},
      "role": "reference_image"
    },
    {
      "type": "image_url",
      "image_url": {"url": "https://assets.example.com/product.png"},
      "role": "reference_image"
    }
  ],
  "ratio": "9:16",
  "duration": 5,
  "resolution": "720p"
}
```

`asset://` 后必须是完整素材 ID。不要把已有 `asset-` 前缀再拼接一次。

`metadata` 示例：

```json
{
  "metadata": {
    "prompt": "客户侧显示的提示词",
    "promptDocument": "可选的富文本或 JSON 字符串",
    "assets": [
      {"id": "asset-xxx", "groupId": "group-xxx", "name": "主角"}
    ],
    "durationMode": "seconds",
    "generationCount": 1
  }
}
```

注意：`metadata.generationCount` 只是历史记录字段，不会让服务端自动创建多条视频。要生成 N 条结果，客户程序必须调用 `POST /api/video/generate` N 次。

### 6.2 查询任务

`GET /api/video/task/{taskId}`

`taskId` 只能包含字母、数字、下划线和短横线，最长 128 字符。每次成功查询都会同步本服务中的任务状态、视频 URL、末帧 URL 和 Token 用量。

### 6.3 取消任务

`POST /api/video/task/{taskId}/cancel`

建议只取消 `queued` 或 `running` 状态的任务。上游成功取消时可能返回 `204 No Content`。

## 7. 历史与用量

### 7.1 查询历史

`GET /api/video/history?limit=100`

`limit` 范围为 1～100。历史严格按当前 API Key 隔离：即使两枚 Key 属于同一项目，也不会互相看到历史。

```json
{
  "tasks": [
    {
      "id": "cgt-xxxxxxxx",
      "createdAt": 1786377600000,
      "prompt": "角色走进雨夜街道",
      "model": "doubao-seedance-2-0-260128",
      "ratio": "16:9",
      "duration": 5,
      "resolution": "720p",
      "status": "succeeded",
      "videoUrl": "https://.../video.mp4"
    }
  ]
}
```

删除历史只会在本地隐藏记录，不会删除上游视频任务或视频文件：

```http
DELETE /api/video/history/{taskId}
DELETE /api/video/history
```

`POST /api/video/history/import` 主要用于从旧版浏览器数据迁移，普通 API 客户通常不需要。单次最多导入 100 条。

### 7.2 查询用量

`GET /api/video/usage?days=14`

`days` 允许 7～30，默认 14。

```json
{
  "summary": {
    "inputTokens": 0,
    "outputTokens": 35800,
    "totalTokens": 35800,
    "requestCount": 1
  },
  "daily": [
    {
      "date": "2026-08-11",
      "inputTokens": 0,
      "outputTokens": 35800,
      "totalTokens": 35800,
      "requestCount": 1
    }
  ]
}
```

该接口只统计经过本系统视频代理、且火山任务响应中包含 `usage` 的记录，不代表该方舟 Key 在火山侧的全部消耗。

### 7.3 使用方舟 API Key 查询火山侧用量

`GET /api/video/ark-usage?start=2026-08-01&end=2026-08-18&interval=Day`

该接口用于查询客户直接调用火山方舟产生的 Seedance 聚合用量。此处必须使用客户自己的方舟 API Key：

```bash
curl "$BASE_URL/api/video/ark-usage?start=2026-08-01&end=2026-08-18&interval=Day" \
  -H "Authorization: Bearer $ARK_API_KEY"
```

参数：

- `start`、`end`：必填，格式为 `YYYY-MM-DD`，单次跨度不能超过 31 天。
- `interval`：可选，`Day` 或 `Hour`，默认 `Day`。
- API Key 只从 `Authorization` 请求头读取，不允许放入 URL。

成功响应示例：

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
      "requestCount": 2,
      "inputTokens": 0,
      "outputTokens": 35800,
      "totalTokens": 35800
    }
  ],
  "upstreamRequestId": "0217865260..."
}
```

安全与口径说明：

- 后端仅在当前请求内将完整方舟 Key 作为火山用量过滤条件，不落库、不写业务日志，响应只显示末 12 位。
- 查询由服务端 IAM AK/SK 签名完成；服务端 AK/SK 不会返回给客户。
- 只返回模型名包含 `seedance` 的记录，其他文字、图片或语音模型用量不会混入汇总。
- 火山聚合用量通常有约 5～30 分钟延迟，不能用于实时限流。
- `billingAmountIncluded: false` 表示该接口不包含人民币费用；实际账单金额属于 T+1 账单查询，应另设账单接口。
- 返回零用量表示查询区间内没有匹配记录，也可能是 Key 尚未产生聚合数据；不能据此证明 Key 一定有效。

## 8. 错误处理

本服务自身错误：

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "API Key 无效或已禁用"
  }
}
```

参数校验错误使用 FastAPI 的 `422` 格式：

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "content"],
      "msg": "Value error, content 至少包含一项非空文本描述"
    }
  ]
}
```

素材库和 Seedance 返回的业务错误可能保持上游格式。客户程序应同时处理 HTTP 状态码、`error`、`detail` 和 `ResponseMetadata.Error`。

本系统的写入 QPM、并发或素材额度达到硬上限时统一返回 `429`：

```json
{
  "error": {
    "code": "quota_exceeded",
    "message": "额度已用尽",
    "metric": "dailyUploadBytes",
    "scope": "api_key",
    "limit": 1073741824,
    "used": 1073741824,
    "resetAt": "2026-08-14T00:00:00+08:00",
    "requestId": "req_0123456789abcdef"
  }
}
```

- `metric` 表示超限指标；`scope` 为 `project` 或 `api_key`。
- `limit` 和 `used` 使用请求数、文件数或字节数等对应指标单位。
- 自然分钟或自然日可自动恢复的限制会返回 `Retry-After` 响应头；`resetAt` 使用北京时间并带时区。
- 素材总数、TOS 总存储等无固定恢复时间的限制可能返回 `resetAt: null`，需删除素材或联系服务方调整额度。
- 查询 QPM 达到 70%、90%、100% 只记录服务端告警，不阻断客户查询。

| HTTP 状态 | 含义 | 建议 |
|---:|---|---|
| `400` | 请求内容或任务 ID 不合法 | 修正请求，不要自动重试 |
| `401` | API Key 缺失、无效或已禁用 | 停止任务并联系服务方 |
| `404` | 资源或任务不存在 | 检查 ID 与当前 API Key |
| `409` | 资源状态冲突 | 查询当前状态后决定 |
| `413` | 上传文件过大 | 压缩文件后重试 |
| `415` | 不支持的图片格式 | 改用 JPEG、PNG 或 WebP |
| `422` | 参数校验失败 | 根据 `detail` 修正请求 |
| `429` | 本系统或上游的频率、并发或额度限制 | 遵守 `Retry-After`；无恢复时间时停止重试并联系服务方 |
| `502` | 无法连接或上游拒绝 | 指数退避，限制重试次数 |
| `503` | 服务端凭据或存储未配置 | 联系服务方，不要持续重试 |

只对网络错误、`429`、`502` 和部分 `5xx` 做有限重试。推荐退避：1、2、4、8、16 秒，并加入随机抖动。创建视频任务目前不支持幂等键；如果客户端未收到响应，不能确定任务是否已经创建，应记录请求时间并人工或通过历史接口核对，避免盲目重复提交产生费用。

## 9. Python 批量调用示例

安装依赖：

```bash
python -m pip install requests
```

设置环境变量：

```bash
export AVATAR_API_BASE_URL="https://api.example.com"
export AVATAR_API_KEY="vap_live_xxx"
```

下面的程序会以最多 3 个并发创建任务，并以 5 秒间隔轮询。请根据服务方给出的额度调整并发，不要无限开启线程。

```python
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


BASE_URL = os.environ["AVATAR_API_BASE_URL"].rstrip("/")
API_KEY = os.environ["AVATAR_API_KEY"]
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
TERMINAL = {"succeeded", "failed", "cancelled"}


def request(method: str, path: str, **kwargs):
    response = requests.request(
        method,
        f"{BASE_URL}{path}",
        headers=HEADERS,
        timeout=(10, 120),
        **kwargs,
    )
    response.raise_for_status()
    return response.json() if response.content else None


def create_task(prompt: str) -> str:
    data = request("POST", "/api/video/generate", json={
        "model": "doubao-seedance-2-0-260128",
        "content": [{"type": "text", "text": prompt}],
        "ratio": "16:9",
        "duration": 5,
        "resolution": "720p",
        "generateAudio": True,
        "returnLastFrame": False,
        "metadata": {"prompt": prompt, "generationCount": 1},
    })
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError(f"创建成功但没有任务 ID: {data}")
    return task_id


def wait_task(task_id: str, timeout_seconds: int = 1800):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        task = request("GET", f"/api/video/task/{task_id}")
        status = str(task.get("status", "")).lower()
        if status in TERMINAL:
            return task
        time.sleep(5)
    raise TimeoutError(f"任务轮询超时: {task_id}")


def run_one(prompt: str):
    task_id = create_task(prompt)
    result = wait_task(task_id)
    video_url = (
        (result.get("content") or {}).get("video_url")
        or (result.get("output") or {}).get("video_url")
        or result.get("video_url")
    )
    return {"prompt": prompt, "taskId": task_id, "status": result.get("status"), "videoUrl": video_url}


prompts = [
    "雨夜中的未来城市，镜头缓慢前进",
    "清晨海边的白色灯塔，航拍镜头",
    "橘猫在窗边看雨，电影感光影",
]

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(run_one, prompt) for prompt in prompts]
    for future in as_completed(futures):
        try:
            print(future.result())
        except Exception as error:
            print({"error": str(error)})
```

实际批处理程序还应把 `prompt`、请求时间、任务 ID、状态和最终 URL 持久化到数据库或文件，不能只保存在内存中。

## 10. 当前能力边界与上线要求

现有接口已经足以让客户完全脱离前端完成自动化，但在开放大批量生产调用前，应处理以下事项：

1. **必须启用 HTTPS。** 当前 IP 地址的 HTTP 服务只能用于验收，不能安全传输 API Key。
2. **约定并发和额度。** 服务端支持项目总额度与 API Key 子额度；交付 Key 时应明确客户的 QPM、并发、每日上传和素材上限。当前限流是单实例实现，横向扩容前需迁移到共享计数器。
3. **增加创建任务幂等性。** 当前 `POST /api/video/generate` 不接受幂等键，网络重试可能重复计费。
4. **稳定响应契约。** 素材与视频响应目前大部分透传上游；上游字段变化会直接影响客户。长期应增加 `/api/v1` 并统一响应模型。
5. **明确模型参数矩阵。** 不同 Seedance 模型支持的分辨率、比例、时长和音频能力可能不同，应由服务方随模型升级维护。
6. **保留单实例约束。** 当前业务数据使用 SQLite，适合单实例；若要横向扩容，应先迁移到 PostgreSQL 等共享数据库。
7. **监控与审计。** 应监控 `/health`、上游错误率、请求延迟、磁盘、数据库备份和 Token 用量。

完成 HTTPS、限流和幂等性后，本文件即可作为客户的单一接入文档；内部项目创建、API Key 签发、禁用和删除仍由服务方管理，不对客户开放。
