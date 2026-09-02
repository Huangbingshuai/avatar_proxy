# AGENTS.md

本文件适用于仓库根目录及全部子目录，供在本项目中工作的开发代理使用。

## 1. 项目目标与边界

本项目是 ToB 火山引擎素材与 Seedance 接入系统，包含三个独立运行单元：

- 根目录 `app/`：内部管理控制台（Vinext、React、TypeScript）。
- `backend/`：FastAPI、SQLite、火山素材/TOS/Seedance 代理和后台维护任务。
- `user-portal/`：客户工具前端（Vite、React、TypeScript）。

生产部署还包含 `deploy/volcengine/` 下的 HTTPS 网关。网关同时承载控制台、业务 API 和漫剧微信支付回调的 TLS 终止，但支付业务不属于本系统后端。

必须保持以下边界：

- 管理端使用同源 `/api/internal/*`、HttpOnly Session Cookie 和 CSRF。
- 客户接口使用 `Authorization: Bearer vap_live_*`，不得接受管理员 Cookie 代替业务 Key。
- `NEXT_PUBLIC_API_BASE_URL` 只用于业务接口调试，不能用于管理员认证。
- 火山 AK/SK、Ark Key、SMTP 授权码、管理员密码、Session、CSRF 和 TOTP 原文不得进入前端、数据库、日志、测试快照或 Git。
- 超级管理员只做账号与安全管理；普通管理员负责项目、Key、额度和日常业务。
- 不要恢复旧 `X-Admin-Token`、`CONSOLE_ADMIN_TOKEN` 或共享万能令牌流程。
- `/minidrama/payments/callbacks/wechat` 仅透明代理到 LocalMiniDrama；本系统不得验签、解密、修改订单或保存支付敏感数据。

## 2. 开始修改前

1. 运行 `git status --short`，识别并保留用户已有改动。
2. 阅读与任务直接相关的实现和测试；优先使用代码知识图谱定位符号与调用关系。
3. 检查更具体目录下是否存在额外 `AGENTS.md`；更深层文件优先。
4. 不读取、打印或提交真实 `.env`；配置项以 `.env.example` 为准。
5. 修改 API 契约时同步检查 `backend/CLIENT_API.md`、README 和两个前端调用方。

工作树可能包含用户的未提交内容。不要用 `git reset --hard`、`git checkout --`、清理整个目录或其他可能覆盖用户工作的命令。

## 3. 代码结构

### 控制台

- `app/page.tsx`：主要业务控制台、项目和 Key 管理入口。
- `app/admin-panel.tsx`：超级管理员、安全、备份、TOTP 和磁盘监控界面。
- `app/admin-api.ts`：管理 Session/CSRF 请求封装。
- `app/globals.css`：控制台样式。
- `tests/console.test.tsx`：控制台交互与认证回归。
- `tests/rendered-html.test.mjs`：SSR 与敏感信息泄漏检查。

### 后端

- `backend/app/main.py`：应用工厂、中间件、路由和后台任务生命周期。
- `backend/app/config.py`：Pydantic 环境配置；新增 Secret 必须使用 `SecretStr` 或等效保护。
- `backend/app/database.py`：SQLite schema 和幂等迁移。
- `backend/app/admin_auth.py`：密码、Session、CSRF、TOTP、角色、再认证和审计。
- `backend/app/routers/admin.py`：超级管理员安全管理接口。
- `backend/app/routers/internal.py`：项目、API Key、额度等普通管理接口。
- `backend/app/routers/assets.py`：素材组、素材和上传接口。
- `backend/app/routers/video.py`：Seedance 任务、历史和用量接口。
- `backend/app/quota.py`：项目/Key 额度与原子预占。
- `backend/app/storage.py`：TOS 上传、删除和失败清理。
- `backend/app/backup.py`：SQLite 与审计备份、校验、恢复。
- `backend/app/system_monitor.py`：磁盘采样、告警状态机、SMTP 队列和重试。

### 客户工具

- `user-portal/src/api.ts`：业务 API 客户端和响应类型。
- `user-portal/src/`：客户视频、素材和用量界面。
- `user-portal/README.md`：独立启动和构建说明。

### 生产网关

- `deploy/volcengine/compose.yaml`：API、控制台、客户工具和 HTTPS 网关编排。
- `deploy/volcengine/api-nginx.conf.template`：同源 API、控制台及漫剧微信支付回调代理。
- `deploy/volcengine/MINIDRAMA_WECHAT_CALLBACK_PLAN.md`：回调路径、上游契约、验证与回滚说明。

## 4. 实现约束

### 管理员认证

- 管理密码长度、安全哈希、锁定、Session 空闲/绝对过期规则不得被弱化。
- 所有已认证写操作必须通过 CSRF 校验；敏感超级管理员操作还必须再次验证当前密码。
- TOTP 换绑确认前旧验证器保持有效；确认后旧密钥、旧恢复码及其他会话失效。
- 禁用、改密、重置密码和删除账号时必须处理 Session 撤销及审计。
- 普通管理员不能访问超级管理员的账号、安全、备份和磁盘监控接口。
- 错误响应不要泄漏“账号存在但已禁用”等可枚举信息。

### 项目、Key 与额度

- 项目名必须由服务端校验并注入上游请求，客户请求体不能覆盖 `projectName`。
- 删除仍含 API Key 的项目必须被拒绝。
- 项目额度和 Key 子额度为空时表示不限额；迁移和新建默认值不得影响现有客户。
- 实际额度取项目和 Key 中更严格的一项，Key 不能突破项目共享上限。
- 写操作预占必须原子化；失败回滚，成功提交，禁止负数、超卖和残留预占。
- 删除操作不能因素材总量或存储总量上限而被阻止。

### 素材与 TOS

- 文件校验必须基于真实媒体内容，不只信任扩展名或 MIME。
- `uploadId` 必须校验项目、API Key、URL、素材类型和消费状态。
- 公网 URL 素材不计入 TOS 存储；本系统上传对象仅在 TOS 确认删除后释放存储量。
- 上游已可能创建素材但无法解析 `assetId` 时，不要自动删除 TOS 对象。
- 失败清理和删除重试必须幂等，不能重复扣减用量。

### 备份、恢复与磁盘监控

- SQLite 迁移必须幂等，旧库连续初始化不得丢失项目、Key、管理员或审计数据。
- 恢复前必须有回滚点、完整性检查和维护锁；成功恢复后撤销全部管理 Session。
- 单实例 SQLite 假设不得被描述为多实例安全。
- 磁盘采样和邮件发送必须由后端后台任务驱动，不能依赖控制台登录或页面打开。
- 磁盘告警需要去重、升级和恢复状态；SMTP 失败按队列重试，成功后不得重复发送同一事件。
- SMTP 只发送磁盘容量告警，除非需求明确改变，不要把登录等安全事件接入邮件。
- 自动测试只能使用模拟 SMTP，不发送真实邮件。

### 漫剧微信支付回调代理

- 公网入口固定为 `POST /minidrama/payments/callbacks/wechat`，其他方法必须返回 `405`。
- 回调入口不能要求管理员 Session、业务 API Key、Basic Auth 或其他交互式登录。
- 网关只做 TLS 终止和透明转发，必须保留原始请求正文、`Content-Type`、四个 `Wechatpay-*` 签名头及必要的转发头。
- 微信验签、通知解密、订单核对、幂等和到账处理全部由 LocalMiniDrama 完成；不能依赖来源 IP 判断通知真实性。
- 不记录请求正文、完整签名、OpenID、商户私钥、API v3 密钥或支付证书。
- 回调失败不得自动改投其他上游，避免重复处理支付通知；上游状态码和响应正文应原样返回。
- `api-gateway` 通过宿主机发布端口访问 LocalMiniDrama，不加入 `lens-rhyme_default` 等其他业务内部网络。
- Nginx 模板只允许替换 `PAYMENT_ORIGIN` 和 `PAYMENT_ORIGIN_HOST`，不得误替换 `$host`、`$remote_addr` 等 Nginx 变量。

## 5. 配置与 Secret

- 真实配置仅保存在被 Git 忽略的 `.env`、部署平台 Secret 或服务器环境变量中。
- 示例配置只写占位符；不得将真实域名凭证、邮箱授权码或个人密码写入示例。
- 新配置项同时更新 `backend/app/config.py`、`backend/.env.example` 和相关文档。
- 浏览器可见的环境变量必须经过安全审查；任何 Secret 都不能使用 `NEXT_PUBLIC_*` 或 `VITE_*` 暴露。
- 不要在错误对象、审计 before/after、日志或 API 响应中保存 Secret 原文。

## 6. 数据库与迁移

- Schema 变更集中在 `backend/app/database.py`，使用 `CREATE TABLE/INDEX IF NOT EXISTS`、列存在性检查或兼容回填实现幂等升级。
- 不要假定数据库是空库；必须保留旧表和业务数据。
- 新状态机或计量字段要定义唯一性、重试和崩溃恢复规则。
- 数据库写入尽量放在短事务中；并发计量使用 SQLite 原子更新，不采用“先查再写”的非原子逻辑。
- 为旧版真实表结构升级、重复初始化和失败恢复添加测试。

## 7. 前端约定

- 沿用现有 React、TypeScript 和样式体系，不引入第二套 UI 框架。
- 管理请求统一通过 `app/admin-api.ts`；不要在组件内重新实现 Cookie/CSRF 逻辑。
- `401` 清理内存中的受保护数据并回到登录态；会话失效后不自动重放写请求。
- Session、密码、TOTP、恢复码和 CSRF 不得写入 `localStorage` 或 `sessionStorage`。
- 一次性密码和恢复码只显示一次，并提供明确复制文本；关闭后不能从接口再次获取原文。
- 修改界面时同时覆盖加载、空数据、错误、禁用和权限不足状态。

## 8. 常用命令

### 根控制台

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 3001
npm run test:unit
npm test
npm run lint
npm run build
```

### 后端

```powershell
cd backend
uv sync --extra test
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
uv run --extra test pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90
```

### 客户工具

```powershell
cd user-portal
npm install
npm run dev
npm test
```

### 完整本地检查

```powershell
npm run test:all
cd user-portal
npm test
```

## 9. 测试要求

按改动风险选择测试，交付前至少覆盖受影响单元：

- 后端业务或迁移：相关 pytest + 全量后端覆盖率检查。
- 控制台：Vitest；涉及渲染、认证或环境变量时再跑 SSR 和生产构建。
- 客户工具：`npm test`（lint + TypeScript + Vite 构建）。
- 跨层认证：使用 `deploy/volcengine/verify_admin_auth.py`，不得创建或修改业务数据。
- 支付回调网关：使用模拟上游和测试证书验证路径改写、正文哈希、签名头、超时、非 POST 拒绝及状态码透传，不调用真实微信支付。

高风险路径必须有失败用例：鉴权拒绝、CSRF、角色边界、并发额度、回滚、TOS 删除失败、SMTP 失败、SQLite 旧库升级和恢复失败。

测试不得连接真实火山服务、真实 TOS、真实 SMTP 或线上服务器。使用临时 SQLite、MockTransport、模拟 TOS 和模拟 SMTP；测试结束后不得在仓库留下数据库、覆盖率、构建或临时目录。

## 10. Git 与交付

- 只暂存本任务明确修改的文件；提交前运行 `git diff --check` 和 `git diff --cached --name-only`。
- 永远不要提交 `.env`、`.env.local`、`.claude/`、数据库、备份、覆盖率、构建产物、日志或凭证。
- 不修改或提交与任务无关的用户文件。
- 不创建空提交，不强推，不擅自 push。
- 只有用户明确要求时才提交、合并、部署或连接线上服务器。
- 部署前必须先在本地通过相应测试，并单独确认备份、迁移、持久卷、环境变量和回滚路径。
- 完成后报告修改文件、测试结果、Git 状态，以及是否提交/合并/部署。

## 11. 文档同步

- 客户接口路径、请求字段、鉴权或错误码变化：更新 `backend/CLIENT_API.md`。
- 配置、启动、安全模型或运维变化：更新根 `README.md`、`backend/.env.example` 和必要时的 `backend/DEPLOYMENT.md`。
- 支付回调路径、上游或代理策略变化：同步更新 `deploy/volcengine/MINIDRAMA_WECHAT_CALLBACK_PLAN.md`，并回归 `/health`、`/api/*`、`/api/internal/*` 和控制台路由。
- 控制台或客户工具独立使用方式变化：更新对应 README。
- 设计计划文档不是运行时事实来源；代码、测试、示例配置和当前 API 文档必须保持一致。
