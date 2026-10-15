# ModelTop 渠道接入与价格快照

更新日期：2026-10-15。本次仅本地开发；未提交、推送或部署。开发阶段未发起真实付费请求；用户配置渠道并明确授权后，已完成下文的最小参数付费验收。

## 配置与隔离

超级管理员在“供应商渠道”选择 ModelTop、客户项目和渠道名称，录入 ModelTop API Key，并使用现有密码和 TOTP 再认证。凭证仅加密存储，不提供任意 Base URL；固定域名 `https://modeltop.ai`。普通管理员在项目模型中选择同项目的 ModelTop 渠道并启用。不会自动替客户创建渠道、录入凭证、开启项目计费或绑定模型。

已有MaxModel、国内火山、BytePlus价格与任务不变。公开模型不加渠道前缀，目录中同名模型只保留一行；通过项目所选渠道决定适配器、能力、上游ID和价目。每个项目模型仍仅一个活动渠道。任务固定提交时的渠道/凭证版本/上游ID，切换项目渠道不会把旧任务改投新渠道。写请求不自动重试，幂等键不重复生成或计量。

## 本期型号与接口

GPT公开模型名与下表上游名相同；视频的公开版本名使用点号，例如上游 `dreamina-seedance-2-5` 对应公开 `dreamina-seedance-2.5`，`2-0-fast-filter-off`对应`2.0-fast-filter-off`。选择ModelTop渠道时自动使用该映射，不需手填ID；选择BytePlus仍使用其原有带日期上游ID。

| 上游模型名 | 协议 |
|---|---|
| `gpt-image-2` | 同步 `/v1/images/generations` |
| `gpt-image-2.5-flare` | 同上 |
| `gpt-image-2.5-sunburst` | 同上 |
| `dreamina-seedance-2-5` | 创建/查询 `/api/v3/contents/generations/tasks` |
| `dreamina-seedance-2-5-filter-off` | 同上 |
| `dreamina-seedance-2-0` | 同上 |
| `dreamina-seedance-2-0-filter-off` | 同上 |
| `dreamina-seedance-2-0-fast` | 同上 |
| `dreamina-seedance-2-0-fast-filter-off` | 同上 |
| `dreamina-seedance-2-0-mini` | 同上 |
| `dreamina-seedance-2-0-mini-filter-off` | 同上 |

市场目录共25款中确认上述11款。文档提到但市场未列出的 GPT Image 1.5 不猜测价格；`-gp` 是独立异步生图协议，不塞入同步接口。其他品牌、Seedream生图、视频超分、编辑/抹除不在本期。

视频支持文生、首帧、首末帧及多模态参考；2.5为4～30秒、其他4～15秒（均支持-1）；2.0支持4K，其余能力以CLIENT_API.md为准。当前不开放视频取消、草稿、回调、联网工具。图片支持文生图、原生Base64；参考图编辑需要multipart接口，不把JSON image透传为已实现编辑功能。当前不开放图片流式。国内或BytePlus的素材ID不能承诺在ModelTop可用。

ModelTop详情卡列出 `/v3/...`，而详细文档示例是 `/api/v3/...`；本次固定采用后者。对这两种路径的虚构任务ID进行无Key只读查询都返回401，只能证明路由存在，不能算成功推理。不能在写请求失败后自动换路径重试。渠道“测试”仅返回manual，引导另行授权真实验收。

## 价格来源与冻结汇率

- 价格只来自 [ModelTop市场](https://modeltop.ai/#/market) 的模型详情，不来自OpenAI或BytePlus原厂价格。
- 市场公开数据：`POST https://modeltop.ai/service/home/model/list`（只读列表）及 `GET /service/home/model/{id}`。GPT详情ID：75、108、100；视频：93/94、83/87、84/85、89/88。金额quota为微美元，除以1000000得到美元单价；本期各Token档位均为每百万Token。
- 汇率来源：[ExchangeRate-API开放数据](https://open.er-api.com/v6/latest/USD)，更新时间 `2026-10-15T00:02:31Z`，冻结 `1 USD = 6.706494 CNY`。采用与昨日BytePlus同类数据源，但不修改昨日6.705025快照。
- 人民币单价=美元单价×6.706494，Decimal四舍五入到六位小数（微元），不加价、不混币种、不自动每日重算。项目原有折扣继续应用。
- 价目生效账期2026-10；幂等迁移只初始化一次，不覆盖后续超管改价或冻结账单。

同名模型的ModelTop价目在数据库计价维度中增加内部 `modeltop:` 命名空间，不修改原厂/MaxModel价目或新增一套项目定价。超管价格页在同一模型下明确标注各渠道档位；客户 `/v1/pricing` 只返回当前绑定渠道的规则，并去除内部维度前缀。用量归集通过成功请求原渠道确定计价，不因项目后来改绑渠道而串价。

GPT生图（每百万Token）：

| 项目 | USD | CNY |
|---|---:|---:|
| 文本输入 | 5 | 33.532470 |
| 图片输入 | 8 | 53.651952 |
| 图片输出 | 30 | 201.194820 |
| 2.5缓存输入 | 1.25 | 8.383118 |

GPT Image 2没有单独公开缓存输入档位，保留缺价，不自行套用2.5缓存价格。生图绝非每张$30；根据上游真实 `usage.input_tokens_details`、`output_tokens_details`及缓存细分计量。混合文本/图片有缓存但未返回缓存分配时待计价，不把图片输入按低价文本计费。缺失Token细分不按图片数估算。

视频（每百万输出Token，分别为无视频输入/有视频输入；同型号的filter-off价格一致）：

| 型号 / 分辨率 | USD无视频 / 有视频 | CNY无视频 / 有视频 |
|---|---|---|
| 2.5 480p/720p | 10.70 / 6.40 | 71.759486 / 42.921562 |
| 2.5 1080p | 11.70 / 7.00 | 78.465980 / 46.945458 |
| 2.0 480p/720p | 7.00 / 4.30 | 46.945458 / 28.837924 |
| 2.0 1080p | 7.70 / 4.70 | 51.640004 / 31.520522 |
| 2.0 4k | 4.00 / 2.40 | 26.825976 / 16.095586 |
| Fast 480p/720p | 5.60 / 3.30 | 37.556366 / 22.131430 |
| Mini 480p/720p | 3.50 / 2.10 | 23.472729 / 14.083637 |

按 `usage.completion_tokens` 计量，不用估算秒价；计费分辨率优先上游实际返回值。上游字段缺失保留待计价。失败、取消或未完成任务不产生成功用量。日志、近30天保留和导出复用现有机制。

## 验收

自动测试只使用临时SQLite和MockTransport，覆盖11个固定型号、请求域名/鉴权/请求体、图片结果、任务创建查询、轮换固定旧凭证、幂等/归属/日志/用量、Token细分、价格快照和连续旧库升级。公开市场列出不等于账号必有调用权限。录入Key后须另行得到用户授权，短视频/单图逐款测试并记录最终结果，不能把“提交成功”当作“生成成功”。

接口参考：[GPT生图](https://modeltop.ai/docs/modelhub/openai/gpt-image-series.html)、[Seedance视频](https://modeltop.ai/docs/modelhub/doubao/sd-2.html)。客户完整契约：[CLIENT_API.md](CLIENT_API.md)。

2026-10-15 本地模拟验收：后端完整399项测试通过，含分支统计总覆盖率91.62%；控制台41项单测、SSR和生产构建通过；TypeScript通过；lint零错误（2条既有img提示）；客户工具lint、TypeScript和生产构建通过。共享模型改绑后新请求/价目按当前渠道走，旧任务与旧用量仍按原渠道固定；客户不需改模型名。该阶段未提交、推送、部署或真实付费验收。

已先备份本地SQLite，再连续初始化两次：完整性及外键检查通过，新增55条ModelTop计价规则；逐表核对项目、业务Key、管理员、渠道/凭证、模型绑定、任务、用量与账单历史保持不变，原有非ModelTop价格亦未改变。未自动创建ModelTop凭证或项目绑定。备份保存在本地忽略目录 `.codex-run`。

## 用户授权后的真实最小参数验收

2026-10-15，用户自行配置并启用 `test_hb` 的ModelTop渠道后，明确授权付费测试。使用该项目既有业务Key请求本地业务HTTP接口，不直接绕过中转层调用供应商；未修改绑定、账号、价目或计费条款，未部署。

| 模型 | 最终结果 | 真实用量（单次） |
|---|---|---|
| `gpt-image-2` | 成功，PNG 1024×1024 | 输入16、输出196 Token，1张 |
| `gpt-image-2.5-flare` | 同上 | 同上 |
| `gpt-image-2.5-sunburst` | 同上 | 同上 |
| `dreamina-seedance-2.0-mini` / `-filter-off` | 各自成功，MP4 4秒、480p | 各38800输出Token |
| `dreamina-seedance-2.0-fast` / `-filter-off` | 各自成功，同上 | 各38800输出Token |
| `dreamina-seedance-2.0` / `-filter-off` | 各自成功，同上 | 各38800输出Token |
| `dreamina-seedance-2.5` / `-filter-off` | 各自成功，同上 | 各38800输出Token |

共11/11终态成功。图片采用 `n=1,quality=low,size=1024x1024`；视频采用 `duration=4,resolution=480p,ratio=1:1,generate_audio=false`，没有附加参考素材。每款只创建一次上游生成任务；Mini以相同幂等键重放一次，仍返回原任务，任务及成功用量均只有一条。累计真实Token为311036；三张Base64图片通过PNG文件头/尺寸检查，八条视频结果URL以1024字节Range读取均返回206及MP4文件头。未测试图片编辑、高分辨率、音视频参考等其他能力。

按当前ModelTop人民币价目与原价折扣计算，本地金额合计14.067275元（约14.07元），不是对供应商账户实扣金额的确认；上游实际扣款以ModelTop账单为准。请求、结果、任务、成功用量保留在本地现有日志和账本中，不在文档保存Key或带签名的媒体URL。
