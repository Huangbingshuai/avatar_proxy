# 瑞池管理端计费账单 API 文档

版本：1.0
更新日期：2026-09-03
默认本地地址：`http://127.0.0.1:8000`

本文档面向内部管理控制台及受信任的运维工具，描述项目计费、模型价目和月度账单接口。这里的接口不是客户接口，不能使用 `vap_live_*` 业务 API Key 调用，也不会在客户工具前端展示金额。

## 1. 权限与鉴权

全部计费接口位于：

```text
/api/internal/billing/*
```

访问规则：

- 仅普通管理员可以访问；超级管理员只负责账号和安全管理，访问计费接口会返回 `403 super_admin_security_only`。
- 管理员先通过 `POST /api/internal/auth/login` 登录，服务端设置 `avatar_admin_session` 和 `avatar_admin_csrf` Cookie。
- `GET`、`HEAD`、`OPTIONS` 不要求 CSRF 请求头。
- `POST`、`PUT`、`DELETE` 必须同时携带 Session Cookie、CSRF Cookie 和 `X-CSRF-Token` 请求头。
- 修改价目、修改项目计费、增删调整项、确认账单和标记支付还必须在 JSON 中传入 `currentPassword`，用于当前管理员密码再认证。
- 密码仅用于当次验证，不能记录到日志、审计或客户端存储。

登录示例：

```bash
export BASE_URL="http://127.0.0.1:8000"

curl -c admin-cookies.txt "$BASE_URL/api/internal/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "billing-admin",
    "password": "<管理员密码>"
  }'
```

登录响应中的 `csrfToken` 只保存在内存中。以下写请求示例用 `<CSRF_TOKEN>` 表示该值。

## 2. 通用约定

### 2.1 时间、金额和折扣

- 账期和生效月份使用北京时间自然月，格式为 `YYYY-MM`。
- 币种固定为 `CNY`，当前金额为税前内部对账口径。
- 请求和响应金额都使用十进制字符串，例如 `"1.200000"`，不能使用浮点数处理金额。
- `null` 表示未配置单价；`"0"` 才表示明确免费。
- `discountBps` 使用基点：`10000` 为原价，`8000` 为八折，`0` 为全免。
- 已结束账期不能修改价目或项目计费规则。

### 2.2 计价指标

| `metric` | 含义 | 单位 |
|---|---|---|
| `input_tokens` | 输入 Token | 每 100 万 Token |
| `output_tokens` | 输出 Token | 每 100 万 Token |
| `image` | 成功生成图片 | 每张 |
| `video_second` | 成功生成视频时长 | 每秒，按分辨率 |

视频分辨率只允许 `480p`、`720p`、`768p`、`1080p`。

### 2.3 错误响应

业务错误统一返回：

```json
{
  "error": {
    "code": "billing_statement_locked",
    "message": "账单已锁定，不能修改"
  }
}
```

常见 HTTP 状态：

| 状态码 | 含义 |
|---|---|
| `401` | 未登录、会话失效或当前密码再认证失败 |
| `403` | CSRF 校验失败、首次改密未完成或角色无权访问 |
| `404` | 项目、模型、账单或调整项不存在 |
| `409` | 账期已关闭、账单已锁定或确认条件不满足 |
| `422` | 月份、金额、分辨率或请求字段格式错误 |

## 3. 模型价目

### 3.1 查询指定月份的全部价目

```http
GET /api/internal/billing/rates?month=2026-09
```

```bash
curl -b admin-cookies.txt \
  "$BASE_URL/api/internal/billing/rates?month=2026-09"
```

成功响应：

```json
{
  "month": "2026-09",
  "rates": [
    {
      "model": "glm-5.2",
      "displayName": "GLM 5.2",
      "provider": "volcengine_ark",
      "modality": "text",
      "month": "2026-09",
      "sourceMonths": ["2026-09"],
      "prices": {
        "inputPerMillionYuan": "1.200000",
        "outputPerMillionYuan": "4.000000"
      }
    }
  ]
}
```

`sourceMonths` 表示本月实际沿用的价格版本月份；未在本月改价时，可能来自更早月份。

### 3.2 设置文本模型价目

```http
PUT /api/internal/billing/rates/{modelAlias}
```

```bash
curl -b admin-cookies.txt -X PUT \
  "$BASE_URL/api/internal/billing/rates/glm-5.2" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <CSRF_TOKEN>" \
  -d '{
    "effectiveMonth": "2026-09",
    "prices": {
      "inputPerMillionYuan": "1.20",
      "outputPerMillionYuan": "4.00"
    },
    "currentPassword": "<当前管理员密码>"
  }'
```

### 3.3 设置图片模型价目

```bash
curl -b admin-cookies.txt -X PUT \
  "$BASE_URL/api/internal/billing/rates/doubao-seedream-5.0-pro" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <CSRF_TOKEN>" \
  -d '{
    "effectiveMonth": "2026-09",
    "prices": {
      "perImageYuan": "0.75"
    },
    "currentPassword": "<当前管理员密码>"
  }'
```

### 3.4 设置视频模型价目

```bash
curl -b admin-cookies.txt -X PUT \
  "$BASE_URL/api/internal/billing/rates/doubao-seedance-2.5" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <CSRF_TOKEN>" \
  -d '{
    "effectiveMonth": "2026-09",
    "prices": {
      "perSecondByResolution": {
        "480p": "0.10",
        "720p": "0.20",
        "768p": "0.25",
        "1080p": "0.40"
      }
    },
    "currentPassword": "<当前管理员密码>"
  }'
```

成功响应均为：

```json
{
  "rate": {
    "model": "doubao-seedance-2.5",
    "modality": "video",
    "month": "2026-09",
    "prices": {
      "perSecondByResolution": {
        "480p": "0.100000",
        "720p": "0.200000",
        "768p": "0.250000",
        "1080p": "0.400000"
      }
    }
  }
}
```

## 4. 项目计费规则

### 4.1 查询项目规则

```http
GET /api/internal/billing/projects/{projectName}?month=2026-09
```

```json
{
  "billing": {
    "projectName": "customer_project",
    "month": "2026-09",
    "enabled": false,
    "discountBps": 10000,
    "sourceMonth": null
  }
}
```

没有配置过的项目默认 `enabled: false`，不会因升级自动出账。

### 4.2 启用、停用或调整折扣

```http
PUT /api/internal/billing/projects/{projectName}
```

```bash
curl -b admin-cookies.txt -X PUT \
  "$BASE_URL/api/internal/billing/projects/customer_project" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <CSRF_TOKEN>" \
  -d '{
    "effectiveMonth": "2026-09",
    "enabled": true,
    "discountBps": 8000,
    "currentPassword": "<当前管理员密码>"
  }'
```

本月启用会从当月 1 日开始归集本系统内的真实成功用量；不会追溯更早月份。停用时将 `enabled` 设为 `false`。

## 5. 实时预估和账单列表

### 5.1 获取项目月度预估

```http
GET /api/internal/billing/preview?projectName={projectName}&month=YYYY-MM
```

打开预估时会先执行一次幂等用量归集和重新计算。

```json
{
  "terms": {
    "projectName": "customer_project",
    "month": "2026-09",
    "enabled": true,
    "discountBps": 8000,
    "sourceMonth": "2026-09"
  },
  "statement": {
    "id": "bstmt_xxx",
    "number": "RB-202609-CUSTOMER_PROJECT",
    "projectName": "customer_project",
    "month": "2026-09",
    "status": "draft",
    "currency": "CNY",
    "subtotalYuan": "100.000000",
    "discountYuan": "20.000000",
    "adjustmentYuan": "0.000000",
    "totalYuan": "80.000000",
    "pendingCount": 0,
    "generatedAt": "2026-09-01 00:00:00",
    "updatedAt": "2026-09-03 10:00:00",
    "confirmedAt": null,
    "paidAt": null,
    "paymentReference": null,
    "paymentNote": null
  }
}
```

项目未启用或该月没有账单时，`statement` 可能为 `null`。

### 5.2 查询账单列表

```http
GET /api/internal/billing/statements
```

可选查询参数：

| 参数 | 含义 |
|---|---|
| `projectName` | 按客户项目筛选 |
| `month` | 按 `YYYY-MM` 账期筛选 |
| `status` | `draft`、`confirmed` 或 `paid` |

响应：

```json
{
  "statements": [
    {
      "id": "bstmt_xxx",
      "number": "RB-202609-CUSTOMER_PROJECT",
      "projectName": "customer_project",
      "month": "2026-09",
      "status": "draft",
      "currency": "CNY",
      "totalYuan": "80.000000",
      "pendingCount": 0
    }
  ]
}
```

## 6. 账单详情与操作

### 6.1 查询账单详情

```http
GET /api/internal/billing/statements/{statementId}
```

除账单汇总字段外，详情包含：

```json
{
  "statement": {
    "id": "bstmt_xxx",
    "status": "draft",
    "lines": [
      {
        "id": "bline_xxx",
        "model": "glm-5.2",
        "metric": "input_tokens",
        "resolution": null,
        "quantity": "500000",
        "unitSize": 1000000,
        "unitPriceYuan": "1.200000",
        "listAmountYuan": "0.600000",
        "netAmountYuan": "0.480000"
      }
    ],
    "adjustments": [],
    "pending": []
  }
}
```

`pending` 按模型和原因汇总待计价用量。只要 `pendingCount` 大于 0，账单就不能确认。

### 6.2 重新归集和计算草稿

```http
POST /api/internal/billing/statements/{statementId}/recalculate
```

该操作要求 Session 和 CSRF，但不要求再次输入密码：

```bash
curl -b admin-cookies.txt -X POST \
  "$BASE_URL/api/internal/billing/statements/bstmt_xxx/recalculate" \
  -H "X-CSRF-Token: <CSRF_TOKEN>"
```

响应为 `{"statement": {...}}`。

### 6.3 添加补收或减免

```http
POST /api/internal/billing/statements/{statementId}/adjustments
```

正数表示补收，负数表示减免，金额不能为零：

```json
{
  "amountYuan": "-12.50",
  "reason": "服务异常减免",
  "currentPassword": "<当前管理员密码>"
}
```

只有 `draft` 账单可以增加或删除调整项。

### 6.4 删除调整项

```http
DELETE /api/internal/billing/statements/{statementId}/adjustments/{adjustmentId}
```

请求体：

```json
{
  "currentPassword": "<当前管理员密码>"
}
```

### 6.5 确认账单

```http
POST /api/internal/billing/statements/{statementId}/confirm
```

请求体：

```json
{
  "currentPassword": "<当前管理员密码>"
}
```

确认条件：

- 账期必须早于当前自然月；当前月只能预览。
- `pendingCount` 必须为 `0`。
- 账期内不能存在 `queued` 或 `running` 的视频/推理任务。
- 账单必须仍为 `draft`。

确认后价目、明细、折扣、调整项和总金额被冻结，不能重新计算或修改。

### 6.6 标记全额已支付

```http
POST /api/internal/billing/statements/{statementId}/mark-paid
```

```json
{
  "paidAt": "2026-10-03T08:00:00+08:00",
  "reference": "BANK-20261003-001",
  "note": "线下转账，全额到账",
  "currentPassword": "<当前管理员密码>"
}
```

`paidAt`、`reference` 和 `note` 可选；省略 `paidAt` 时使用服务器当前时间。第一阶段只支持将 `confirmed` 账单标记为全额 `paid`，不支持部分付款或撤销。

### 6.7 导出 CSV

```http
GET /api/internal/billing/statements/{statementId}/export.csv
```

```bash
curl -b admin-cookies.txt \
  "$BASE_URL/api/internal/billing/statements/bstmt_xxx/export.csv" \
  -o billing.csv
```

CSV 为 UTF-8 BOM，包含账单概要、模型明细、调整项和金额合计，可直接使用 Excel 打开。

## 7. 账单状态与自动处理

```text
实时归集成功用量
        ↓
draft（草稿，可重算、可调整）
        ↓ 确认
confirmed（已确认，金额冻结）
        ↓ 标记支付
paid（已支付）
```

- 后端每分钟异步归集一次成功用量，模型调用主链路不会因计费计算失败而中断。
- 打开预估或手动重新计算会立即补做一次归集。
- 失败、取消和未完成任务不计费。
- 缺少真实用量或价目时进入待计价，不会按 `0` 元处理。
- 重复轮询、应用重启和重复重算不会重复收费。
- 已确认账单收到迟到用量时不会被修改；迟到金额进入下一开放账期的系统调整项。
- 账单按客户项目汇总，API Key 仅保留在底层用量明细中用于核对，不单独配置价格或折扣。

## 8. 主要错误码

| 错误码 | 说明 |
|---|---|
| `admin_reauthentication_failed` | 当前管理员密码不正确 |
| `super_admin_security_only` | 超级管理员不能处理日常计费业务 |
| `project_not_found` | 客户项目不存在 |
| `billing_model_not_found` | 模型不存在或已下架 |
| `billing_month_invalid` | 月份格式无效 |
| `billing_amount_invalid` | 单价格式或范围无效 |
| `billing_adjustment_invalid` | 调整金额为零、格式无效或超出范围 |
| `billing_adjustment_reason_required` | 未填写调整原因 |
| `billing_resolution_invalid` | 视频分辨率不受支持 |
| `billing_period_closed` | 尝试修改已结束或已关闭账期 |
| `billing_statement_not_found` | 账单不存在 |
| `billing_statement_locked` | 账单已确认或已支付，不能修改 |
| `billing_current_month_open` | 尝试提前确认当前月账单 |
| `billing_usage_pending` | 仍有缺价格或缺真实用量的待计价项目 |
| `billing_tasks_active` | 账期内仍有未完成任务 |
| `billing_statement_not_confirmed` | 账单尚未确认，不能标记支付 |
| `billing_paid_at_invalid` | 支付时间不是有效 ISO 8601 时间 |

## 9. 与客户 API 的边界

- 客户继续使用 `Authorization: Bearer vap_live_*` 调用 `/api/*` 和 `/v1/*`。
- 客户 API 不接受管理员 Cookie，也不能读取价目、折扣、账单或支付信息。
- 本地账单只统计经过本系统且能够归属到项目的真实成功用量；绕过本系统直接调用供应商的消耗不在账单中。
- 已删除的旧方舟 Key 聚合查询不作为本地收费来源；视频计费只使用中转站记录的供应商真实成功用量。
- 本文档描述内部对账凭证，不代表税务发票，也不包含在线支付或余额扣费能力。
