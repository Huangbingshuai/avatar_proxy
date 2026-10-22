# Vega 视频与素材

[文档首页](../../CLIENT_API.md) · [模型目录](models.md) · [错误与重试](errors.md)

先联系管理员为项目开通模型。调用方只填写星辰平台业务 Key，不传腾讯云凭证、站点、SubAppId、ModelName、ModelVersion或渠道；这些由服务端绑定决定。Vega素材与火山素材是两个独立系统，不能混用素材ID。

## 视频模型

| model | 输出时长 | 分辨率（小写） | 智能时长 |
|---|---|---|---|
| `vega-1.0-lite` | 4～15秒 | 480p、768p、1080p、2k、4k | 不支持 |
| `vega-1.0-pro` | 4～15秒 | 720p、1080p、2k、4k | duration=-1 |
| `vega-1.0-pro-fast` | 4～15秒 | 720p、1080p、2k、4k | duration=-1 |
| `vega-1.0-pro-mini` | 4～15秒 | 720p、1080p、2k、4k | duration=-1 |
| `vega-1.5-pro` | 4～30秒 | 720p、1080p、2k、4k | duration=-1 |

使用 `POST /api/v3/contents/generations/tasks` 创建，`GET /api/v3/contents/generations/tasks/{taskId}` 查询。请求结构与本站其他视频一致，但能力与附加字段不同。每个模型的完整示例见[独立模型参考](model-reference.md)。Vega不支持取消任务、回调、任意上游Action透传或永久存储；任务固定使用提交时的渠道与密钥版本。

## Vega专用参数

以下选项放在顶层 `vega` 对象中，服务端负责生成供应商要求的双层JSON字符串，调用方不要手写ExtInfo。

| 字段 | 模型 | 值与默认行为 |
|---|---|---|
| `enhance_prompt` | 全部 | auto、enable、disable；Lite默认enable，Pro默认disable |
| `moderation_mode` | 全部 | Moderation_L1、Moderation_L2；默认L1 |
| `generate_mode` | Lite | Standard、Fast、StandardMovie |
| `video_quality_mode` | Lite | Standard、Fast、SuperFast |
| `task_type` | 1.5 Pro | auto、reference、edit、extend；edit需要参考视频、ratio=adaptive和duration=-1；extend需要参考视频和ratio=adaptive |

服务端始终请求ReturnVegaUsage=true，不接受客户端关闭真实用量采集。Pro支持顶层 `return_last_frame`、`output_format`（mp4/mov）与 `seed`（整数-1～2147483647）；Lite不支持这三个字段。首尾帧模式遵循输入图片比例；Lite参考模式允许adaptive。

## 参考媒体规格

所有媒体必须是供应商可访问的HTTP(S) URL，或本Key、本渠道注册得到的asset://素材。本站不下载远程媒体做探测，不保证只凭扩展名就能满足真实编码要求；供应商会校验实际文件。

| 限制 | Lite | 1.0 Pro / Fast / Mini | 1.5 Pro |
|---|---|---|---|
| 图片数/视频数/音频数/总文件数 | 9/3/3/12 | 9/3/3/12 | 30/10/10/50 |
| 图片尺寸 | 每边256～5760 | 每边300～6000，宽高比0.4～2.5 | 同1.0 Pro |
| 图片格式 | jpg/jpeg/png/webp/heic/heif | jpeg/png/webp/bmp/tiff/gif/heic/heif | 同1.0 Pro |
| 单图片大小 | ≤30MB | <30MB | <30MB |
| 视频时长 | 每段2～15秒，总计≤15秒 | 每段2～15秒，总计≤15秒 | 每段2～30秒；文档未明确总时长上限 |
| 单视频大小 | ≤50MB | ≤50MB | ≤200MB |
| 视频格式 | H.264/H.265；音轨AAC/MP3 | mp4/mov，24～60fps | mp4/mov，H.264/H.265，音轨AAC/MP3，24～60fps |
| 视频尺寸 | 每边256～5760，宽高比0.4～2.5 | 每边300～6000，总像素409600～2086876，480p/720p/1080p | 每边300～6000，总像素409600～8295044，480p～4k |
| 音频 | wav/mp3，每段2～15秒，总计≤15秒，单个≤15MB | 同Lite | wav/mp3，每段2～30秒，总计≤30秒，单个≤15MB |

所有版本音频都必须搭配图片或视频。首帧、尾帧各最多一张，不能与参考图片/视频/音频混用。Lite提示词最多7000字符。Pro真人素材可能需要下述注册；不要通过伪造IsRealPerson绕过供应商审核。

## 素材与真人活体流程

完整的逐接口参数、请求及响应示例见 [Vega素材与活体接口](vega-materials.md)，HTML左侧目录为“Vega（腾讯云点播）→ 素材接口”。

仅Pro系列提供以下接口；统一为 `POST /v1/vega/{action}`，JSON中必填 `model`，其余字段沿用下表大小写。未知字段、SubAppId、凭证、回调URL、ExtInfo均拒绝。每个操作都使用业务Bearer Key，并记录调用日志。创建操作必须提供 `Idempotency-Key`，相同业务Key、相同操作、相同请求只提交一次；结果未确认时禁止换键重试。

| action | 请求字段（除model） | 说明 |
|---|---|---|
| CreateAigcLivenessValidate | 无 | 国内站发起活体认证；返回Response.H5Link和Response.LivenessToken |
| DescribeAigcLivenessValidateResult | LivenessToken | 先在H5Link完成认证；成功返回Status=DONE和GroupId |
| CreateAigcMaterial | FileInfo、AssetType；可选GroupId、AssetName、IsRealPerson、GroupName、GroupDescription | FileInfo为Type=Url和Url；AssetType为Image/Video/Audio；IsRealPerson是字符串True/False，默认False。非真人省略GroupId则本站生成隔离组；真人必须使用认证返回的GroupId |
| DescribeTaskDetail | TaskId | 使用本站创建素材时返回的id，不是上游Response.TaskId；从Response.CreateAigcMaterialTask读取状态和Output.AssetId |
| DescribeAigcMaterial | AssetId | 查询本Key登记的素材 |
| ModifyAigcMaterial | AssetId、AssetName | 修改素材名称 |
| DeleteAigcMaterial | AssetId或GroupId，二选一 | 删除单素材或整个组；删除组会删除组内全部素材 |
| ModifyAigcMaterialGroup | GroupId；可选GroupName、GroupDescription | 修改素材组 |
| DescribeAigcMaterialGroup | GroupId | 查询素材组 |
| DescribeAigcMaterialList | GroupId；可选AssetType、Limit、Offset | Limit=1～300，默认10；Offset≥0且为Limit整数倍 |

素材、组与活体令牌按项目、业务Key、Vega渠道隔离；不支持直接使用腾讯云控制台或其他Key创建的资源ID。素材属于供应商账户，但通过本站创建后才能在本站安全引用。国际站真人素材按供应商说明使用IsRealPerson=False，无需国内站活体接口；国内站真人应先完成活体认证，或由供应商明确开通免活体权限。

### 创建非真人素材

```bash
curl "$BASE_URL/v1/vega/CreateAigcMaterial" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: replace-with-unique-material-order" \
  -d '{"model":"vega-1.0-pro","FileInfo":{"Type":"Url","Url":"https://example.com/reference.png"},"AssetType":"Image","AssetName":"参考角色","IsRealPerson":"False"}'
```

把示例URL替换为真实可访问的素材地址。创建返回 `{"id":"tsk_...","Response":{"TaskId":"上游ID","RequestId":"..."}}`。

### 查询素材创建结果

```bash
curl "$BASE_URL/v1/vega/DescribeTaskDetail" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"vega-1.0-pro","TaskId":"替换为本站tsk_开头的素材任务id"}'
```

`Response.CreateAigcMaterialTask.Status=FINISH` 且 `ErrCode=0` 时，从 `Output.AssetId` 取素材ID。以 `asset://` 加该ID作为视频content中相应媒体URL，例如 `asset://asset-xxx`；不是火山的素材ID。创建/活体返回值包含敏感令牌和认证链接，不要公开分享；日志会脱敏这两项。

## 计费用量与价格

`GET /v1/pricing?model=vega-1.0-pro` 查询当前项目所绑定站点的人民币价格。全局价目包含domestic（国内人民币）与international（国际美元按固定汇率折算）两类维度。2026-10-22国际站折算汇率为1 USD=6.689327 CNY，后续可由超级管理员统一更新价格；不会在每次请求时联网换价。

- Lite：真实输出秒数＋真实输入视频秒数，按输出分辨率对应单价；真实输入图片超过5张的部分另收费。
- Pro系列无参考视频：真实输出秒数×无视频输入单价。
- Pro系列有参考视频：（真实输出秒数＋max(真实输入视频秒数，真实输出秒数×2/3)）×有视频输入单价。输入、输出同一分辨率档位。
- 仅成功视频计入模型账单；缺失真实InputSeconds、OutputSeconds或Lite图片数时进入待计价，绝不按请求时长补零估算。
- 素材注册、活体认证与腾讯云存储等不是上述视频模型价格的一部分；相关供应商收费不承诺免费，第一阶段不纳入本站视频自动计费。

默认并发通常为1路，提升需联系供应商；Pro需要供应商开通权限。429或超时后保留原幂等键，不自动重发付费创建。
