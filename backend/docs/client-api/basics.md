# 鉴权与通用约定

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

## 鉴权

除 `/health` 外，请求都必须携带星辰平台签发的业务 API Key：

```http
Authorization: Bearer vap_live_xxx
Accept: application/json
```

JSON 请求还需携带 `Content-Type: application/json`。

业务 API Key 已绑定星辰平台客户项目，服务端自动确定可用模型与素材范围。请求不需要、也不能覆盖 `projectName`、供应商、渠道、Base URL 或供应商 API Key。请只在服务端保存业务 Key，不要写入网页代码、公开仓库、日志或 URL。

## 基础接口

### 健康检查

```bash
curl "https://api.richbest.cn/health"
```

该接口无需鉴权。

### 验证 API Key

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
  "apiKeyId": "3ee92a25-4dd8-42c6-9af5-b8d74891f870"
}
```

该接口不会返回客户项目名、供应商凭证或模型渠道信息。

## 地址与示例约定

正式 API 根地址为 `https://api.richbest.cn`。本文的 curl 示例使用 Bash 语法，并复用以下环境变量：

```bash
export BASE_URL="https://api.richbest.cn"
export API_KEY="替换为管理员签发的业务Key"
```

API 路径已经包含 `/v1` 或 `/api`，拼接完整请求 URL 时不要重复添加前缀。配置兼容 OpenAI 的客户端时，模型接口 Base URL 通常填写 `https://api.richbest.cn/v1`；视频和素材接口使用完整的 `/api/...` 路径。SDK 自动重试应关闭，是否重试按[安全重试规则](errors.md#幂等与断线恢复)判断。

所有模型名称均使用 [`GET /v1/models`](models.md#查询可用模型) 返回的 `id`。同名模型的能力、价格由项目当前绑定渠道决定，不能由调用方在请求中切换。

## 响应与请求标识

- JSON 接口按 HTTP 状态和响应正文共同判断结果；异步任务提交成功不代表生成成功。
- 文本流式响应为 `text/event-stream`；语音合成成功为音频二进制，不能统一按 JSON 解析。
- 响应头 `X-Request-Id` 用于排查；`/v1/*` 错误还包含顶层 `request_id`。
- 保留未知的扩展字段兼容性：只依赖本文承诺字段，不因供应商增加字段而报错。
- 图片、视频和音频结果 URL 可能过期，不会自动登记为素材；取得结果后应及时保存。
