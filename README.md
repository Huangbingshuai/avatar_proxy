# Avatar Proxy

项目由三个独立部署单元组成：

```text
内部管理员浏览器
  └─ 内部控制台（当前根目录的 Vinext/React 站点）
       └─ HttpOnly 管理会话 + CSRF ──> 独立 FastAPI API 服务器

API 用户浏览器
  └─ 用户视频门户（user-portal/）
       └─ Authorization: Bearer vap_live_xxx ──> 独立 FastAPI API 服务器

API 用户自己的程序
  └─ Authorization: Bearer vap_live_xxx ──────> 独立 FastAPI API 服务器
       ├─ AK/SK ──> 火山虚拟人像素材库
       ├─ AK/SK ──> TOS 文件中转
       └─ Ark API Key ──> Seedance 视频任务
```

控制台不保存火山凭证、管理员密码或管理会话令牌，也不参与用户请求转发。用户只获得我方签发的 `vap_live_...`。

## 目录

- `app/`：内部管理控制台，管理项目、API Key，并提供视频接口调试页。
- `user-portal/`：面向用户独立部署的视频生成门户。
- `backend/`：可独立构建和部署的 Python FastAPI 公网服务。
- `backend/DEPLOYMENT.md`：API 服务器生产部署说明。
- `backend/CLIENT_API.md`：面向客户程序与批量任务的业务 API 接入文档。
- `backend/tests/`：鉴权、项目隔离、素材、TOS 和 Seedance 代理测试。

## 本地启动 API 服务器

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

必须在 `backend/.env` 中配置：

```dotenv
VOLCENGINE_ACCESS_KEY=xxx
VOLCENGINE_SECRET_KEY=xxx
SEEDANCE_ARK_API_KEY=xxx
ADMIN_COOKIE_SECURE=false
CORS_ORIGINS=http://localhost:3001,http://localhost:3002
ENABLE_API_DOCS=false
```

`VOLCENGINE_ACCESS_KEY/SECRET_KEY` 用于素材库请求签名和创建本地项目时校验火山资源项目，凭证至少需要相应素材接口权限及 `iam:GetProject` 权限；`SEEDANCE_ARK_API_KEY` 用于视频生成，二者不能互相替代。

首次使用时，在 `backend/` 中离线创建首位超级管理员。命令会生成高强度初始密码并仅显示一次，该密码不会写入日志或配置文件：

```powershell
.\.venv\Scripts\python.exe -m app.admin_cli create --username admin --display-name "系统管理员"
```

首次登录后必须立即修改初始密码。系统只保留一个由 CLI 初始化的 `super_admin`，可以管理管理员账号；控制台中新建的账号固定为普通 `admin`，可以使用项目、API Key、额度和调试等业务控制台，但不能查看或修改管理员账号。超级管理员密码遗失时，只能在服务器终端执行 `python -m app.admin_cli reset-password --username <用户名>` 恢复。

## 本地启动内部控制台

根目录创建 `.env.local`：

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

然后运行：

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 3001
```

打开 `http://localhost:3001` 后使用管理员用户名和密码登录。本地开发服务器会把相对路径 `/api/*` 同源代理到 `http://127.0.0.1:8000`；如需覆盖目标，可在启动进程中设置 `CONSOLE_API_PROXY_TARGET`。管理请求始终使用同源 `/api/internal/*`，不会把管理会话存入 `localStorage` 或 `sessionStorage`。

在“视频调试”页粘贴一枚已生成的业务 API Key，即可创建、轮询和取消 Seedance 任务，不需要进入 Swagger。`NEXT_PUBLIC_API_BASE_URL` 只用于业务 API 调试和接入示例，不承载管理员认证。

本地登录并完成首次改密后，可运行无业务数据变更的跨层冒烟测试。密码默认交互读取，也可仅在当前进程临时通过 `ADMIN_VERIFY_PASSWORD` 提供：

```powershell
python deploy/volcengine/verify_admin_auth.py --base-url http://127.0.0.1:3001 --username admin
```

该脚本只创建并撤销自己的登录会话，验证旧共享令牌被拒绝、Cookie、CSRF、两级角色边界及原业务控制台访问，不创建或修改项目、API Key 和额度。对最终 HTTPS 控制台域名验收时增加 `--expect-no-store`，同时验证网关禁止缓存管理响应。

## 本地启动用户门户

```powershell
cd user-portal
Copy-Item .env.example .env.local
npm install
npm run dev
```

默认访问 `http://localhost:3002`。用户门户只使用 `vap_live_...`，不接受管理令牌，也不包含项目和 API Key 管理功能。

## 用户视频接口

所有用户接口统一使用：

```http
Authorization: Bearer vap_live_xxx
Content-Type: application/json
```

创建任务：

```http
POST /api/video/generate
```

```json
{
  "model": "doubao-seedance-2-0-260128",
  "content": [
    {"type": "text", "text": "一只橘猫坐在窗边看雨"}
  ],
  "ratio": "16:9",
  "duration": 5,
  "generateAudio": true,
  "returnLastFrame": false
}
```

查询与取消：

```http
GET  /api/video/task/{taskId}
POST /api/video/task/{taskId}/cancel
```

参考人像素材可以使用公网图片 URL，或使用 `asset://<完整素材ID>`。例如素材 ID 为 `asset-20260811093724-drv67` 时，写成：

```json
{"type": "image_url", "image_url": {"url": "asset://asset-20260811093724-drv67"}}
```

不要写成 `asset://asset-asset-...`。

## 其他业务接口

- 素材组：`/api/asset-group/create|list|get|update|delete`
- 人像素材：`/api/asset/create|list|get|update|delete`
- 文件中转：`POST /api/asset/upload-file`
- 内部项目：`/api/internal/project/create|list`
- 内部 API Key：`/api/internal/apikey/create|list|disable|bind-project`

创建本地项目时，服务端会调用火山 IAM `GetProject` 校验 `ProjectName`。火山项目不存在、名称大小写不一致、凭证无读取权限或校验服务异常时，本地项目均不会写入。绑定成功后，项目名会由服务端注入到火山素材库请求中，用户不能在请求体中覆盖。

## 测试

```powershell
npm test
npm run lint

cd backend
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-tmp
```

官方参考：[虚拟人像素材资产库](https://docs.volcengine.com/docs/82379/2333565?lang=zh)
