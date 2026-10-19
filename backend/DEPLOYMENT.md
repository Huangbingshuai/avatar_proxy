# 公网 API 服务器部署

此目录是一个可独立部署的 FastAPI 服务，不依赖内部控制台的运行进程。

## 1. 配置

复制 `.env.example` 为 `.env`，至少填写：

- `VOLCENGINE_ACCESS_KEY`、`VOLCENGINE_SECRET_KEY`
- `TOS_BUCKET`、`TOS_PUBLIC_BASE_URL`（需要文件中转时）
- `ADMIN_COOKIE_SECURE=true`
- `CORS_ORIGINS=https://你的用户门户域名`

多供应商模型中转默认关闭。设置 `MULTI_PROVIDER_ENABLED=true` 后，如果没有通过部署 Secret 提供 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY`，服务会在 SQLite 同目录自动生成 `provider_credentials.key` 并在后续启动时自动加载。该密钥不得复用 `ADMIN_TOTP_ENCRYPTION_KEY`，不得写入仓库、镜像或日志。生产环境仍推荐使用部署 Secret；使用自动密钥文件时必须确认数据库目录位于持久卷。SQLite 备份只包含供应商凭证密文，不包含主密钥；灾备时必须分开保管并同时恢复，否则已有渠道凭证无法解密。

生产环境保持 `ENABLE_API_DOCS=false`。所有火山凭证只存在此服务器的环境变量中。管理员不再使用共享万能令牌，环境中不应继续配置 `CONSOLE_ADMIN_TOKEN`。

数据库初始化后，通过服务器终端创建首位超级管理员：

```bash
docker compose exec api-server python -m app.admin_cli create \
  --username admin --display-name "系统管理员"
```

命令生成高强度一次性初始密码并仅显示一次。首次登录必须修改密码并绑定 TOTP；恢复码只显示一次。系统只允许一个由 CLI 初始化的 `super_admin`，且该账号只能管理账号、安全告警、会话和备份，不能访问项目、API Key、额度等业务功能。后续账号由超级管理员创建并固定为普通 `admin`，日常业务必须使用普通管理员账号。

生产环境先生成并持久化 TOTP 加密主密钥：

```bash
docker compose run --rm api-server python -m app.admin_cli generate-totp-key
```

把输出保存为受保护的 `ADMIN_TOTP_ENCRYPTION_KEY`，不要写入仓库或日志。若不显式配置，程序会在 SQLite 同目录生成 `admin_totp.key`，该文件必须与数据库分别保管并一同纳入灾备。超级管理员密码遗失时执行 `reset-password`；TOTP 设备与恢复码均遗失时执行：

```bash
docker compose exec api-server python -m app.admin_cli reset-totp --username admin
```

两种恢复操作都会撤销该超级管理员的全部旧会话，下一次登录必须重新完成安全设置。

已有有效登录会话时，不需要服务器操作：在控制台“安全管理 → TOTP验证器”中输入当前密码，扫描 10 分钟有效的新二维码并输入新验证码即可完成换绑，无需旧验证器验证码。确认前旧密钥不变；确认后系统废弃旧恢复码、撤销其他会话并一次性生成新恢复码。修改密码也只需校验当前密码，成功后全部登录会话失效。无法登录且设备和恢复码均遗失时仍使用上述 CLI 应急恢复。

## 2. 启动

```bash
docker compose up -d --build
```

健康检查：

```bash
curl https://api.example.com/health
```

## 3. 对外暴露

使用 Nginx、Caddy 或云负载均衡器终止 HTTPS，再转发到容器的 `8000` 端口。用户业务接口为 `/api/asset-*`、`/api/asset-group/*`、`/v1/*` 和 Seedance 的 `/api/v3/contents/generations/tasks*`。

`/api/internal/*` 使用服务端 Session、`HttpOnly` Cookie 和 CSRF 校验。控制台必须通过 HTTPS 提供，并把 `/api/internal/*` 同源反向代理到 API 容器；当前火山部署由 `https://api.richbest.cn/` 同时提供控制台页面和客户 `/api/*`，管理 Cookie 仅作用于 `/api/internal`。

仓库内的火山部署配置遵循以下边界：

- `edge` 是控制台的同源代理，并对所有管理响应强制 `Cache-Control: no-store`；
- `api.richbest.cn` 的 `/api/internal/*` 仅接受管理员 Session 和 CSRF，响应强制禁止缓存；
- IP 地址只记录到登录、会话和审计信息，不用于登录限制、白名单或账号权限判断；
- Cookie 的 `Secure` 属性在生产必须开启。本地纯 HTTP 验收时才临时设置 `ADMIN_COOKIE_SECURE=false`。

## 4. 持久化与扩容

默认数据库为挂载在 `/app/data` 的 SQLite，适合单实例部署。不能让多个容器共享同一个 SQLite 文件；需要多实例高可用时，应先把 API Key、项目和日志存储迁移到 PostgreSQL 等共享数据库。

业务接口会按可识别的业务 API Key 写入脱敏调用明细。完整 JSON 请求与 JSON/SSE 返回文本固定滚动保留近 30 天，过期明细清理后累计请求和累计异常计数仍保留；控制台可按已选 Key 流式导出保留窗口内的 CSV。日志不保存鉴权头、完整 Key、供应商凭证、Cookie、签名、幂等键原文、文件正文、Data URI、Base64 或媒体二进制，这些内容仅记录脱敏标记或体积元数据。上线前应根据实际请求量评估 SQLite 持久卷增长，并将数据库备份和日志导出文件视为包含客户业务内容的敏感数据。

默认每 24 小时通过 SQLite 在线备份 API 生成一份一致性数据库快照和一份管理员审计 JSONL，并在落盘前执行 `PRAGMA integrity_check`，保留最近 30 组。使用 `ADMIN_BACKUP_INTERVAL_SECONDS`、`ADMIN_BACKUP_RETENTION` 和 `ADMIN_BACKUP_DIRECTORY` 调整策略。备份目录必须位于持久卷，并同步到独立磁盘或对象存储；同机备份不能替代异地灾备。控制台中的“立即备份”同样要求超级管理员再次输入当前密码。

恢复演练至少验证：数据库快照完整性、审计 JSONL 可读、显式 `ADMIN_TOTP_ENCRYPTION_KEY` 或 `admin_totp.key` 可用，以及超级管理员能够用 TOTP 登录。不要只恢复数据库而遗漏 TOTP 加密主密钥。

控制台支持恢复服务器自动生成的数据库快照，但不支持上传外部数据库。操作路径为“安全管理 → SQLite 与审计备份”：先校验目标备份，再输入当前超级管理员密码、新一组 TOTP 和确认短语。服务会进入维护状态并排空在途请求，先生成当前数据库回滚快照，再使用 SQLite Backup API 覆盖并执行迁移、`PRAGMA integrity_check` 和 TOTP 密钥解密校验；失败时自动恢复回滚快照。成功或失败均写入恢复记录、审计和 Critical 安全告警，成功后撤销全部管理员 Session。

该在线恢复流程仅保证单进程、单实例部署。多实例环境必须在负载均衡层停止流量并确保所有实例停写后再恢复。备份文件和 `admin_totp.key` 必须来自同一套环境；恢复会同时恢复项目、API Key、管理员账号与密码等全库状态，恢复后要使用备份时间点有效的凭证登录。

## 5. 控制台连接

内部控制台与用户门户分别构建和发布。控制台构建变量仍可设置为客户业务 API 的公开地址：

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
```

该变量仅供视频调试与接入示例使用。管理员登录和管理请求固定访问同源 `/api/internal/*`，由控制台网关转发。

用户门户构建变量设置为：

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

API 服务同时设置：

```dotenv
CORS_ORIGINS=https://video.example.com
```

同源控制台请求不依赖 CORS。只有确实跨域访问业务 API 的浏览器前端需要加入 `CORS_ORIGINS`。

## 6. 数据库升级和回滚准备

升级前停止写入并备份 SQLite 文件，随后执行完整性检查：

```bash
cp /opt/avatar-proxy/data/avatar_proxy.db \
  /opt/avatar-proxy/backups/avatar_proxy-before-admin-auth.db
sqlite3 /opt/avatar-proxy/backups/avatar_proxy-before-admin-auth.db 'PRAGMA integrity_check;'
```

应用启动会幂等创建管理员账号、TOTP、恢复码、会话、安全告警、备份状态和审计所需表，不会自动生成管理员，也不会把旧共享令牌转换为账号。创建首位 `super_admin`，完成首次改密与 TOTP 绑定，再由它创建普通管理员；使用普通管理员验证原有项目/API Key 数据后，再移除旧环境变量。此次本地验收阶段不执行线上升级。

启动时还会幂等写入内置官方价目，各由一条 `app_migrations` 记录控制，只执行一次：

- `official-volcengine-rates-2026-09-04`：国内火山官方价目，生效账期 `2026-09`。
- `official-byteplus-rates-2026-10-14`：海外 BytePlus 官方美元公示价按冻结汇率 `1 USD = 6.705025 CNY` 折算后写入，生效账期 `2026-10`，不叠加加价。
- `official-modeltop-rates-2026-10-15`：ModelTop市场美元公示价按冻结汇率 `1 USD = 6.706494 CNY` 折算，生效账期 `2026-10`，55条规则使用 `modeltop:` 计价维度隔离，保留已有原厂与其他渠道价格。

ModelTop升级会幂等重建 `provider_channels` 的供应商CHECK约束，保留渠道及其凭证、绑定和任务外键；新增6条不重复模型目录行，不创建任何项目渠道或模型绑定。升级前必须保存一致性SQLite备份、独立加密密钥和原镜像，并在隔离的数据库副本上执行迁移与外键检查。本地供应商Key、项目绑定与测试数据库不得上传生产。

价目写入只新增 `billing_model_rates` 行，不改写、不删除既有行；某个别名不在 `model_catalog` 时会被跳过而不是报错。模型目录写入在价目写入之前完成，因此同一次启动内新增的模型和对应价目都会就位。汇率与官方价是代码中的常量，调整它们需要同时提升价目版本号，否则已升级过的库不会再次写入；超级管理员仍可在控制台按账期覆盖单价。

完成 HTTPS 和同源代理配置后，从仓库根目录执行安全冒烟：

```bash
python deploy/volcengine/verify_admin_auth.py \
  --base-url https://console.example.com --username admin --expect-no-store
```

密码由终端安全提示读取。脚本只登录并退出当前会话，不改动任何业务数据。

## 7. 模型长请求与发布排空

模型接口独立于 `UPSTREAM_TIMEOUT_SECONDS`（仍用于普通查询/轮询）。新增非敏感设置：

| 配置 | 默认 | 范围/作用 |
|---|---|---|
| `MODEL_CONNECT_TIMEOUT_SECONDS` | 10 | >0～60秒，建立供应商连接 |
| `MODEL_GENERATION_TIMEOUT_SECONDS` | 1800 | >0～3600秒，同步图片、非流式文本/音频及视频提交的读等待 |
| `MODEL_STREAM_IDLE_TIMEOUT_SECONDS` | 300 | >0～3600秒，流式响应连续无数据等待 |
| `MODEL_WRITE_TIMEOUT_SECONDS` | 120 | >0～300秒，向供应商发送请求数据 |
| `MODEL_IMAGE_MAX_INFLIGHT` | 16 | 1～128，单实例后台生图上限 |

HTTPX 的读取超时是两次接收数据之间的等待，不是整个请求的总秒数（[官方说明](https://www.python-httpx.org/advanced/timeouts/)）。不要简单把所有超时都关闭；保持短连接超时、较长生成读等待和有界后台并发。`httpx` 不自动重试，两个网关模型路由显式 `proxy_next_upstream off`。

HTTPS模板和8080入口的 `/v1/*` 及视频创建读等待为3660秒，超过允许的最大后端读等待。生图精确匹配路由额外设置 `proxy_ignore_client_abort on`；支付回调、管理员会话、健康检查和素材接口的超时与安全配置保持不变。客户的SDK、外层CDN/负载均衡也必须匹配，否则仍会先断线。

发布API前停止接收新生成请求，等当前请求与后台生图排空，再替换进程；不能把前端断线当作上游取消。正常客户端断开不会取消已提交生图；服务退出则中止后台等待并标记结果未知。单实例启动时幂等标记遗留生图、写入未知用量，但绝不重新提交。恢复后应凭任务和供应商记录人工核对，不能清空幂等记录再试；未知用量不应确认为免费账单。

本地回归仅使用临时SQLite、MockTransport和网关配置检查，不需要真实供应商调用，也不会产生生成费用。
