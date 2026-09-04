# 多供应商模型中转实施计划

## 目标

在现有 FastAPI、SQLite、业务 API Key、项目隔离和管理员认证体系上增加多供应商模型中转能力。客户继续使用 `vap_live_*`，管理员为客户项目配置供应商渠道并统一启用模型；项目下所有有效业务 Key 自动共享项目模型权限，无需客户接触真实供应商凭证。

第一批内置对外模型别名：

- `deepseek-v4-flash`：火山方舟文本模型。
- `glm-5.2`：火山方舟文本模型。
- `doubao-seedream-5.0-pro`、`doubao-seedream-5.0-lite`、`doubao-seedream-4.5`、`doubao-seedream-4.0`：火山方舟生图、参考图改图和受能力约束的组图模型。
- `doubao-seed-2.1-pro`、`doubao-seed-2.0-pro`、`doubao-seed-2.0-lite`、`doubao-seed-2.0-mini`：火山方舟图文理解模型。
- `doubao-seedance-2.5`：火山方舟 Seedance 2.5 视频模型。
- `doubao-seedance-2.0`、`doubao-seedance-2.0-fast`、`doubao-seedance-2.0-mini`：火山方舟 Seedance 2.0 视频模型。
- `doubao-seedance-1.0-pro`、`doubao-seedance-1.0-pro-fast`：火山方舟 Seedance 1.0 Pro 视频模型。
- `wan3.0-video`：阿里百炼异步视频模型。
- `minimax-h3`：MiniMax 异步视频模型。
- `image2.0`：OpenAI 图片模型别名，固定映射到 `gpt-image-2`。

新功能默认关闭，不改变当前素材接口、`/api/video/*`、全局 Seedance Key 或已有业务 Key 的行为。

## New API 参考边界

设计参考 QuantumNous/New-API 提交 `0ed497f` 中的 Channel、Ability、Distributor、Adaptor、TaskAdaptor、模型映射和预扣/结算机制。实现采用 Python 原生重写，不复制其 Go 源码、前端或数据库代码，避免将本项目直接纳入 AGPLv3 代码派生范围。

对应关系：

| New API 概念 | 本项目实现 |
| --- | --- |
| Channel | 项目级 `provider_channels` 和版本化凭证 |
| Ability | 模型目录和项目模型绑定 |
| Distributor | 项目、模型和渠道的确定性路由器 |
| Adaptor | OpenAI、方舟、百炼、MiniMax Python 适配器 |
| TaskAdaptor | 统一异步视频任务和状态映射 |
| 预扣与结算 | 现有原子额度能力加统一用量账本 |

## 数据与安全

新增幂等 SQLite 表：供应商渠道、版本化凭证、模型目录、项目模型绑定、推理任务和推理用量。早期版本创建的 `api_key_model_permissions` 表为兼容旧 SQLite 保留，但不再参与鉴权和路由。

- 渠道属于一个项目；禁止跨项目绑定。
- 同一项目和模型第一期只有一个活动渠道，不做权重分流或自动故障转移。
- 凭证使用独立 Fernet 主密钥加密，数据库、日志、审计和接口只出现掩码。未显式配置 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY` 时，系统在 SQLite 同目录自动生成并复用受保护的 `provider_credentials.key`；生产仍可用部署 Secret 覆盖。
- 供应商渠道的创建、凭证轮换、禁用和删除仅允许超级管理员，并复用密码与 TOTP 再认证。
- 普通管理员只能绑定项目模型；项目下所有有效业务 Key 自动继承项目模型权限。
- 异步任务固定渠道及凭证版本；轮换后新任务使用新凭证，旧任务继续使用原版本。
- 渠道仍被模型引用或存在未完成任务时拒绝删除。

## 接口

客户接口使用 `Authorization: Bearer vap_live_*`：

```text
GET  /v1/models
POST /v1/chat/completions
POST /v1/responses
POST /v1/images/generations
POST /v1/videos
GET  /v1/videos/{taskId}
GET  /v1/videos/{taskId}/content
HEAD /v1/videos/{taskId}/content
```

- `/v1/models` 只返回当前业务 Key 所属项目已绑定且渠道可用的模型。
- Chat Completions 和 Responses 同时支持 JSON 与 SSE；视觉模型允许 OpenAI 兼容的 `image_url`/`input_image` 内容，非视觉模型拒绝图片输入。
- 图片接口采用 OpenAI 兼容请求响应；方舟适配器会过滤 OpenAI 专属字段，并按具体 Seedream 能力转换参考图和组图参数。
- 视频请求支持 `model`、`prompt`、`image`、`duration`、`width`、`height`、`fps`、`seed`、`n`、`response_format` 和受白名单约束的 `metadata`。
- 图片和视频写接口支持 `Idempotency-Key`，相同请求复用结果，不同请求体返回 `409`。
- 图片和视频结果透传供应商 URL，不自动转存 TOS。
- 客户不能覆盖项目、供应商、Base URL、渠道或真实上游模型 ID。

管理接口提供渠道管理、渠道测试、凭证轮换、模型目录、项目模型绑定、推理任务和用量查询。所有写操作保留现有 Session、CSRF、角色和审计规则。

## 计量与任务

- 文本记录供应商真实返回的输入、输出和总 Token。
- 图片记录真实图片数和供应商提供的 Token；未知数据保存为空，不估算为零。
- 视频任务成功后记录真实时长、分辨率和输出数量；失败任务不计成功产出。
- 任务状态统一为 `queued`、`running`、`succeeded`、`failed` 和 `canceled`。
- 轮询、重复回调或重复请求不得重复结算。
- 第一阶段只记录原始用量，不实现价格、余额、充值或金额扣费。

## 控制台

- 超级管理员安全区增加供应商渠道管理，秘密只能录入或轮换，不能取回原文。
- 普通管理员增加项目模型绑定；控制台不提供逐 Key 模型权限配置。
- 增加按项目、业务 Key、模型、供应商和时间筛选的推理用量与任务列表。
- 客户工具前端提供文本流式、识图、文生图、参考图改图和异步视频测试入口；完整业务接入仍使用 OpenAI 兼容 API。

## 兼容与开关

- `MULTI_PROVIDER_ENABLED=false` 为默认值。
- 功能开启时必须配置有效的凭证加密主密钥；未配置时新接口返回明确的服务不可用错误，旧接口照常工作。
- 现有业务 Key 自动保留素材和 `/api/video/*` 权限；只有所属项目启用模型后才能访问对应 `/v1/*` 接口。
- 真实上游模型 ID 由服务端内置目录固定维护；管理员只选择项目渠道，不接受手工模型 ID。
- 第一阶段只允许内置供应商的官方 HTTPS 地址，不提供任意 Base URL。

## 验收

- 旧 SQLite 连续升级、重复初始化、备份恢复不丢失现有数据。
- 凭证原文不进入数据库、日志、审计、接口、SSR 或测试快照。
- 项目、角色、CSRF、项目模型权限和跨项目边界全部有拒绝用例，并验证同项目多枚 Key 自动共享模型权限。
- MockTransport 覆盖 OpenAI、方舟、百炼和 MiniMax 的请求转换、同步响应、SSE、异步查询及错误映射。
- 幂等请求、任务固定渠道、凭证轮换、重复轮询和失败不结算均有回归测试。
- 现有素材、Seedance、额度、管理员认证、备份和磁盘监控测试保持通过。
- 后端分支覆盖率不低于 90%；控制台单元测试、SSR、lint 和生产构建通过。
- 自动测试不连接真实供应商、不发送真实邮件、不产生模型费用。

## 实施边界

本阶段只在本地功能分支开发和提交，不合并主分支、不 push、不部署线上。完成本地验收后等待新的明确指令。
