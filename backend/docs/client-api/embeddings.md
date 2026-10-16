# 文本与多模态向量

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

使用项目可用的 `doubao-embedding-vision`，请求和响应均为 JSON。

## 请求字段

`POST /v1/embeddings` 用于文本，`POST /v1/embeddings/multimodal` 用于多模态内容。

| 字段 | `/v1/embeddings` | `/v1/embeddings/multimodal` | 说明 |
|---|---:|---:|---|
| `model` | 必填 | 必填 | 使用 `/v1/models` 返回的别名，最长 128 个字符 |
| `input` | 必填 | 必填 | 文本接口当前一次只接受一个字符串或仅含一个字符串的数组；多模态接口接受内容数组 |
| `dimensions` | 可选 | 可选 | 只允许 `1024` 或 `2048` |
| `encoding_format` | 可选 | 可选 | 原样传递给供应商 |
| `instructions` | 可选 | 可选 | 原样传递给供应商 |
| `user` | 可选 | 不支持 | OpenAI 兼容字段 |
| `sparse_embedding` | 可选 | 不支持 | 当前文本适配不会向 embedding-vision 上游传递该字段 |

文本向量成功响应为 OpenAI 风格的 `object=list`，`data[].embedding` 为向量数组，`model` 会改写为客户提交的公开别名；响应头包含 `X-Request-Id`。

## 文本向量

文本向量化示例：

```bash
curl "$BASE_URL/v1/embeddings" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-embedding-vision","input":"星辰平台模型中转服务","dimensions":2048}'
```

## 多模态向量

`POST /v1/embeddings/multimodal` 的 `input` 是内容数组，不是 Chat 的 `messages`。文本、图片和视频可按供应商支持的内容格式组合；媒体必须是供应商能访问的地址，不能填写本机路径或私有网络 URL。模型能力以 `/v1/models` 为准。

```bash
curl "$BASE_URL/v1/embeddings/multimodal" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-embedding-vision",
    "input": [
      {"type": "text", "text": "白色背景上的蓝色杯子"},
      {"type": "image_url", "image_url": {"url": "https://customer.example.com/product.jpg"}}
    ],
    "dimensions": 2048
  }'
```

文本路径的成功响应经过 OpenAI 风格归一化，多模态路径保留供应商的多模态 JSON 结构，不应假定与文本路径的 `data[]` 相同。解析时区分所调用的路径；缺失 `usage` 不等于消耗为零。
