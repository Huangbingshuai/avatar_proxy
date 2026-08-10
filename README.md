# Avatar Proxy

火山方舟私域虚拟人像素材资产库的服务端代理与管理控制台。调用方使用本系统生成的 API Key，火山引擎 AK/SK 只保留在服务端环境变量中。

## 配置

本地开发复制 `.dev.vars.example` 为 `.dev.vars`，部署时配置同名运行时变量：

```text
VOLCENGINE_ACCESS_KEY=火山引擎AK
VOLCENGINE_SECRET_KEY=火山引擎SK
CONSOLE_ADMIN_TOKEN=至少32位的随机管理令牌
```

然后运行：

```bash
npm install
npm run dev
```

打开控制台后用 `CONSOLE_ADMIN_TOKEN` 解锁，先创建项目，再生成 API Key。完整 Key 只显示一次，数据库只保存其 SHA-256 哈希。

## 鉴权

所有业务接口统一使用：

```text
Authorization: Bearer vap_live_xxx
Content-Type: application/json
```

每个 API Key 固定绑定一个火山方舟 `ProjectName`。服务端会覆盖客户端传入的项目字段，确保跨项目资源不能混用。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST / GET | `/api/v1/asset-groups` | 创建 / 查询素材组 |
| GET / PATCH / DELETE | `/api/v1/asset-groups/{id}` | 获取 / 更新 / 删除素材组 |
| POST / GET | `/api/v1/assets` | 上传 / 查询素材 |
| GET / PATCH / DELETE | `/api/v1/assets/{id}` | 获取 / 更新 / 删除素材 |

创建素材组：

```bash
curl -X POST http://localhost:3001/api/v1/asset-groups \
  -H "Authorization: Bearer vap_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"name":"campaign-hero","description":"活动角色"}'
```

上传图片素材：

```bash
curl -X POST http://localhost:3001/api/v1/assets \
  -H "Authorization: Bearer vap_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"group_id":"group-xxx","url":"https://example.com/avatar.png","asset_type":"Image","name":"角色正面照"}'
```

素材状态变为 `Active` 后，可使用 `asset://<asset_id>` 参与 Seedance 视频生成。

## 安全设计

- 上游 AK/SK 不进入数据库、不返回客户端，只从运行时 Secret 读取。
- API Key 只存哈希，完整密钥仅在创建响应中出现一次。
- 项目由 API Key 强制注入，客户端无法覆盖。
- 请求日志只保存操作、项目、状态和耗时，不保存业务请求体。
- 管理接口必须携带独立的 `X-Admin-Token`。

## 验证

```bash
npm run build
npm test
```
