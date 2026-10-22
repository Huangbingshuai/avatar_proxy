# Vega 统一渠道接入说明

本次接入依据用户提供的 Lite/Pro 接入、刊例价、常见问题及控制台测试 PDF（核对日期：2026-10-22）。本文件面向内部管理员；交付客户请使用 [客户API](CLIENT_API.md)、[HTML阅读版](CLIENT_API.html) 和 [Vega视频与素材](docs/client-api/vega.md)。

## 范围与配置

同一个 `vega` 供应商渠道支持5个视频版本、3个 `vega-image-1.0-{lite,flash,pro}` 图片模型、3个 `wand-vega-vl-1.0-{lite,flash,pro}` 多模态理解模型。视频、图片及Pro素材使用腾讯云VOD的TC3签名；VL使用同一渠道中的独立API Token。客户始终使用本站业务Key。[图片与VL客户参数](docs/client-api/vega-image-vl.md)依据本次提供的5份PDF，不与视频模型版本混用。

不需要新增Vega专用环境变量。后端现有配置需满足：

```dotenv
MULTI_PROVIDER_ENABLED=true
# 仅本地HTTP开发；生产HTTPS必须为true
ADMIN_COOKIE_SECURE=false
```

已有 `.env` 不要用样例覆盖。`DATABASE_PATH` 应继续指向原SQLite文件；供应商凭证主密钥必须沿用现有 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY`，或数据库同目录的 `provider_credentials.key`。未配置主密钥时系统在首次加密时生成并保存独立密钥文件，后续不可丢失或替换；备份数据库时需另行安全保管该文件。

1. 在腾讯云开通VOD、对应模型权限，确认子应用SubAppId及SecretId/SecretKey权限。
2. 超级管理员在“供应商渠道”选择Vega、所属项目、国内/国际站，填写SubAppId；视频/图片填成对的SecretId/SecretKey，VL填API Token，可仅配置所需能力。全部凭证加密保存在同一个渠道，经现有密码与TOTP校验后保存，不写入前端环境变量。轮换凭证时留空项保留旧值，单独补充VL Token不会清除原视频/图片的Secret，历史任务继续使用原凭证版本。
3. 视频/图片国内站固定请求 `vod.tencentcloudapi.com`，国际站固定请求 `vod.intl.tencentcloudapi.com`；VL按提供的接入PDF固定为 `https://mmu.vod-qcloud.com/v1`。VL Token在VOD控制台的AI文本API Key管理中创建，约需1分钟同步，国内/国际站凭证不能混用。不允许客户自填Base URL。
4. 普通管理员在“项目模型”绑定该项目的Vega渠道并启用所需模型。项目下有效业务Key共享项目模型权限；客户仍使用本站业务Key，不接触腾讯云凭证。
5. 如需本地上传及音视频校验，将FFmpeg和ffprobe加入服务进程PATH，或使用现有 `FFPROBE_PATH` 配置指定ffprobe位置。

## 接口与任务边界

| 能力 | 本站入口 | 说明 |
|---|---|---|
| 创建视频 | `POST /api/v3/contents/generations/tasks` | `model`为本站别名，必须提供`Idempotency-Key` |
| 查询视频 | `GET /api/v3/contents/generations/tasks/{taskId}` | 使用本站返回的任务ID，固定原渠道及凭证版本 |
| 异步图片 | `POST /v1/images/tasks`、`GET /v1/images/tasks/{taskId}` | Lite/Flash/Pro；创建必须提供幂等键，按业务Key隔离 |
| 同步兼容图片 | `POST /v1/images/generations` | 等待同一异步任务，超时返回可继续查询的taskId |
| 多模态理解 | `POST /v1/chat/completions` | JSON/SSE，Lite/Flash支持纯文本，Pro至少一种媒体；不支持Responses |
| Pro素材与活体 | `POST /v1/vega/{action}` | 仅文档列出的Action，使用业务Key；创建操作要求幂等键 |

客户不能覆盖站点、SubAppId、上游模型名称、凭证或任意Action。Vega素材按项目、业务Key及渠道隔离，不能与火山素材ID混用；素材任务不能通过视频查询入口读取。活体凭证及敏感链接在调用日志中脱敏。

不支持取消、回调或永久存储。结果链接可能过期，客户应自行及时下载保存。素材注册、活体认证及供应商存储可能另收费，不在视频自动计价范围内。

## 价格与真实用量

- 按提供的刊例价初始化全局价目，区分站点、分辨率及是否输入参考视频；国内站人民币，国际站美元按汇率快照折算人民币。此次快照为2026-10-22，`1 USD = 6.689327 CNY`，来源及时间保存在价目元数据中，不代表自动实时换汇。
- 全局价目可由超级管理员后续统一调整；新模型和渠道不会自动启用任何项目计费。
- Lite按真实输入/输出视频秒数计价，超过5张的真实输入图片另计。Pro参考视频计费秒数为 `max(实际输入秒数, 实际输出秒数 × 2/3) + 实际输出秒数`；无参考视频按真实输出秒数。
- 请求中强制开启上游VegaUsage采集。只使用成功任务实际返回的Usage；不能用请求时长代替真实时长，缺失必要用量进入待计价，不按零元结算。
- 金额使用Decimal及整数微元；归集、查询及重新计算不能重复收费。默认并发通常只有1路，供应商限流时不得换幂等键盲目重提。
- 图片按实际返回的输出张数计量，国内Lite/Flash/Pro为0.162/0.45/0.95元/张；Pro前3张输入免费，额外输入0.10元/张，须以上游确认数量为依据。国际站图片价未提供，预留可编辑维度而不编造单价；缺价或缺用量进入待计价。
- VL按真实输入、输出及缓存Token分开计价，缓存从普通输入中扣除；同时出现cached_tokens/cache_read_tokens时不相加。未完成的SSE和缺失用量不算成功结算，不按0元消账。国内/国际站价目和字段说明见客户文档；传入会话头按项目和Key做哈希隔离。

## 本地启动与验收

按 [README本地启动](../README.md#2-启动后端) 启动三个独立进程，保留已有配置和账号，不重复初始化管理员：

```powershell
# backend目录
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 仓库根目录，另开终端
npm run dev -- --host 127.0.0.1 --port 3001
# user-portal目录，另开终端
npm run dev -- --host 127.0.0.1 --port 3002
```

后端健康检查为 `http://127.0.0.1:8000/health`，控制台为 `http://127.0.0.1:3001`，客户工具为 `http://127.0.0.1:3002`。管理员请求走控制台同源代理，不能用业务Key代替管理Session。

视频阶段离线基线为后端616项测试（分支覆盖率91.74%）、控制台93项测试及文档阅读器11项测试。图片/VL阶段另补充统一渠道、凭证轮换、异步恢复、Key隔离及缓存计量回归。测试只使用临时SQLite和模拟供应商，不代表真实账号已开通或网络已端到端验证；完整校验命令为后端pytest覆盖率、控制台单测/TypeScript/lint/构建和文档生成/回放测试。

2026-10-22图片/VL收尾验证：后端全量656项通过，含分支覆盖率90.68%；最终媒体格式边界补充后独立回归38项通过。控制台94项单测、TypeScript、生产构建、SSR、文档阅读器12项及生成同步校验均通过。前端单测使用单worker避免默认并行下的5秒资源争用超时；lint无错误，保留2项既有img优化提示。Vega视频、图片和VL在控制台统一使用同一款腾讯云图标。本批仅完成本地实现与验证，推送、部署和真实收费验收需单独授权。

渠道“测试”不自动发起收费生成。真实验收须先取得用户明确付费授权，再通过本站客户接口提交一次最短时长、最低支持分辨率的视频并轮询原任务；不要通过腾讯云直连绕过本站鉴权、日志和用量采集。失败或结果未知时不要自动重试。本次本地接入未部署、未发起付费调用。
