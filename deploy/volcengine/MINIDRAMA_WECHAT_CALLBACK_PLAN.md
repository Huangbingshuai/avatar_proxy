# 漫剧微信支付 HTTPS 回调代理实施说明

## 目标

在现有 `api.richbest.cn:443` 网关增加固定入口：

```text
POST https://api.richbest.cn/minidrama/payments/callbacks/wechat
```

网关只负责 TLS 终止和透明转发。微信验签、通知解密、订单核对、幂等处理和积分到账均由 LocalMiniDrama 负责。

## 请求链路

```text
微信支付
→ api.richbest.cn:443
→ avatar-proxy api-gateway
→ host.docker.internal:10588
→ local-minidrama:5679
→ /api/v1/payments/callbacks/wechat
```

采用宿主机已发布的 `10588` 端口，不让 `api-gateway` 加入 `lens-rhyme_default`，避免扩大其对 Lens 内部容器、数据库和 Redis 的访问范围。

## 配置契约

默认值：

```ini
PAYMENT_ORIGIN=host.docker.internal:10588
PAYMENT_ORIGIN_HOST=drama.richbest.cn
```

Nginx 官方镜像在启动时仅替换以上两个模板变量。`NGINX_ENVSUBST_FILTER` 必须保持为：

```text
^(PAYMENT_ORIGIN|PAYMENT_ORIGIN_HOST)$
```

这样不会替换 `$host`、`$remote_addr` 等 Nginx 内置变量。

`api-gateway` 通过以下 Compose 配置访问宿主机：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## 回调行为

- 仅精确匹配 `/minidrama/payments/callbacks/wechat`。
- 仅接受 `POST`，其他方法返回 `405`。
- 不要求管理员登录、Cookie、Basic Auth 或本系统 API Key。
- 请求正文最大 `1MB`，不解压、不解析、不重写。
- 保留微信支付签名请求头以及 `Content-Type`。
- 设置正确的 `Host`、`X-Forwarded-*` 和 `X-Real-IP`。
- 上游连接超时 `5s`，发送和读取超时 `30s`。
- 禁止自动切换上游，避免 POST 被重复转发。
- 上游状态码和响应正文原样返回，不把代理失败改成成功。
- 专用访问日志不记录正文、完整签名、OpenID 或支付密钥。

## 本地验证

必须验证：

1. `docker compose config` 正常渲染模板路径、环境变量和 `extra_hosts`。
2. 使用临时证书和模拟上游执行 `nginx -t`。
3. POST 外部路径被改写为上游 `/api/v1/payments/callbacks/wechat`。
4. 请求正文前后 SHA-256 一致。
5. 四个 `Wechatpay-*` 请求头、Content-Type 和转发头完整到达上游。
6. 上游 `204`、`500` 均原样返回。
7. 上游不可达时返回 `502` 或 `504`。
8. 非 POST 请求不会到达上游。
9. 日志中不出现请求正文和完整签名。
10. `/health`、`/api/*`、`/api/internal/*` 和控制台 `/` 的原配置保持不变。

公网路由可使用仓库内脚本进行无副作用验收。脚本只发送 `GET`、健康检查和
一个无签名的空 JSON，不会创建订单或修改支付状态：

```bash
python deploy/volcengine/verify_minidrama_callback.py \
  --base-url https://api.richbest.cn
```

只有脚本输出 `PASS` 才表示网关已经把无签名请求交给微信验签逻辑；
`UNAUTHORIZED`、Basic Auth HTML 或登录跳转都会使脚本失败。

## 后续线上发布

本次提交不部署线上。获得明确部署指令后：

1. 确认 `local-minidrama` 为 `healthy`，且宿主机 `http://127.0.0.1:10588/ready` 返回 `200`。
2. 备份 `/opt/avatar-proxy/current` 指向的 Release 和当前 Nginx 配置。
3. 在独立临时容器中使用真实证书执行 `nginx -t`。
4. 只重建 `api-gateway`，不重启素材后端、控制台、Lens 或漫剧容器。
5. 验证网关可访问 `host.docker.internal:10588/ready`。
6. 用无效签名请求确认回调能到达漫剧后端并被拒绝。
7. 回归检查素材 API、内部管理接口、控制台、证书和现有 HTTP 路由。
8. 由 LocalMiniDrama 维护者执行真实微信支付通知验收。

无效签名验收返回 `INVALID_SIGNATURE` 只表示请求已经绕过登录认证并进入
微信支付验签逻辑，不是有效支付通知的成功响应。如果返回 `UNAUTHORIZED`、
HTML Basic Auth 页面或登录跳转，说明请求仍被通用认证拦截，禁止开始真实支付验收。

回滚时恢复上一份 Release，并只重建 `api-gateway`。

## 边界

- 不修改本系统素材后端。
- 不修改 Lens 网络和服务。
- 不修改 LocalMiniDrama 部署脚本和支付业务代码。
- 不保存微信商户号、API v3 密钥、私钥、证书或支付公钥。
- Preview 若需接收真实通知，LocalMiniDrama 必须另行提供无需 Basic Auth 的稳定 HTTP 上游。
