# 瑞池素材管理 API 接入文档

版本：2.2
正式地址：`https://api.richbest.cn`

本文档面向直接通过 HTTP API 接入的客户。调用过程不依赖控制台或其他前端页面，可从客户自己的后端服务、命令行程序或批处理脚本发起请求。

## 1. 当前能力状态

当前开放：

- 上传 JPEG、PNG、WebP 图片；
- 创建、查询、修改和删除素材组；
- 将图片登记到素材组；
- 查询、修改和删除素材；
- 验证业务 API Key。

当前暂不可用：

- 纯文本生成视频；
- 图生视频；
- 依赖 Seedance 上游服务的视频任务查询和取消。

视频功能暂不可用的原因是服务端火山 Seedance API Key 已停用。素材上传和素材库使用独立的对象存储及素材服务配置，不受 Seedance API Key 停用影响。

火山 Seedance API Key 不是客户请求参数。后续如恢复视频能力，该 Key 仍通过约定的安全渠道线下人工交付并由服务端配置，客户请求中不要传入火山 Key。

## 2. 地址与鉴权

所有接口均使用以下正式地址：

```text
https://api.richbest.cn
```

除 `/health` 外，所有接口都必须携带瑞池签发的 `vap_live_...` 业务 API Key：

```http
Authorization: Bearer vap_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Accept: application/json
```

JSON 请求还需要：

```http
Content-Type: application/json
```

请将业务 API Key 保存在客户自己的后端环境变量或密钥管理服务中，不要写入浏览器前端代码、公开仓库、日志或 URL。

## 3. 接口总览

### 3.1 基础接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 健康检查，无需鉴权 |
| `GET` | `/api/auth/me` | 验证业务 API Key |

### 3.2 素材上传和素材组

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/asset/upload-file` | 上传图片并取得公网 URL |
| `POST` | `/api/asset-group/create` | 创建素材组 |
| `GET` | `/api/asset-group/list` | 查询素材组列表 |
| `GET` | `/api/asset-group/get` | 查询单个素材组 |
| `PUT` | `/api/asset-group/update` | 修改素材组 |
| `DELETE` | `/api/asset-group/delete` | 删除素材组 |

### 3.3 素材管理

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/asset/create` | 将图片登记到素材组 |
| `GET` | `/api/asset/list` | 查询素材列表 |
| `GET` | `/api/asset/get` | 查询单个素材 |
| `PUT` | `/api/asset/update` | 修改素材名称 |
| `DELETE` | `/api/asset/delete` | 删除素材 |

## 4. 验证业务 API Key

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

每枚业务 API Key 已绑定项目。客户不需要、也不能通过请求体覆盖 `projectName`。

## 5. 推荐素材接入流程

1. 调用 `/api/auth/me` 验证业务 API Key；
2. 调用 `/api/asset-group/create` 创建素材组并保存素材组 ID；
3. 调用 `/api/asset/upload-file` 上传本地图片并取得 `url`；
4. 调用 `/api/asset/create`，使用素材组 ID 和上传结果中的 `url` 登记素材；
5. 调用 `/api/asset/get` 或 `/api/asset/list` 查询素材处理状态；
6. 保存返回的素材 ID，后续查询、修改和删除都需要使用该 ID。

上传文件和登记素材是两个独立步骤。仅上传文件不会自动在素材库中创建素材记录。

## 6. 上传图片

```bash
curl -X POST "$BASE_URL/api/asset/upload-file" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@./portrait.png"
```

要求：

- 表单字段名必须为 `file`；
- 支持 JPEG、PNG、WebP；
- 文件内容必须与声明的 MIME 类型一致；
- 当前默认大小上限为 10 MB，实际以服务端返回为准；
- 不要手动设置 multipart boundary，交给 HTTP 客户端生成。

成功响应示例：

```json
{
  "url": "https://cdn.example.com/avatar-assets/customer_project/xxx-portrait.png",
  "objectKey": "avatar-assets/customer_project/xxx-portrait.png",
  "contentType": "image/png",
  "size": 284931,
  "etag": "xxxxxxxx",
  "requestId": "xxxxxxxx"
}
```

后续登记素材时使用响应中的 `url`。

## 7. 素材组接口

### 7.1 创建素材组

```bash
curl -X POST "$BASE_URL/api/asset-group/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "人物素材",
    "description": "主要角色参考图"
  }'
```

字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `name` | 是 | 素材组名称，1～128 个字符 |
| `description` | 否 | 描述，最多 1000 个字符 |

响应由上游素材服务返回。请保存 `Result.Id` 中的素材组 ID。

### 7.2 查询素材组列表

```bash
curl "$BASE_URL/api/asset-group/list?pageNumber=1&pageSize=20" \
  -H "Authorization: Bearer $API_KEY"
```

可选查询参数：

| 参数 | 说明 |
|---|---|
| `pageNumber` | 页码，默认 1 |
| `pageSize` | 每页数量，1～100，默认 20 |
| `name` | 按名称筛选 |
| `groupIds` | 按素材组 ID 筛选；多个值可重复传递该参数 |

### 7.3 查询单个素材组

```bash
curl "$BASE_URL/api/asset-group/get?groupId=group-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

### 7.4 修改素材组

`name` 和 `description` 至少提供一个：

```bash
curl -X PUT "$BASE_URL/api/asset-group/update" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "groupId": "group-xxxxxxxx",
    "name": "人物素材（已审核）"
  }'
```

### 7.5 删除素材组

```bash
curl -X DELETE "$BASE_URL/api/asset-group/delete?groupId=group-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

删除前请确认该素材组及其内容不再使用。删除操作可能无法恢复。

## 8. 素材接口

### 8.1 登记素材

先上传图片并取得 URL，再调用：

```bash
curl -X POST "$BASE_URL/api/asset/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "groupId": "group-xxxxxxxx",
    "url": "https://cdn.example.com/avatar-assets/customer_project/xxx-portrait.png",
    "name": "角色正面照"
  }'
```

字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `groupId` | 是 | 目标素材组 ID |
| `url` | 是 | HTTP(S) 图片 URL，可直接使用上传接口返回的 `url` |
| `name` | 否 | 素材名称，最多 128 个字符 |

当前接口固定将素材类型登记为图片，客户不需要传 `assetType` 或 `projectName`。

### 8.2 查询素材列表

```bash
curl "$BASE_URL/api/asset/list?groupId=group-xxxxxxxx&pageNumber=1&pageSize=20" \
  -H "Authorization: Bearer $API_KEY"
```

查询参数：

| 参数 | 必填 | 说明 |
|---|---:|---|
| `groupId` | 是 | 素材组 ID |
| `pageNumber` | 否 | 页码，默认 1 |
| `pageSize` | 否 | 每页数量，1～100，默认 20 |
| `name` | 否 | 按名称筛选 |
| `statuses` | 否 | 按状态筛选；多个值可重复传递该参数 |
| `sortBy` | 否 | 排序字段，默认 `CreateTime` |
| `sortOrder` | 否 | 排序方向，默认 `Desc` |

素材进入上游素材库后可能需要异步处理。批量程序应根据列表或详情响应中的状态字段判断素材是否可用。

### 8.3 查询单个素材

```bash
curl "$BASE_URL/api/asset/get?assetId=asset-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

### 8.4 修改素材名称

```bash
curl -X PUT "$BASE_URL/api/asset/update" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "assetId": "asset-xxxxxxxx",
    "name": "角色正面照（新版）"
  }'
```

### 8.5 删除素材

```bash
curl -X DELETE "$BASE_URL/api/asset/delete?assetId=asset-xxxxxxxx" \
  -H "Authorization: Bearer $API_KEY"
```

## 9. Python 批量上传示例

以下示例只负责上传文件。取得每个 `url` 后，再调用 `/api/asset/create` 将其登记到目标素材组。

```python
import os
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE_URL = "https://api.richbest.cn"
API_KEY = os.environ["RICHBEST_API_KEY"]
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def upload_image(path: Path) -> dict:
    content_type = mimetypes.guess_type(path.name)[0]
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError(f"不支持的图片格式：{path}")
    with path.open("rb") as file_handle:
        response = requests.post(
            f"{BASE_URL}/api/asset/upload-file",
            headers=HEADERS,
            files={"file": (path.name, file_handle, content_type)},
            timeout=120,
        )
    response.raise_for_status()
    return {"file": str(path), **response.json()}


image_paths = [
    Path("./images/character-1.png"),
    Path("./images/character-2.jpg"),
]

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(upload_image, path) for path in image_paths]
    for future in as_completed(futures):
        try:
            print(future.result())
        except Exception as error:
            print({"error": str(error)})
```

建议从较小并发开始，遇到 `429` 或 `5xx` 时使用指数退避并限制重试次数。

## 10. 视频接口状态

以下接口当前不要调用：

| 方法 | 路径 | 当前状态 |
|---|---|---|
| `POST` | `/api/video/generate` | 暂不可用，纯文本和图生视频都会失败 |
| `GET` | `/api/video/task/{taskId}` | 暂不可用，需要 Seedance 上游凭证 |
| `POST` | `/api/video/task/{taskId}/cancel` | 暂不可用，需要 Seedance 上游凭证 |

服务端恢复并验证新的火山 Seedance API Key 后，才会重新开放这些接口。客户不能通过请求头或请求体临时传入火山 Seedance API Key。

直接使用火山 Seedance API Key 产生的视频任务、调用量和费用不经过本系统，因此不能通过本文接口查询。相关任务记录和用量请在对应的火山方舟账号或项目中查看。

## 11. 错误处理与安全

本系统错误格式示例：

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "API Key 无效或已禁用"
  }
}
```

| HTTP 状态 | 含义 | 建议 |
|---:|---|---|
| `400` | 请求内容不合法 | 修改请求，不要自动重试 |
| `401` | 业务 API Key 缺失、无效或已禁用 | 停止调用并联系技术支持 |
| `404` | 素材或素材组不存在 | 检查资源 ID |
| `413` | 上传图片超过限制 | 压缩图片后重试 |
| `415` | 图片格式不支持 | 改用 JPEG、PNG 或 WebP |
| `422` | 参数校验失败 | 根据响应中的 `detail` 修改参数 |
| `429` | 请求频率过高 | 指数退避后有限重试 |
| `502` | 上游素材或存储服务请求失败 | 指数退避后有限重试 |
| `503` | 对应服务未配置或暂不可用 | 联系技术支持，不要持续重试 |

安全要求：

- 仅通过 HTTPS 调用；
- 不要在浏览器前端、移动 App 或公开脚本中内置业务 API Key；
- 不要向本文任何接口提交火山 Seedance API Key、AK 或 SK；
- 为批量任务设置并发上限、连接超时和重试上限；
- 删除素材或素材组前先确认影响范围；
- 如业务 API Key 泄露，应立即联系技术支持停用并重新签发。
