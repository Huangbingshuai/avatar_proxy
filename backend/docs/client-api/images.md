# 图片生成

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

## 创建图片

`POST /v1/images/generations`

请求：JSON。响应：同步 JSON。建议发送 `Idempotency-Key`；长耗时调用与断线处理见[安全重试](errors.md#幂等与断线恢复)。

Seedream 参考图片支持 HTTP(S) URL 或 `data:image/*;base64,...`。Base64 输入按解码后的真实文件大小校验，而不是按编码字符串长度估算；国内 `doubao-seedream-*` 模型单张参考图上限为 10 MiB，最多 10 张。HTTP(S) 图片还需通过最终的格式、尺寸和内容校验。这里是生图模型的参考图规则，与素材库 `/api/asset/upload-file` 的本地文件上传规则不同；素材库还可以不上传文件，直接登记符合素材规格的公网 HTTP(S) URL。

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: image-order-20260902-001" \
  -d '{
    "model": "doubao-seedream-5.0-lite",
    "prompt": "白色背景上的东方瓷器产品摄影",
    "image": "https://customer.example.com/reference.jpg",
    "n": 1,
    "response_format": "url"
  }'
```

`image` 可填写单个 HTTP(S) 图片 URL、图片 Data URL 或 URL 数组，具体数量由 `/v1/models` 的 `maxInputImages` 决定。`n` 必须是 1～15 的整数，并且不能超过该模型返回的 `maxN`；Seedream 的 `n>1` 只在支持组图的型号上生效，服务端会按所选模型生成组图。还可按模型能力使用 `size`、`output_format`、`watermark`、`sequential_image_generation`、`sequential_image_generation_options`、`optimize_prompt_options` 和 `tools`。不支持的模型能力会返回明确的 `422`，不会盲目透传。

`model` 必填且最长 128 个字符，`prompt` 必填且为 1～32000 个字符。`response_format` 只允许 `url` 或 `b64_json`，默认 `url`。除上述能力字段外，接口还允许供应商适配所需的 `background`、`moderation`、`output_compression`、`guidance_scale` 和 `seed`；是否实际生效取决于 `/v1/models` 返回的模型能力。

图片接口允许部分 OpenAI 兼容字段，但不会把 `quality`、`style`、`user` 等供应商无关字段用于国内 Seedream 模型，因此调用方不能把它们展示为对 Seedream 生效的控制项。`negative_prompt` 不属于当前公开图片契约，传入会返回 `422 image_parameter_unsupported`；负向要求应直接写入 `prompt`。当前公开接口只提供非流式 JSON 响应；传入 `stream=true` 会返回 `image_stream_unsupported`。返回 URL 属于供应商临时资源，本系统不会自动归档，请在供应商有效期内下载。

成功响应示例：

```json
{
  "created": 1788336000,
  "model": "doubao-seedream-5.0-lite",
  "data": [
    {"url": "https://provider.example.com/result.png"}
  ],
  "usage": {
    "generated_images": 1
  }
}
```

以实际响应为准：供应商没有返回的 `usage` 字段不会被补零。使用 `url` 时应及时下载结果；使用 `b64_json` 时，响应体可能明显增大。

## BytePlus Seedream

这三个模型统一调用 `POST /v1/images/generations`，仍填写星辰平台业务 Key；需要哪个模型，请联系管理员为项目开通。

| 模型别名 | 单次结果数量 | 参考图片 | `size` 等级 | `output_format` |
|---|---|---|---|---|
| `dola-seedream-5.0-pro` | 1 张 | 最多 10 张 | 1K、1.5K、2K | png、jpeg |
| `dola-seedream-5.0-flash` | 1 张 | 最多 10 张 | 1K、1.5K、2K | png、jpeg |
| `dola-seedream-5.0-lite` | 最多 15 张，参考图与结果图合计 ≤15 | 最多 14 张 | 2K、3K、4K | png、jpeg |

单张海外参考图的 Data URL 按解码后不超过 30 MiB 校验；URL 由海外供应商读取并执行最终媒体校验。三个模型默认 `size=2K`，也接受 `宽x高`：Pro/Flash 总像素须为 921,600～4,624,220，Lite 须为 3,686,400～16,777,216，宽高比均在 1/16～16 之间。

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: dola-image-order-001" \
  -d '{
    "model": "dola-seedream-5.0-flash",
    "prompt": "白色背景上的东方瓷器产品摄影",
    "n": 1,
    "size": "2K",
    "output_format": "png",
    "response_format": "url",
    "watermark": false
  }'
```

更换 `model` 为表中另一模型即可；增加 `image` 可使用参考图改图。Pro/Flash 不接受组图参数；Lite 的 `n>1` 自动转换为上游组图参数。只有 Pro 的 `optimize_prompt_options.mode` 接受 `fast`，三款均接受 `standard`。当前接入范围为非流式生图和参考图改图，暂未开放分层分解、透明背景、联网搜索或图片流式输出；这些模型不接受 OpenAI 的 `quality`、`style`、`background` 等专有参数。结果图片 URL 有效期通常为 24 小时，请及时下载。

Pro 的单图价按输出图实际像素分两档，Flash 和 Lite 按成功输出张数计价；维度含义见[海外模型计价维度](models.md#海外模型计价维度)，单价可用 `/v1/pricing` 核对。

## GPT Image 与渠道差异

同一个 `gpt-image-2` 可绑定 MaxModel 或 ModelTop，由管理员为项目选择；请求中始终只填写标准别名。先查询 `/v1/models` 的能力，不要因为名称相同而假定支持同样的参数。

| 渠道 | 模型 | 数量与输入 | 结果 |
|---|---|---|---|
| MaxModel | `gpt-image-2` | 当前单张，具体参数以能力为准 | 同步 JSON |
| ModelTop | `gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst` | 最多 10 张；当前只开放文生图 | 同步 JSON，优先读取 `data[].b64_json` |

### ModelTop 请求参数

对 `gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`，调用 `POST /v1/images/generations`，分别替换以下 `model`：

```json
{"model":"gpt-image-2","prompt":"白色背景上的蓝色陶瓷杯","n":1,"size":"1024x1024","quality":"medium","response_format":"b64_json"}
```

尺寸为 `auto` 或 `1024x1024`、`1536x1024`、`1024x1536`、`2048x2048`、`2048x1152`、`3840x2160`、`2160x3840`，不能用 `1K`/`2K` 简写。质量支持 `auto/low/medium/high`；两个 2.5 模型另支持 `xhigh/max`，以及自定义尺寸（边长≤3840，均为16的倍数，宽高比≤3:1，总像素655360～8294400）。2.5 另支持透明背景 `background=transparent`、`output_format=png/jpeg/webp`、JPEG/WebP 的 `output_compression=0..100`；透明背景不能用JPEG。原生返回Base64，请优先读取 `data[].b64_json`，不要假设请求 `url` 一定有URL。当前不提供 ModelTop 参考图编辑、流式或 `-gp` 异步生图。

## 请求字段速查

| 字段 | 必填 | 类型与限制 |
|---|---|---|
| `model` | 是 | 字符串，最长 128 个字符；项目可用的图片别名 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数，1～15；不得超过 `capabilities.maxN` |
| `image` | 否 | URL、Data URL 或数组；仅支持参考图的模型可用 |
| `size` | 否 | 字符串；格式、尺寸和默认值按型号/渠道区分 |
| `response_format` | 否 | `url`（默认）或 `b64_json`；ModelTop 可能只返回 Base64 |
| `quality` / `style` / `user` | 否 | 兼容字段；不会向国内 Seedream 转发 |
| `output_format` / `background` / `output_compression` | 否 | 仅模型支持时使用；具体组合见渠道说明 |
| `watermark` / `sequential_image_generation` / `sequential_image_generation_options` | 否 | 水印和组图，按模型能力使用 |
| `optimize_prompt_options` / `tools` | 否 | 提示词优化、工具；按模型能力使用 |
| `moderation` / `guidance_scale` / `seed` | 否 | 适配字段，不保证所有供应商支持 |
| `stream` | 否 | 只支持非流式；传 `true` 会拒绝 |

未列出的顶层字段返回 `422 image_parameter_unsupported`。不要套用其他平台的图片编辑路径或上传规则。
