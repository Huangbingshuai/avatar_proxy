# Star Proxy

Star Proxy 是一个面向 ToB 客户的多供应商 AI 模型中转与火山素材管理系统。系统用我方签发的业务 API Key 隔离客户项目，统一提供文本、图片、视频、向量和音频能力，并配套内部管理控制台、客户工具前端和独立 FastAPI 服务。

## 系统组成

```text
内部管理员
  └─ 管理控制台（根目录，Vinext + React）
       └─ 同源 /api/internal/* ──> FastAPI
            ├─ 管理员、Session、TOTP 与审计
            ├─ 项目、业务 API Key 与额度
            ├─ 逐 Key 业务调用日志与全量概览
            ├─ 项目计费、模型价目与月度账单
            ├─ SQLite 备份、校验与恢复
            └─ 磁盘监控与阈值配置

客户浏览器
  └─ user-portal/（React + Vite）
       └─ Bearer vap_live_* ─────> FastAPI

客户程序
  └─ Bearer vap_live_* ─────────> FastAPI
       ├─ AK/SK ──> 火山素材库与 IAM 项目校验
       ├─ AK/SK ──> TOS 文件中转
       └─ 项目加密供应商渠道 ──> 火山方舟与语音 / 阿里百炼 / MiniMax / MaxModel / OpenAI

微信支付平台
  └─ POST /minidrama/payments/callbacks/wechat
       └─ HTTPS 网关透明转发 ──> LocalMiniDrama
            └─ 验签、解密、订单幂等与到账处理
```

三个运行单元彼此独立：

- `app/`：内部管理控制台。
- `backend/`：FastAPI 公网业务与内部管理服务。
- `user-portal/`：客户使用业务 Key 的视频与素材工具。

控制台不会把管理员密码、Session、CSRF、火山 AK/SK 或 Ark API Key 写入浏览器持久存储。客户只获得我方签发的 `vap_live_...` 业务 Key。

## 当前功能

### 客户与业务接口

- 火山 `ProjectName` 对应的本地项目隔离；创建项目时调用 IAM `GetProject` 校验真实存在性。
- 一个项目可签发多枚业务 API Key，Key 可独立禁用并绑定子额度。
- 项目额度、Key 子额度、QPM、写并发、每日上传量、素材总量和 TOS 存储量控制；未配置额度时默认不限额，不影响旧客户。
- 图片、视频和音频上传校验、TOS 中转、素材组管理及素材生命周期账本。
- Seedance 视频任务创建、状态查询与取消；客户工具只在当前浏览器保存任务索引。
- 使用业务 Key 通过火山兼容任务接口中转 Seedance 视频生成，并按任务归属隔离查询与取消。
- 统一 `429` 限流协议、额度事件、审计与失败清理。
- 可选的模型中转：使用同一枚 `vap_live_*` 调用文本、图片、多模态向量、音频和统一异步视频接口；按项目路由到火山方舟、BytePlus ModelArk（海外）、豆包语音、阿里百炼、MiniMax、MaxModel 或 OpenAI 渠道。
- 项目复用加密供应商渠道并统一启用模型；项目下所有有效业务 Key 自动共享项目模型权限。
- 普通管理员通过独立的只读“模型价格”页面查看超级管理员配置的完整税前价目；客户可通过 `/v1/pricing` 查询当前项目可用模型的全局价和项目折扣后参考价。
- 对外文本模型包含 DeepSeek V4 Flash/Pro、GLM 5.2、Doubao Seed 2.1/2.0、Evolving、Character、2.0 Code 和 Translation；图片覆盖 Doubao Seedream 4.0、4.5、5.0、5.0 Lite、5.0 Pro，以及经 MaxModel 转发的 `gpt-image-2`；视频覆盖 6 个 Doubao Seedance 模型、阿里百炼 `wan3.0-video` 和 MiniMax `minimax-h3`；另提供 Doubao 多模态向量、TTS、ASR 和 Seed Audio。已停服、没有公开适配接口或当前渠道不可用的模型不开放新调用。模型与所选渠道在服务端固定映射到上游模型ID；管理员选择项目渠道，不手动改写模型ID。

模型中转调用方可直接使用 [模型中转接口文档](backend/MODEL_RELAY_API.md)；素材库及完整客户接口、字段和错误码以 [backend/CLIENT_API.md](backend/CLIENT_API.md) 为准。模型目录的固定映射、接入门槛和验收记录见 [火山方舟模型目录维护文档](backend/VOLCENGINE_MODEL_CATALOG.md)。

### BytePlus ModelArk 海外渠道

本地代码新增独立供应商 `byteplus_modelark`，限定接入 Dreamina Seedance 2.5、2.0、2.0 Fast、2.0 Mini，以及 Dola Seedream 5.0 Pro、Lite、Flash，共 7 个模型。国内模型和海外模型使用独立别名、凭证、渠道及价目。2026-10-14 已通过 `test_hb` 项目的业务 Key 完成七个模型的本地真实付费基础调用验收（3 张图片、4 段 4 秒/480p 视频），随后于同日部署到生产环境：重建 `api` 与控制台镜像，网关、客户门户和微信支付回调链路未重启。生产目前尚未录入 BytePlus 渠道凭证，也没有项目绑定海外模型，因此这些模型暂不可调用，价格与目录为预置状态；本节不代表所有参考素材组合均已验收。

超级管理员在“供应商渠道”选择“BytePlus ModelArk（海外）”，选择瑞池客户项目，录入 BytePlus `ap-southeast-1` 区域的 API Key，并按现有规则输入密码和 TOTP。海外项目权限由 BytePlus Key 自身控制，无需在渠道表单重复填写项目名。普通管理员再到“项目模型”选择该渠道并启用所需模型；现有业务 Key 自动获得项目模型权限。客户工具的“模型测试”页通过 `/v1/models` 自动发现这些模型。

海外渠道固定请求 `https://ark.ap-southeast.bytepluses.com/api/v3`。视频复用 `/api/v3/contents/generations/tasks`，图片复用 `/v1/images/generations`；任务及用量保留原渠道和凭证版本，日志和近 30 天导出继续覆盖这两个入口。渠道“测试”不会生成视频或图片，真实模型权限须通过实际请求验收。

海外价目按官方美元公示价折算为全局人民币售价：`1 USD = 6.705025 CNY`（2026-10-14 冻结汇率），不叠加加价，也不复用国内价格。视频以真实输出 Token、分辨率和是否含视频参考输入计量；Pro 图片根据实际输出像素档位及首张后的参考图数量计量，Lite/Flash 按成功图片数计量。缺少价格或计量维度时保留为待计价。配置、模型映射与验收说明见 [BytePlus 海外渠道接入说明](backend/BYTEPLUS_MODELARK.md)。

### ModelTop 中转渠道

新增独立供应商 `modeltop`，固定请求 `https://modeltop.ai`，复用渠道凭证加密、超级管理员密码/TOTP再认证和项目隔离。支持3个同步GPT生图型号及8个Seedance视频型号（标准/`filter-off`），模型不加渠道前缀。同一模型只展示一行，通过所选渠道决定上游ID、能力和计价；不覆盖已有绑定、价目或历史任务。

新增价目使用 **ModelTop 自身市场详情**，按2026-10-15汇率快照 `1 USD = 6.706494 CNY` 一次性折算；不是原厂价复制或每日浮动价。GPT按细分Token、视频按真实输出Token和分辨率/视频参考档位计费。缺价格或用量仍待计价。初始化幂等，不覆盖后续超管改价。

配置、价格来源与边界见 [ModelTop 接入说明](backend/MODELTOP_RELAY.md)，客户请求见 [CLIENT_API.md](backend/CLIENT_API.md)。2026-10-15 经用户授权，已通过本地 `test_hb` 业务Key完成11/11最小参数真实付费验收：3张低质量图片、8段4秒/480p无音频视频，最终结果与真实用量均已核对，本地价目计费合计14.067275元。同日已部署API与控制台；本地Key、渠道绑定和测试数据不会随代码发布到线上，生产仍需由管理员配置ModelTop渠道并为项目开通。

## 客户 API 快速接入

所有客户接口使用同一套业务 Key 鉴权：

```http
Authorization: Bearer vap_live_xxx
```

接入方应先请求 `GET /v1/models`，只使用响应中返回的模型 `id`，再按能力选择接口：

| 能力 | 接口 |
|---|---|
| 当前项目模型价格 | `GET /v1/pricing`，可用 `?model=模型名称` 过滤 |
| 文本对话 | `POST /v1/chat/completions`、`POST /v1/responses` |
| 图片生成与改图 | `POST /v1/images/generations` |
| 文本/多模态向量 | `POST /v1/embeddings`、`POST /v1/embeddings/multimodal` |
| 语音合成、录音识别、音频生成 | `/v1/audio/*` |
| 异步视频创建、查询、取消 | `/api/v3/contents/generations/tasks*` |
| 火山素材上传与素材组管理 | `/api/asset*`、`/api/asset-group*` |

对外别名是 Star Proxy 的稳定契约，真实上游模型 ID 由服务端维护。Doubao 产品统一使用 `doubao-` 前缀，例如 `doubao-seedream-5.0` 和 `doubao-seedance-2.0`；旧 `seedream-*`、`seedance-*` 短别名不再兼容。图片和视频创建建议携带 `Idempotency-Key`，避免调用方超时重试造成重复任务与重复费用。

### 管理员安全

- 系统只允许通过 CLI 初始化一个 `super_admin`；控制台创建的账号固定为普通 `admin`。
- 普通管理员负责项目、业务 API Key、额度、项目计费和日常业务；超级管理员负责账号安全、供应商凭证与全局模型价目。
- 密码使用 Argon2id 哈希；管理登录使用 HttpOnly Session Cookie 和 CSRF 双重校验。
- 超级管理员强制绑定 TOTP，并获得仅展示一次的一组恢复码。
- 超级管理员可在控制台验证当前密码和旧 TOTP 后自助更换验证器。
- 删除、启停管理员、重置密码、备份、恢复和监控阈值修改等敏感操作要求再次输入超级管理员密码。
- 禁用账号、修改或重置密码、TOTP 换绑后，相关旧 Session 会立即失效。
- 管理员操作、登录和安全事件写入审计；旧 `X-Admin-Token`/共享控制台令牌不再具备权限。
- 超级管理员负责创建、测试、轮换、禁用和删除供应商渠道；这些凭证操作需要密码与 TOTP 再认证。
- 普通管理员负责项目模型绑定以及中转用量和任务查询，不能读取供应商凭证原文。

### 业务调用日志与全量概览

- 控制台概览按数据库现有全部历史统计累计请求、累计异常、素材、上传量、成功模型调用次数和供应商实际返回的 Token 总量，不再只展示 24 小时或当日窗口。
- 每个能够识别到业务 API Key 的 `/api/*`、`/v1/*` 请求写入一条调用日志，包含 Key 名称与掩码、项目、HTTP 方法、接口模板、模型别名、状态码、成功状态、耗时、返回字节数、请求 ID、来源 IP 和 User-Agent。
- 普通管理员可在“调用日志”中先选择项目、再选择具体业务 Key；选中后立即加载并每 5 秒自动刷新，可展开查看完整文本请求参数与完整 JSON/SSE 返回结果。管理接口为 `GET /api/internal/call-logs`。
- 选择具体业务 Key 后，可通过 `GET /api/internal/call-logs/export.csv?apiKeyId=...` 流式导出该 Key 近 30 天的全部调用日志；CSV 使用 UTF-8 BOM，并包含接口、模型、结果、耗时、完整请求参数和完整返回结果。
- 日志不会保存 `Authorization`、完整业务 Key、供应商凭证、密码、Cookie、签名、幂等键原文、带签名的 URL 查询参数、文件正文、Data URI、Base64 或音视频/图片二进制；这些敏感或媒体字段会替换为脱敏标记或体积元数据，其余 JSON 与 SSE 文本不截断。
- 调用明细固定滚动保留近 30 天，不提供延长配置；过期明细清理后，全量请求与异常累计计数仍会保留。未知 Key 无法安全归属到客户，因此只返回鉴权错误，不进入逐 Key 日志。
- 已产生调用日志的 Key 删除时会不可逆注销并保留 Key 墓碑；存在调用历史的项目不允许物理删除，历史日志、用量和账单归属不会被级联删除。

### 多供应商模型中转

- 默认 `MULTI_PROVIDER_ENABLED=false`，迁移后没有任何默认模型绑定，素材接口行为保持不变；视频生成仅通过启用后的中转渠道提供。
- 启用时使用独立 Fernet 主密钥；未显式配置 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY` 时，系统会在 SQLite 同目录自动创建并复用 `provider_credentials.key`，SQLite 仍只保存凭证密文和尾号掩码。
- 固定使用供应商官方 HTTPS 域名，客户请求不能指定供应商、渠道、项目、Base URL 或真实上游模型 ID。
- `gpt-image-2` 使用项目级 MaxModel 渠道：超级管理员只需录入 MaxModel API Key，系统固定请求 `https://aiapi.maxmaas.com/v1/images/generations`；原有 `image2.0` 别名会迁移为 `gpt-image-2`，旧 OpenAI 绑定会被清除，防止旧凭证被发送到新上游。
- `/v1/models` 只返回当前业务 Key 所属项目已启用且渠道可用的模型；`/v1/pricing` 在相同项目隔离规则下返回税前价目并支持模型名称过滤；支持 Chat Completions、Responses、图片与多模态向量接口，以及豆包语音合成、异步录音识别和音频生成。
- Seedance 视频使用与火山方舟、漫剧调用格式一致的 `/api/v3/contents/generations/tasks` 异步任务接口；任务提交后固定渠道、凭证版本和上游模型，轮换不会破坏旧任务查询。
- 图片和视频支持 `Idempotency-Key`；相同键与相同请求复用结果，不同请求体返回 `409`。
- 只记录供应商真实返回的 Token、图片数和视频秒数，未知字段保持为空；第一阶段不做余额或金额扣费。
- 图片和视频结果 URL 由供应商提供，系统不自动转存 TOS，客户应在供应商链接有效期内下载。

### 项目计费与月度账单

- 普通管理员可以按项目逐个启用计费；存量和新建项目默认关闭，启用可选择本月补算或下月生效。
- 全局模型价目由超级管理员统一维护并按月份版本化，全部项目共用，项目只能配置是否计费和结算折扣，不能覆盖模型单价。
- 火山官方价目初始化自 2026-09-04 版价格文档：文本支持输入、缓存输入、输出及上下文阶梯价；图片支持张数与像素档位；Seedance 2.x 按上游返回的 `completion_tokens`、分辨率及是否有视频输入计价，不再把火山视频误按秒计费。
- 海外官方价目初始化自 2026-10-14 版 BytePlus 价格文档，按冻结汇率 `1 USD = 6.705025 CNY` 折算成人民币写入同一张全局价目表，账本不混用两种货币；美元原价保留在代码中便于复核。
- 计费只归集系统记录的真实成功用量。缺少真实用量、模型映射或单价时显示为“待计价”，不会按零元处理；只有明确配置零元单价才表示免费。
- 金额固定为人民币税前口径，数据库使用整数微元和十进制运算；项目折扣按基点保存，避免浮点金额误差。
- 当前自然月显示实时预估，不能提前确认；历史草稿确认后金额和明细冻结，可登记一次全额支付及凭证备注。
- 已确认账期收到迟到用量时，不改写历史账单，而是在下一开放账期生成可追溯的系统调整项。
- 账单详情支持 UTF-8 BOM CSV 导出和浏览器打印；该账单是内部对账凭证，不是法定发票，也不包含在线支付或充值余额。
- 全局价目修改要求超级管理员重新验证当前密码；项目计费、调整、确认和支付登记要求普通管理员重新验证当前密码，全部写入不含密码的审计日志。

#### Seedance 中转验证基线

截至 2026-09-03，使用业务 Key、素材库 `asset://` 图片以及最低分辨率完成了真实异步链路验证。以下别名由服务端固定映射，客户不能覆盖真实 Model ID：

| 对外别名 | 火山 Model ID | 最小验证规格 | 本地实测 |
|---|---|---:|---|
| `doubao-seedance-2.5` | `doubao-seedance-2-5-260628` | 4 秒 / 480p | 成功 |
| `doubao-seedance-2.0` | `doubao-seedance-2-0-260128` | 4 秒 / 480p | 成功 |
| `doubao-seedance-2.0-fast` | `doubao-seedance-2-0-fast-260128` | 4 秒 / 480p | 成功 |
| `doubao-seedance-2.0-mini` | `doubao-seedance-2-0-mini-260615` | 4 秒 / 480p | 成功 |
| `doubao-seedance-1.0-pro` | `doubao-seedance-1-0-pro-250528` | 2 秒 / 480p | 成功 |
| `doubao-seedance-1.0-pro-fast` | `doubao-seedance-1-0-pro-fast-251015` | 2 秒 / 480p | 成功 |

表中视频模型均已通过真实 `asset://` 素材完成生成验证。视频创建响应只返回中转站任务 ID；查询响应返回模型别名、状态及火山结果，不暴露渠道 ID、凭证版本、真实上游 Model ID 或内部请求哈希。

### 备份与恢复

- SQLite 与管理员审计 JSONL 默认每天生成一次一致性快照，默认保留最近 30 组。
- 备份落盘前执行 SQLite 完整性检查。
- 超级管理员可在控制台校验并恢复服务器生成的备份；恢复前自动建立回滚点。
- 恢复期间系统进入维护状态，成功后撤销全部管理员 Session。
- 若未显式设置 `ADMIN_TOTP_ENCRYPTION_KEY`，必须同时备份数据库目录中的 `admin_totp.key`，否则恢复后无法解密已绑定的 TOTP。

当前恢复流程面向单进程、单实例 SQLite 部署。多实例环境必须先统一停写，并迁移到共享数据库方案。

### 磁盘监控与邮件告警

- 后端启动后独立运行磁盘采样任务，不依赖管理员登录或打开控制台。
- 默认每 60 秒采样、每 5 分钟持久化一次；默认监控 `DATABASE_PATH` 所在目录。
- 默认阈值为预警 80%、严重 90%、紧急 95%、恢复线 75%，可由超级管理员在控制台修改。
- 告警升级会去重；磁盘恢复到恢复线以下后发送恢复邮件。
- 邮件失败会按 1 分钟、5 分钟、15 分钟重试，邮件队列与发送状态保存在 SQLite 中。
- SMTP 授权码只从服务端环境变量读取，不写入数据库、日志或管理接口响应。
- 磁盘邮件只用于磁盘容量告警，不与管理员登录等安全事件混用。

### HTTPS 网关与漫剧支付回调

- `api.richbest.cn:443` 统一承载控制台、业务 API、健康检查和漫剧微信支付回调入口。
- 微信通知入口固定为 `POST /minidrama/payments/callbacks/wechat`；非 POST 请求返回 `405`。
- 网关只负责 TLS 终止、路径改写和透明转发，不要求本系统管理员登录或业务 API Key。
- 原始正文、微信支付签名头和上游状态码保持不变；网关不验签、不解密、不操作订单。
- 微信验签、通知解密、订单校验、幂等和到账处理均由 LocalMiniDrama 负责。
- 网关通过宿主机发布端口访问 LocalMiniDrama，不加入 Lens 内部 Docker 网络，避免扩大数据库和 Redis 的网络暴露面。
- 回调日志不记录正文、完整签名、OpenID、商户私钥、API v3 密钥或支付证书。

完整配置、验证和回滚步骤见 [漫剧微信支付回调代理说明](deploy/volcengine/MINIDRAMA_WECHAT_CALLBACK_PLAN.md)。

## 目录说明

| 路径 | 用途 |
|---|---|
| `app/` | 管理控制台页面、管理员 API 客户端、项目/Key/额度、计费账单与安全管理 UI |
| `backend/app/routers/` | FastAPI 业务与内部管理路由 |
| `backend/app/database.py` | SQLite 表结构、兼容迁移和数据访问 |
| `backend/app/call_logging.py` | 业务请求安全脱敏、完整文本内容与逐 Key 调用日志中间件 |
| `backend/app/admin_auth.py` | 管理员、Session、CSRF、TOTP、角色和审计 |
| `backend/app/quota.py` | 项目与 Key 额度、原子预占及事件 |
| `backend/app/storage.py` | TOS 上传、素材账本清理与后台重试 |
| `backend/app/backup.py` | SQLite/审计备份、校验和恢复 |
| `backend/app/system_monitor.py` | 磁盘采样、告警状态机和 SMTP 邮件队列 |
| `backend/app/billing.py` | 真实用量归集、模型计价、月度账单、调整与 CSV 导出 |
| `backend/tests/` | 后端鉴权、迁移、额度、素材、用量、计费和监控测试 |
| `tests/` | 控制台单元测试及 SSR/敏感信息检查 |
| `user-portal/` | 客户视频与素材工具前端 |
| `deploy/volcengine/` | 火山服务器 Compose、HTTPS 网关、漫剧支付回调代理和安全验收脚本 |

## 环境要求

- Node.js `>=22.13`
- Python `>=3.11`（容器使用 Python 3.12）
- `uv`（推荐）或 Python `venv`/`pip`
- `ffprobe`（处理视频、音频上传时需要；后端 Docker 镜像已安装 FFmpeg）

## 本地启动

如需在本地启用多供应商中转，在 `backend/.env` 设置 `MULTI_PROVIDER_ENABLED=true` 即可。若 `PROVIDER_CREDENTIAL_ENCRYPTION_KEY` 留空，系统首次使用供应商凭证时会在 SQLite 同目录自动生成 `provider_credentials.key`，以后重启自动加载，无需人工复制密钥。该文件被 Git 忽略且不会进入 SQLite 备份，迁移或恢复服务时必须与数据库分别备份和恢复。生产环境也可以继续通过部署 Secret 显式提供主密钥，环境变量优先于本地密钥文件。

### 1. 后端

```powershell
cd backend
Copy-Item .env.example .env
uv sync --extra test
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

至少根据使用范围配置：

```dotenv
VOLCENGINE_ACCESS_KEY=xxx
VOLCENGINE_SECRET_KEY=xxx
TOS_BUCKET=xxx
TOS_PUBLIC_BASE_URL=https://assets.example.com
DATABASE_PATH=./data/avatar_proxy.db
ADMIN_COOKIE_SECURE=false
CORS_ORIGINS=http://localhost:3001,http://localhost:3002
ENABLE_API_DOCS=false
```

本地 HTTP 环境使用 `ADMIN_COOKIE_SECURE=false`；生产 HTTPS 必须设为 `true`。完整配置和说明见 [backend/.env.example](backend/.env.example)。

首次初始化唯一超级管理员：

```powershell
uv run python -m app.admin_cli create --username admin --display-name "系统管理员"
```

命令输出的高强度初始密码仅展示一次。首次登录必须修改密码并绑定 TOTP。

应急命令：

```powershell
uv run python -m app.admin_cli reset-password --username admin
uv run python -m app.admin_cli reset-totp --username admin
uv run python -m app.admin_cli generate-totp-key
```

### 2. 内部管理控制台

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev -- --host 127.0.0.1 --port 3001
```

打开 `http://localhost:3001`。Vite 会把相对路径 `/api/*` 代理到 `CONSOLE_API_PROXY_TARGET`，默认是 `http://127.0.0.1:8000`。

`NEXT_PUBLIC_API_BASE_URL` 只供业务 API 调试与示例使用。管理员认证始终访问同源 `/api/internal/*`，不能改成跨域管理请求。

### 3. 客户工具前端

```powershell
cd user-portal
Copy-Item .env.example .env.local
npm install
npm run dev
```

默认地址为 `http://localhost:3002`。客户工具只接受 `vap_live_...` 业务 Key，不接受管理员 Cookie 或旧管理令牌。

## SMTP 磁盘告警配置

以下变量只配置在 `backend/.env` 或生产服务端 Secret 中：

```dotenv
SYSTEM_MONITOR_ENABLED=true
SYSTEM_MONITOR_PATH=
SYSTEM_MONITOR_SAMPLE_INTERVAL_SECONDS=60
SYSTEM_MONITOR_PERSIST_INTERVAL_SECONDS=300
SYSTEM_MONITOR_RETENTION_DAYS=30

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=monitor@example.com
SMTP_PASSWORD=邮箱授权码
SMTP_FROM_EMAIL=monitor@example.com
ALERT_EMAIL_RECIPIENTS=ops@example.com,owner@example.com
SMTP_SECURITY=ssl
SMTP_TIMEOUT_SECONDS=10
```

`SMTP_SECURITY` 支持 `ssl`（通常端口 465）和 `starttls`（通常端口 587）。收件人可使用逗号或分号分隔。不要把真实邮箱授权码写入 `.env.example`、README、Git、日志或截图。

## 测试与质量检查

根目录完整检查：

```powershell
npm run test:all
```

分项执行：

```powershell
# 控制台单元测试、SSR 与敏感信息检查
npm test
npm run lint
npm run build

# 后端测试、分支覆盖率且总覆盖率不低于 90%
cd backend
uv run --extra test pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90

# 客户工具前端
cd user-portal
npm test
```

自动测试必须使用临时 SQLite、模拟 TOS/火山请求和模拟 SMTP，不应调用真实火山服务、真实 Bucket 或真实邮箱。

## 部署

生产部署、HTTPS、同源代理、持久卷、备份和恢复步骤见 [backend/DEPLOYMENT.md](backend/DEPLOYMENT.md)。

当前正式业务地址为 `https://api.richbest.cn`：

- 客户程序直接调用该域名下的 `/api/*`；
- 管理控制台通过同一域名的 `/api/internal/*` 使用同源 Cookie；
- `/health` 用于健康检查；
- `POST /minidrama/payments/callbacks/wechat` 透明转发微信支付通知到 LocalMiniDrama；
- 生产环境应保持 `ENABLE_API_DOCS=false`。

客户工具前端自 2026-10-15 起关闭，原 `http://101.96.224.33:8088/video/`、
`/video` 及其静态资源统一返回 `404`。`edge` 保留为 `:8088` 的 API 兼容代理，
通过只读挂载 `deploy/volcengine/nginx.conf` 持久化入口配置；控制台和 HTTPS API 正常提供服务。

### 当前生产发布基线（2026-10-15）

- 应用提交 `778127b`，Release 为 `/opt/avatar-proxy/releases/20261015-modeltop-relay-778127b`；后续仅补充发布记录的文档提交不改变运行镜像。
- 本次仅替换API与控制台；客户工具和HTTPS网关只做必要的Nginx配置检查与平滑reload，没有由本次发布重建，微信支付回调配置不变。
- 使用原有已验证镜像及未变化的依赖构建增量应用镜像，避免无关运行时升级。API停写窗口约50秒；已有项目、Key、管理员、渠道、凭证、模型绑定及历史记录保持不变，密钥文件和原有价格不变。
- 一致性SQLite、独立密钥/环境配置及旧镜像已保留，备份目录 `/opt/avatar-proxy/backups/20261015-modeltop-relay-before`；迁移、验证与回滚详见 [ModelTop生产部署记录](backend/MODELTOP_RELAY.md)。

### 历史生产发布记录（2026-09-11）

- 当次生产应用 Release 为 `20260911-call-log-detail-19e0215`，控制台对应代码提交 `19e0215`；2026-10-14的后续发布见 [BytePlus生产部署记录](backend/BYTEPLUS_MODELARK.md)。仅修改文档并推送 Git 不代表生产应用已经再次部署。
- 本次只重建并替换 `console`，`api`、客户工具 `edge` 与 HTTPS `api-gateway` 容器均未重启，也没有修改其他宿主机业务容器。
- 数据库和后端仍沿用 `20260911-call-log-export-5512285` 发布；其 SQLite 一致性快照、`admin_totp.key`、`provider_credentials.key`、生产环境配置及旧 API/控制台镜像均已保留，回滚备份位于 `/opt/avatar-proxy/backups/20260911-call-log-export-before-5512285`。
- 新控制台镜像已先通过隔离容器首页检查；发布后已确认公网首页和 API 健康、受保护接口继续要求鉴权、新构建包含调用详情稳定展示逻辑，且控制台日志无新增异常。
- 后续同类发布应继续采用“先备份与校验 → 在新 Release 预构建和隔离预检 → 单独替换 API → 健康后替换控制台 → reload 网关 → 回归素材、模型、价格和支付回调”的顺序。仅当前端或后端发生变化时，不应重建无关的 `edge`、`api-gateway` 或其他宿主机业务容器。

支付回调上游只通过服务端部署变量配置：

```dotenv
PAYMENT_ORIGIN=host.docker.internal:10588
PAYMENT_ORIGIN_HOST=drama.richbest.cn
```

这两个变量不是浏览器配置，也不能包含微信商户密钥。LocalMiniDrama 必须自行完成验签、解密和幂等；如果其回调路由仍要求登录，网关能够转发请求，但真实微信通知仍会被上游拒绝。

部署前必须备份并校验 SQLite、确认持久卷和 `admin_totp.key`/`ADMIN_TOTP_ENCRYPTION_KEY`，再运行完整测试。除非收到明确部署指令，否则只在本地修改和验证。

## 相关文档

- [客户 API 接入文档](backend/CLIENT_API.md)
- [模型中转接口文档](backend/MODEL_RELAY_API.md)
- [RichiDrama 对接中转站改造说明](backend/RICHIDRAMA_RELAY_ALIGNMENT.md)
- [管理端计费账单 API 文档](backend/ADMIN_BILLING_API.md)
- [多供应商模型中转实施与安全边界](backend/MULTI_PROVIDER_RELAY_PLAN.md)
- [后端生产部署说明](backend/DEPLOYMENT.md)
- [额度与素材账本设计](backend/RISK_CONTROL_PLAN.md)
- [客户工具说明](user-portal/README.md)
- [漫剧微信支付回调代理说明](deploy/volcengine/MINIDRAMA_WECHAT_CALLBACK_PLAN.md)
- [开发代理协作约定](AGENTS.md)
