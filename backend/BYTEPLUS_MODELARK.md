# BytePlus ModelArk 海外渠道接入说明

更新日期：2026-10-14。本文供维护人员使用；客户 HTTP 契约见 [CLIENT_API.md](CLIENT_API.md)。本次是本地开发版本，已完成下述账号级基础调用验收，尚未部署生产环境。

## 接入范围与固定映射

供应商类型为 `byteplus_modelark`，固定区域 `ap-southeast-1`，固定 Base URL 为 `https://ark.ap-southeast.bytepluses.com/api/v3`。客户不能覆盖供应商、地址、项目或上游模型 ID。

| 对外别名 | 固定上游 ID | 客户接口 |
|---|---|---|
| `dreamina-seedance-2.5` | `dreamina-seedance-2-5-260628` | `/api/v3/contents/generations/tasks` |
| `dreamina-seedance-2.0` | `dreamina-seedance-2-0-260128` | 同上 |
| `dreamina-seedance-2.0-fast` | `dreamina-seedance-2-0-fast-260128` | 同上 |
| `dreamina-seedance-2.0-mini` | `dreamina-seedance-2-0-mini-260615` | 同上 |
| `dola-seedream-5.0-pro` | `dola-seedream-5-0-pro-260628` | `/v1/images/generations` |
| `dola-seedream-5.0-flash` | `dola-seedream-5-0-flash-260915` | 同上 |
| `dola-seedream-5.0-lite` | `seedream-5-0-lite-260128` | 同上 |

Lite 在控制台展示为 Dola 品牌，但官方模型列表仍列出 `seedream-5-0-lite-260128` 为可接受 ID，因此不凭展示名称拼接 `dola-` 上游 ID。本次只增加表中七个海外模型，不改已有国内模型。

## 控制台配置

1. 超级管理员打开“供应商渠道”，选择客户项目和“BytePlus ModelArk（海外）”。
2. 输入渠道名称及 BytePlus 亚太区域 Key，使用现有密码和 TOTP 再认证。无需重复填写海外项目名：海外资源权限取决于该 Key 自身的授权。
3. 普通管理员打开“项目模型”，选择同项目的海外渠道并启用所需模型。项目下现有有效业务 Key 立即共享权限。
4. 超级管理员在“模型价格”配置独立的全局人民币售价；普通管理员和客户分别通过只读价格页及 `/v1/pricing?model=模型别名` 查询。
5. 客户工具“模型测试”通过 `/v1/models` 自动发现已启用模型，仍使用原业务 Key 发起真实请求。

渠道 Key 复用现有 CredentialVault 加密和版本轮换。异步任务创建后固定原渠道、凭证版本与真实模型 ID；后续轮换或禁用不会把已提交任务改到其他渠道。新增供应商通过幂等 CHECK 约束迁移进入旧 SQLite，迁移不会自动创建渠道、授权模型或启用计费。

渠道“测试”返回 `manual`，提示通过实际模型请求验证，不猜测 `/models` 的探测行为或自动创建付费任务。

## 参数与素材

视频支持文生视频、首帧/首末帧以及全能参考。2.5 使用 4～30 秒，2.0 系列使用 4～15 秒，均支持 `duration=-1`；2.0 Fast/Mini 只开放 480p/720p，其余开放至 1080p。2.5 支持 MP4/MOV 和末帧返回。当前不开放海外视频的随机种子、固定镜头、离线推理、样片或草稿任务引用。

图片支持非流式生图、参考图改图；Lite 支持组图，Pro/Flash 每次单张。本阶段不开放图片流式、图层分解、透明背景或联网搜索。具体参数和边界由模型能力及 CLIENT_API 记录。

国内素材库 `asset://` ID 不能直接跨平台复用；请使用海外服务可访问的 HTTP(S) URL，或海外同一账号已授权素材。图片和音频也可按接口支持使用 Data URL。结果只透传供应商临时 URL，不自动转存；图片/视频 URL 通常有效 24 小时，海外视频任务记录通常只可查询近 7 天。

## 价格与真实用量

BytePlus 上游按美元结算；账本仍以人民币微元和字符串金额出账，因此内置价目把官方美元公示价按一次性冻结的汇率折算为人民币，不在每次请求时重新换算，也不叠加加价。

- 汇率基准：`1 USD = 6.705025 CNY`，取自 `open.er-api.com/v6/latest/USD`（2026-10-14 00:02 UTC）。换算金额保留 6 位小数（微元精度），四舍五入。
- 官方来源：<https://docs.byteplus.com/en/docs/ModelArk/model-pricing>，价目版本 `2026-10-14`，生效账期 `2026-10`。美元原价与人民币折算价同时保存在 `backend/app/official_rates.py`，便于复核。
- 后台启动时以幂等迁移 `official-byteplus-rates-2026-10-14` 写入全局价目；超级管理员仍可在控制台按账期覆盖，后续月份的修改不会被重新初始化覆盖。
- 缺失真实用量或单价保留为待计价；汇率或官方价变化需要重新确认后更新，不由后台任务自动跟随。

| 对外模型 | 计价维度 | 官方美元价 | 折算人民币价 |
|---|---|---:|---:|
| `dreamina-seedance-2.5` | 480p/720p 无视频参考 | 10.70 USD/M tokens | 71.743768 元/M tokens |
| `dreamina-seedance-2.5` | 480p/720p 含视频参考 | 6.40 USD/M tokens | 42.912160 元/M tokens |
| `dreamina-seedance-2.5` | 1080p 无视频 / 含视频参考 | 11.70 / 7.00 USD/M tokens | 78.448793 / 46.935175 元/M tokens |
| `dreamina-seedance-2.0` | 480p/720p 无视频 / 含视频参考 | 7.00 / 4.30 USD/M tokens | 46.935175 / 28.831608 元/M tokens |
| `dreamina-seedance-2.0` | 1080p 无视频 / 含视频参考 | 7.70 / 4.70 USD/M tokens | 51.628693 / 31.513618 元/M tokens |
| `dreamina-seedance-2.0-fast` | 480p/720p 无视频 / 含视频参考 | 5.60 / 3.30 USD/M tokens | 37.548140 / 22.126583 元/M tokens |
| `dreamina-seedance-2.0-mini` | 480p/720p 无视频 / 含视频参考 | 3.50 / 2.10 USD/M tokens | 23.467588 / 14.080553 元/M tokens |
| `dola-seedream-5.0-pro` | 首张之后的参考图 | 0.003 USD/张 | 0.020115 元/张 |
| `dola-seedream-5.0-pro` | 单图生成 ≤ 261 万像素 | 0.045 USD/张 | 0.301726 元/张 |
| `dola-seedream-5.0-pro` | 单图生成 > 261 万像素 | 0.09 USD/张 | 0.603452 元/张 |
| `dola-seedream-5.0-flash` | 成功输出图片 | 0.018 USD/张 | 0.120690 元/张 |
| `dola-seedream-5.0-lite` | 成功输出图片 | 0.035 USD/张 | 0.234676 元/张 |

尚未纳入计价、需要单独确认的官方档位：

- Seedance 2.0 系列官方价目表另列 4K 输出档（4.00 USD/M tokens 无视频参考、2.40 USD/M tokens 含视频参考），模型文档也把 `4k (10-bit color depth)` 列为输出规格；但内置目录当前只声明 480p/720p/1080p，需要先完成 4K 真实调用验证并放开能力后才具备计价意义，因此暂不写入价目。
- Pro 图片的图层分解档（0.0225 / 0.045 USD）当前无法与单图生成区分：中转链路拿不到该模式标记，相关输出按单图生成档计费。
- 视频价格按在线推理档（Online inference）配置；官方标注离线推理（Offline inference）暂不支持。

计量维度：

- 视频：按真实 `usage.completion_tokens` 计量，以 `分辨率:no_video` / `分辨率:video` 区分参考视频输入。每个规则单位为百万 Token。
- Pro 图片：根据响应中的真实图片尺寸区分 `output:le2610000` / `output:gt2610000`，并单独记录 `input:after_first`。响应无尺寸时仅接受明确的请求 `宽x高` 作为维度，无法确定时待计价。
- Lite/Flash 图片：按成功结果数量计量；部分失败条目不会算作成功图片，响应中仍保留其错误信息。
- 未返回 Token 时保留 NULL，失败/取消任务不产生成功用量；幂等请求和重复任务查询不重复计量。

## 本地验收与真实付费测试

`backend/tests/test_byteplus_modelark.py` 使用临时 SQLite 和 MockTransport，覆盖七个固定模型、URL/鉴权/请求转换、任务归属、幂等、凭证轮换、取消、错误、参数边界、用量、计价与旧库连续升级。控制台测试覆盖海外渠道录入、CSRF 和本地存储隔离。

2026-10-14 本地验证结果：后端全量 320 项测试通过，含分支统计的总覆盖率 90.11%；其中海外渠道专项 42 项全部通过。控制台 39 项单测、SSR、TypeScript 和生产构建通过，lint 无错误（保留 2 条既有图片标签警告）。客户工具 lint、TypeScript 和 Vite 构建通过。账单测试隔离内置历史费率，避免随月份变化发生价格继承或唯一键冲突。

2026-10-14 北京时间 18:39～18:46，经用户授权，使用 `test_hb` 项目已有业务 Key（名称 `test_2`）向本地 `http://127.0.0.1:8000` 客户接口执行真实付费测试。凭证由已配置的海外渠道读取；没有绕过中转站直连供应商，没有修改项目授权或生成新 Key。七个写请求各发送一次，使用独立幂等键，不自动重试。

| 对外模型 | 测试参数 / 实际输出 | 最终结果 | 上游实际输出 Token |
|---|---|---|---:|
| `dola-seedream-5.0-pro` | 单图，1K / 1024×1024 | 成功，图片可访问 | 4096 |
| `dola-seedream-5.0-flash` | 单图，1K / 1024×1024 | 成功，图片可访问 | 4096 |
| `dola-seedream-5.0-lite` | 单图，2K / 2048×2048 | 成功，图片可访问 | 16384 |
| `dreamina-seedance-2.5` | 文生视频，4 秒，480p，16:9，无音频 | 成功，视频可访问 | 38830 |
| `dreamina-seedance-2.0` | 同上 | 成功，视频可访问 | 40594 |
| `dreamina-seedance-2.0-fast` | 同上 | 成功，视频可访问 | 40594 |
| `dreamina-seedance-2.0-mini` | 同上 | 成功，视频可访问 | 40594 |

七个创建请求均返回 HTTP 200，视频均持续查询到 `succeeded`，不是仅验证任务提交。对七个结果 URL 分别执行 1 KiB 范围读取，均返回 HTTP 206 和对应的 `image/jpeg` 或 `video/mp4`；未下载完整媒体。Seedance 2.5 本轮约 6 分 39 秒完成，其余视频约 1～2 分钟完成，该耗时只是本轮观测值，不作为时延承诺。

数据库恰好有七条对应的成功用量记录；视频成功后再次查询，没有重复计量。请求日志保存七次创建的完整业务参数及脱敏返回，视频查询的最终结果也已记录；未保存 Authorization 密钥。上游未返回输入 Token 时数据库保留 NULL，不补零。用量合计输出/总 Token 为 185188（不同模态计价口径不同，不能直接合并折算金额）。该轮测试时海外售价尚未配置，七项用量全部为 `pending` / `rate_missing`，不按免费处理；2026-10-14 配置官方折算价目后，这七项用量在下一轮归集时会按上表价格重新计价。

本轮七项用量按已配置价目折算的账单金额：

| 对外模型 | 计量维度 | 数量 | 折后金额（无项目折扣） |
|---|---|---:|---:|
| `dola-seedream-5.0-pro` | `image` `output:le2610000` | 1 张 | 0.301726 元 |
| `dola-seedream-5.0-flash` | `image` 标准 | 1 张 | 0.120690 元 |
| `dola-seedream-5.0-lite` | `image` 标准 | 1 张 | 0.234676 元 |
| `dreamina-seedance-2.5` | `output_tokens` `480p:no_video` | 38830 | 2.785811 元 |
| `dreamina-seedance-2.0` | `output_tokens` `480p:no_video` | 40594 | 1.905286 元 |
| `dreamina-seedance-2.0-fast` | `output_tokens` `480p:no_video` | 40594 | 1.524229 元 |
| `dreamina-seedance-2.0-mini` | `output_tokens` `480p:no_video` | 40594 | 0.952643 元 |

上述金额按微元精度四舍五入，七项合计 7.825061 元（无项目折扣），实际账单以数据库微元和账单导出为准。

脱敏机器验收记录位于本地忽略目录 `.codex-run/byteplus-paid-smoke-20261014.json`，包含请求 ID、公共/上游任务 ID、实际用量及结果链接连通性，不包含业务 Key、供应商 Key 或带签名的结果 URL。真实 Key 不放入源码、日志、文档或 Git。本轮仅验证基础文生图和文生视频，不涵盖全部参考图/视频/音频组合、组图、取消或生产服务器网络连通性。测试时仅将本地后端进程的上游超时设为 120 秒，没有修改 `.env`。未连接生产服务器，不部署、不提交、不推送。

## 官方参考

- [模型列表](https://docs.byteplus.com/en/docs/modelark/model-list)
- [图片生成 API](https://docs.byteplus.com/en/docs/modelark/image-generation-api)
- [视频任务创建](https://docs.byteplus.com/en/docs/modelark/create-video-generation-task-api)
- [视频任务查询](https://docs.byteplus.com/en/docs/modelark/get-video-generation-task-api)
- [区域与资源隔离](https://docs.byteplus.com/en/docs/modelark/region-availability)
- [模型价格](https://docs.byteplus.com/en/docs/modelark/model-pricing)
