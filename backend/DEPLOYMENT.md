# 公网 API 服务器部署

此目录是一个可独立部署的 FastAPI 服务，不依赖内部控制台的运行进程。

## 1. 配置

复制 `.env.example` 为 `.env`，至少填写：

- `VOLCENGINE_ACCESS_KEY`、`VOLCENGINE_SECRET_KEY`
- `SEEDANCE_ARK_API_KEY`
- `CONSOLE_ADMIN_TOKEN`
- `TOS_BUCKET`、`TOS_PUBLIC_BASE_URL`（需要文件中转时）
- `CORS_ORIGINS=https://你的控制台域名,https://你的用户门户域名`

生产环境保持 `ENABLE_API_DOCS=false`。所有火山凭证只存在此服务器的环境变量中。

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

`/api/internal/*` 需要 `X-Admin-Token`。除令牌鉴权外，生产环境还应在网关层限制为公司出口 IP 或 VPN 来源；不要把管理令牌交给用户。

## 4. 持久化与扩容

默认数据库为挂载在 `/app/data` 的 SQLite，适合单实例部署。不能让多个容器共享同一个 SQLite 文件；需要多实例高可用时，应先把 API Key、项目和日志存储迁移到 PostgreSQL 等共享数据库。

## 5. 控制台连接

内部控制台与用户门户分别构建和发布。控制台构建变量设置为：

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
```

用户门户构建变量设置为：

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

API 服务同时设置：

```dotenv
CORS_ORIGINS=https://console.example.com,https://video.example.com
```
