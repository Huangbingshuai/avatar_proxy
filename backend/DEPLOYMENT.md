# 公网 API 服务器部署

此目录是一个可独立部署的 FastAPI 服务，不依赖内部控制台的运行进程。

## 1. 配置

复制 `.env.example` 为 `.env`，至少填写：

- `VOLCENGINE_ACCESS_KEY`、`VOLCENGINE_SECRET_KEY`
- `SEEDANCE_ARK_API_KEY`
- `TOS_BUCKET`、`TOS_PUBLIC_BASE_URL`（需要文件中转时）
- `ADMIN_COOKIE_SECURE=true`
- `CORS_ORIGINS=https://你的用户门户域名`

生产环境保持 `ENABLE_API_DOCS=false`。所有火山凭证只存在此服务器的环境变量中。管理员不再使用共享万能令牌，环境中不应继续配置 `CONSOLE_ADMIN_TOKEN`。

数据库初始化后，通过服务器终端创建首位超级管理员：

```bash
docker compose exec api-server python -m app.admin_cli create \
  --username admin --display-name "系统管理员"
```

命令生成高强度一次性初始密码并仅显示一次。首次登录必须修改密码。系统只允许一个由 CLI 初始化的 `super_admin`；后续账号由该超级管理员在控制台中创建，且固定为普通 `admin`。普通管理员只能使用业务管理功能，不能管理管理员账号。超级管理员密码遗失时，在服务器终端使用 `python -m app.admin_cli reset-password --username <用户名>` 恢复。

## 2. 启动

```bash
docker compose up -d --build
```

健康检查：

```bash
curl https://api.example.com/health
```

## 3. 对外暴露

使用 Nginx、Caddy 或云负载均衡器终止 HTTPS，再转发到容器的 `8000` 端口。用户业务接口为 `/api/asset-*` 和 `/api/video/*`。

`/api/internal/*` 使用服务端 Session、`HttpOnly` Cookie 和 CSRF 校验。控制台必须通过 HTTPS 提供，并把 `/api/internal/*` 同源反向代理到 API 容器；不要让控制台跨域调用公开 API 域名上的管理接口。

仓库内的火山部署配置遵循以下边界：

- `edge` 是控制台的同源代理，并对所有管理响应强制 `Cache-Control: no-store`；
- 独立客户 API 域名拒绝 `/api/internal/*`，避免管理入口经公开 API 域名暴露；
- IP 地址只记录到登录、会话和审计信息，不用于登录限制、白名单或账号权限判断；
- Cookie 的 `Secure` 属性在生产必须开启。本地纯 HTTP 验收时才临时设置 `ADMIN_COOKIE_SECURE=false`。

## 4. 持久化与扩容

默认数据库为挂载在 `/app/data` 的 SQLite，适合单实例部署。不能让多个容器共享同一个 SQLite 文件；需要多实例高可用时，应先把 API Key、项目和日志存储迁移到 PostgreSQL 等共享数据库。

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

应用启动会幂等创建管理员账号、会话和审计所需表，不会自动生成管理员，也不会把旧共享令牌转换为账号。创建首位 `super_admin` 并验证登录、首次改密和原有项目/API Key 数据后，再移除旧环境变量。此次本地验收阶段不执行线上升级。

完成 HTTPS 和同源代理配置后，从仓库根目录执行安全冒烟：

```bash
python deploy/volcengine/verify_admin_auth.py \
  --base-url https://console.example.com --username admin --expect-no-store
```

密码由终端安全提示读取。脚本只登录并退出当前会话，不改动任何业务数据。
