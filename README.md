# Avatar Proxy（前后端分离版）

火山方舟私域虚拟人像素材资产库的 API 网关与管理控制台。

```text
浏览器 ──HTTP──> Next/Vinext 前端
                    │
                    └──HTTP──> Python FastAPI 后端 ──签名请求──> Volcengine Ark
                                      │
                                      └── SQLite（项目、API Key、调用日志）
```

## 目录

- `app/`：前端控制台，只包含界面和后端 HTTP 客户端。
- `backend/`：Python FastAPI 后端，包含鉴权、SQLite、火山签名及接口代理。
- `.env.example`：前端后端地址配置。
- `backend/.env.example`：后端密钥、数据库和 CORS 配置。

## 1. 启动 Python 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[test]"
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

在 `backend/.env` 中配置：

```text
VOLCENGINE_ACCESS_KEY=火山引擎AK
VOLCENGINE_SECRET_KEY=火山引擎SK
CONSOLE_ADMIN_TOKEN=至少32位随机字符串
DATABASE_PATH=./data/avatar_proxy.db
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
```

后端健康检查：`GET http://localhost:8000/health`

Swagger 文档：`http://localhost:8000/docs`

也可以使用 Docker：

```bash
docker compose up --build backend
```

## 2. 启动前端

复制 `.env.example` 为 `.env.local`：

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

然后：

```bash
npm install
npm run dev
```

打开控制台后使用后端的 `CONSOLE_ADMIN_TOKEN` 解锁。

## 业务接口

所有接口使用：

```text
Authorization: Bearer vap_live_xxx
Content-Type: application/json
```

| 方法 | 路径 | 上游 Action |
| --- | --- | --- |
| POST / GET | `/api/v1/asset-groups` | CreateAssetGroup / ListAssetGroups |
| GET / PATCH / DELETE | `/api/v1/asset-groups/{id}` | Get / Update / DeleteAssetGroup |
| POST / GET | `/api/v1/assets` | CreateAsset / ListAssets |
| GET / PATCH / DELETE | `/api/v1/assets/{id}` | Get / Update / DeleteAsset |

后端固定使用官网参数：

- Service：`ark`
- Region：`cn-beijing`
- Version：`2024-01-01`
- GroupType：`AIGC`
- `ProjectName`：从调用方 API Key 自动注入，客户端不能覆盖。

## 安全设计

- 火山 AK/SK 只存在 Python 后端环境变量中。
- API Key 仅保存 SHA-256 哈希，完整值只在创建时返回一次。
- 项目由 API Key 强制绑定，防止跨项目访问。
- 请求日志不保存业务请求体。
- 控制台管理接口使用独立的 `X-Admin-Token`。
- CORS 仅允许 `CORS_ORIGINS` 中配置的前端域名。

## 测试

```bash
npm test
npm run lint

cd backend
pytest
```

官方参考：[私域虚拟人像素材资产库使用指南](https://docs.volcengine.com/docs/82379/2333565?lang=zh)。
