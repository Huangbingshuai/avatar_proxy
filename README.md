# Avatar Proxy

Avatar Proxy 是一个面向 ToB 客户的火山引擎素材与 Seedance 接入系统。系统用我方签发的业务 API Key 隔离客户项目，并提供内部管理控制台、客户工具前端和独立 FastAPI 服务。

## 系统组成

```text
内部管理员
  └─ 管理控制台（根目录，Vinext + React）
       └─ 同源 /api/internal/* ──> FastAPI
            ├─ 管理员、Session、TOTP 与审计
            ├─ 项目、业务 API Key 与额度
            ├─ SQLite 备份、校验与恢复
            └─ 磁盘监控与阈值配置

客户浏览器
  └─ user-portal/（React + Vite）
       └─ Bearer vap_live_* ─────> FastAPI

客户程序
  └─ Bearer vap_live_* ─────────> FastAPI
       ├─ AK/SK ──> 火山素材库、IAM 项目校验与用量查询
       ├─ AK/SK ──> TOS 文件中转
       ├─ Ark API Key ──> Seedance 视频任务
       └─ 项目供应商渠道 ──> 方舟 / OpenAI / 阿里百炼 / MiniMax

微信支付平台
  └─ POST /minidrama/payments/callbacks/wechat
       └─ HTTPS 网关透明转发 ──> LocalMiniDrama
            └─ 验签、解密、订单幂等与到账处理
```

三个运行单元彼此独立：

- `app/`：内部管理控制台。
- `backend/`：FastAPI 公网业务与内部管理服务。
- `user-portal/`：客户使用业务 Key 的视频与素材工具。

控制台不会把管理员密码、Session、CSRF、火山 AK/SK 或 Ark API Key 写入浏览器持久存储。客户只获得我方签发的 `vap_live_...` 业务 Key。

## 当前功能

### 客户与业务接口

- 火山 `ProjectName` 对应的本地项目隔离；创建项目时调用 IAM `GetProject` 校验真实存在性。
- 一个项目可签发多枚业务 API Key，Key 可独立禁用并绑定子额度。
- 项目额度、Key 子额度、QPM、写并发、每日上传量、素材总量和 TOS 存储量控制；未配置额度时默认不限额，不影响旧客户。
- 图片、视频和音频上传校验、TOS 中转、素材组管理及素材生命周期账本。
- Seedance 视频任务创建、历史、状态查询与取消。
- 业务 Key 与客户方舟 Key 同项目校验后，查询 Seedance 聚合用量。
- 统一 `429` 限流协议、额度事件、审计与失败清理。
- 可选的多供应商模型中转：使用同一枚 `vap_live_*` 调用 OpenAI 兼容文本、图片和异步视频接口。
- 项目复用加密供应商渠道并统一启用模型；项目下所有有效业务 Key 自动共享项目模型权限。
- 内置模型目录包含 `deepseek-v4-flash`、`glm-5.2`、`seedream-5.0-pro`、方舟当前在售的 7 个 Seedance 视频模型、`wan3.0-video`、`minimax-h3` 和 `image2.0`。已停服的 Seedance 1.0 Lite 不再开放新调用。每个别名在服务端模型目录中固定对应一个真实上游模型 ID，管理员只选择项目渠道，不能手动改写模型 ID。

客户 HTTP 接口、字段和错误码以 [backend/CLIENT_API.md](backend/CLIENT_API.md) 为准。

### 管理员安全

- 系统只允许通过 CLI 初始化一个 `super_admin`；控制台创建的账号固定为普通 `admin`。
- 普通管理员负责项目、业务 API Key、额度和日常业务；超级管理员只负责账号与系统安全管理。
- 密码使用 Argon2id 哈希；管理登录使用 HttpOnly Session Cookie 和 CSRF 双重校验。
- 超级管理员强制绑定 TOTP，并获得仅展示一次的一组恢复码。
- 超级管理员可在控制台验证当前密码和旧 TOTP 后自助更换验证器。
- 删除、启停管理员、重置密码、备份、恢复和监控阈值修改等敏感操作要求再次输入超级管理员密码。
- 禁用账号、修改或重置密码、TOTP 换绑后，相关旧 Session 会立即失效。
- 管理员操作、登录和安全事件写入审计；旧 `X-Admin-Token`/共享控制台令牌不再具备权限。
- 超级管理员负责创建、测试、轮换、禁用和删除供应商渠道；这些凭证操作需要密码与 TOTP 再认证。
- 普通管理员负责项目模型绑定以及中转用量和任务查询，不能读取供应商凭证原文。

### 多供应商模型中转

- 默认 `MULTI_PROVIDER_ENABLED=false`，迁移后没有任何默认模型绑定，旧素材和 `/api/video/*` 行为保持不变。
- 启用时必须配置独立 Fernet 主密钥 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY`；SQLite 只保存凭证密文和尾号掩码。
- 固定使用供应商官方 HTTPS 域名，客户请求不能指定供应商、渠道、项目、Base URL 或真实上游模型 ID。
- `/v1/models` 只返回当前业务 Key 所属项目已启用且渠道可用的模型；Chat Completions、Responses 和图片接口采用 OpenAI 兼容格式。
- 阿里百炼 Wan 和 MiniMax H3 使用统一异步视频任务；任务提交后固定渠道、凭证版本和上游模型，轮换不会破坏旧任务查询。
- 图片和视频支持 `Idempotency-Key`；相同键与相同请求复用结果，不同请求体返回 `409`。
- 只记录供应商真实返回的 Token、图片数和视频秒数，未知字段保持为空；第一阶段不做余额或金额扣费。
- 图片和视频结果 URL 由供应商提供，系统不自动转存 TOS，客户应在供应商链接有效期内下载。

### 备份与恢复

- SQLite 与管理员审计 JSONL 默认每天生成一次一致性快照，默认保留最近 30 组。
- 备份落盘前执行 SQLite 完整性检查。
- 超级管理员可在控制台校验并恢复服务器生成的备份；恢复前自动建立回滚点。
- 恢复期间系统进入维护状态，成功后撤销全部管理员 Session。
- 若未显式设置 `ADMIN_TOTP_ENCRYPTION_KEY`，必须同时备份数据库目录中的 `admin_totp.key`，否则恢复后无法解密已绑定的 TOTP。

当前恢复流程面向单进程、单实例 SQLite 部署。多实例环境必须先统一停写，并迁移到共享数据库方案。

### 磁盘监控与邮件告警

- 后端启动后独立运行磁盘采样任务，不依赖管理员登录或打开控制台。
- 默认每 60 秒采样、每 5 分钟持久化一次；默认监控 `DATABASE_PATH` 所在目录。
- 默认阈值为预警 80%、严重 90%、紧急 95%、恢复线 75%，可由超级管理员在控制台修改。
- 告警升级会去重；磁盘恢复到恢复线以下后发送恢复邮件。
- 邮件失败会按 1 分钟、5 分钟、15 分钟重试，邮件队列与发送状态保存在 SQLite 中。
- SMTP 授权码只从服务端环境变量读取，不写入数据库、日志或管理接口响应。
- 磁盘邮件只用于磁盘容量告警，不与管理员登录等安全事件混用。

### HTTPS 网关与漫剧支付回调

- `api.richbest.cn:443` 统一承载控制台、业务 API、健康检查和漫剧微信支付回调入口。
- 微信通知入口固定为 `POST /minidrama/payments/callbacks/wechat`；非 POST 请求返回 `405`。
- 网关只负责 TLS 终止、路径改写和透明转发，不要求本系统管理员登录或业务 API Key。
- 原始正文、微信支付签名头和上游状态码保持不变；网关不验签、不解密、不操作订单。
- 微信验签、通知解密、订单校验、幂等和到账处理均由 LocalMiniDrama 负责。
- 网关通过宿主机发布端口访问 LocalMiniDrama，不加入 Lens 内部 Docker 网络，避免扩大数据库和 Redis 的网络暴露面。
- 回调日志不记录正文、完整签名、OpenID、商户私钥、API v3 密钥或支付证书。

完整配置、验证和回滚步骤见 [漫剧微信支付回调代理说明](deploy/volcengine/MINIDRAMA_WECHAT_CALLBACK_PLAN.md)。

## 目录说明

| 路径 | 用途 |
|---|---|
| `app/` | 管理控制台页面、管理员 API 客户端、项目/Key/额度与安全管理 UI |
| `backend/app/routers/` | FastAPI 业务与内部管理路由 |
| `backend/app/database.py` | SQLite 表结构、兼容迁移和数据访问 |
| `backend/app/admin_auth.py` | 管理员、Session、CSRF、TOTP、角色和审计 |
| `backend/app/quota.py` | 项目与 Key 额度、原子预占及事件 |
| `backend/app/storage.py` | TOS 上传、素材账本清理与后台重试 |
| `backend/app/backup.py` | SQLite/审计备份、校验和恢复 |
| `backend/app/system_monitor.py` | 磁盘采样、告警状态机和 SMTP 邮件队列 |
| `backend/tests/` | 后端鉴权、迁移、额度、素材、用量和监控测试 |
| `tests/` | 控制台单元测试及 SSR/敏感信息检查 |
| `user-portal/` | 客户视频与素材工具前端 |
| `deploy/volcengine/` | 火山服务器 Compose、HTTPS 网关、漫剧支付回调代理和安全验收脚本 |

## 环境要求

- Node.js `>=22.13`
- Python `>=3.11`（容器使用 Python 3.12）
- `uv`（推荐）或 Python `venv`/`pip`
- `ffprobe`（处理视频、音频上传时需要；后端 Docker 镜像已安装 FFmpeg）

## 本地启动

如需在本地启用多供应商中转，先生成独立加密主密钥：

```powershell
cd backend
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出仅写入本地 `backend/.env` 的 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY`，并设置 `MULTI_PROVIDER_ENABLED=true`。不要提交该密钥；数据库备份不包含它，生产环境必须另行备份。

### 1. 后端

```powershell
cd backend
Copy-Item .env.example .env
uv sync --extra test
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

至少根据使用范围配置：

```dotenv
VOLCENGINE_ACCESS_KEY=xxx
VOLCENGINE_SECRET_KEY=xxx
SEEDANCE_ARK_API_KEY=xxx
TOS_BUCKET=xxx
TOS_PUBLIC_BASE_URL=https://assets.example.com
DATABASE_PATH=./data/avatar_proxy.db
ADMIN_COOKIE_SECURE=false
CORS_ORIGINS=http://localhost:3001,http://localhost:3002
ENABLE_API_DOCS=false
```

本地 HTTP 环境使用 `ADMIN_COOKIE_SECURE=false`；生产 HTTPS 必须设为 `true`。完整配置和说明见 [backend/.env.example](backend/.env.example)。

首次初始化唯一超级管理员：

```powershell
uv run python -m app.admin_cli create --username admin --display-name "系统管理员"
```

命令输出的高强度初始密码仅展示一次。首次登录必须修改密码并绑定 TOTP。

应急命令：

```powershell
uv run python -m app.admin_cli reset-password --username admin
uv run python -m app.admin_cli reset-totp --username admin
uv run python -m app.admin_cli generate-totp-key
```

### 2. 内部管理控制台

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev -- --host 127.0.0.1 --port 3001
```

打开 `http://localhost:3001`。Vite 会把相对路径 `/api/*` 代理到 `CONSOLE_API_PROXY_TARGET`，默认是 `http://127.0.0.1:8000`。

`NEXT_PUBLIC_API_BASE_URL` 只供业务 API 调试与示例使用。管理员认证始终访问同源 `/api/internal/*`，不能改成跨域管理请求。

### 3. 客户工具前端

```powershell
cd user-portal
Copy-Item .env.example .env.local
npm install
npm run dev
```

默认地址为 `http://localhost:3002`。客户工具只接受 `vap_live_...` 业务 Key，不接受管理员 Cookie 或旧管理令牌。

## SMTP 磁盘告警配置

以下变量只配置在 `backend/.env` 或生产服务端 Secret 中：

```dotenv
SYSTEM_MONITOR_ENABLED=true
SYSTEM_MONITOR_PATH=
SYSTEM_MONITOR_SAMPLE_INTERVAL_SECONDS=60
SYSTEM_MONITOR_PERSIST_INTERVAL_SECONDS=300
SYSTEM_MONITOR_RETENTION_DAYS=30

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=monitor@example.com
SMTP_PASSWORD=邮箱授权码
SMTP_FROM_EMAIL=monitor@example.com
ALERT_EMAIL_RECIPIENTS=ops@example.com,owner@example.com
SMTP_SECURITY=ssl
SMTP_TIMEOUT_SECONDS=10
```

`SMTP_SECURITY` 支持 `ssl`（通常端口 465）和 `starttls`（通常端口 587）。收件人可使用逗号或分号分隔。不要把真实邮箱授权码写入 `.env.example`、README、Git、日志或截图。

## 测试与质量检查

根目录完整检查：

```powershell
npm run test:all
```

分项执行：

```powershell
# 控制台单元测试、SSR 与敏感信息检查
npm test
npm run lint
npm run build

# 后端测试、分支覆盖率且总覆盖率不低于 90%
cd backend
uv run --extra test pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90

# 客户工具前端
cd user-portal
npm test
```

自动测试必须使用临时 SQLite、模拟 TOS/火山请求和模拟 SMTP，不应调用真实火山服务、真实 Bucket 或真实邮箱。

## 部署

生产部署、HTTPS、同源代理、持久卷、备份和恢复步骤见 [backend/DEPLOYMENT.md](backend/DEPLOYMENT.md)。

当前正式业务地址为 `https://api.richbest.cn`：

- 客户程序直接调用该域名下的 `/api/*`；
- 管理控制台通过同一域名的 `/api/internal/*` 使用同源 Cookie；
- `/health` 用于健康检查；
- `POST /minidrama/payments/callbacks/wechat` 透明转发微信支付通知到 LocalMiniDrama；
- 生产环境应保持 `ENABLE_API_DOCS=false`。

支付回调上游只通过服务端部署变量配置：

```dotenv
PAYMENT_ORIGIN=host.docker.internal:10588
PAYMENT_ORIGIN_HOST=drama.richbest.cn
```

这两个变量不是浏览器配置，也不能包含微信商户密钥。LocalMiniDrama 必须自行完成验签、解密和幂等；如果其回调路由仍要求登录，网关能够转发请求，但真实微信通知仍会被上游拒绝。

部署前必须备份并校验 SQLite、确认持久卷和 `admin_totp.key`/`ADMIN_TOTP_ENCRYPTION_KEY`，再运行完整测试。除非收到明确部署指令，否则只在本地修改和验证。

## 相关文档

- [客户 API 接入文档](backend/CLIENT_API.md)
- [多供应商模型中转实施与安全边界](backend/MULTI_PROVIDER_RELAY_PLAN.md)
- [后端生产部署说明](backend/DEPLOYMENT.md)
- [额度与素材账本设计](backend/RISK_CONTROL_PLAN.md)
- [客户工具说明](user-portal/README.md)
- [漫剧微信支付回调代理说明](deploy/volcengine/MINIDRAMA_WECHAT_CALLBACK_PLAN.md)
- [开发代理协作约定](AGENTS.md)
