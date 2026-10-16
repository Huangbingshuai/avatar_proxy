# 按供应商和模型接入

[文档首页](../../CLIENT_API.md) · [模型目录与价格](models.md) · [素材接口](assets.md)

## 火山引擎

### `deepseek-v4-flash`

文本对话

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `deepseek-v4-flash`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "deepseek-v4-flash",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "deepseek-v4-flash",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "deepseek-v4-flash",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 输入限制

该模型当前不接受图片输入；需要识图时选择 /v1/models 中 imageInput=true 的模型。

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "deepseek-v4-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=deepseek-v4-flash" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `deepseek-v4-flash` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `deepseek-v4-pro`

文本对话

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `deepseek-v4-pro`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "deepseek-v4-pro",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "deepseek-v4-pro",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "deepseek-v4-pro",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 输入限制

该模型当前不接受图片输入；需要识图时选择 /v1/models 中 imageInput=true 的模型。

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "deepseek-v4-pro",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=deepseek-v4-pro" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `deepseek-v4-pro` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `glm-5.2`

文本对话

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `glm-5.2`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "glm-5.2",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "glm-5.2",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "glm-5.2",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 输入限制

该模型当前不接受图片输入；需要识图时选择 /v1/models 中 imageInput=true 的模型。

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "glm-5.2",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=glm-5.2" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `glm-5.2` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedream-5.0-pro`

生图、参考图改图；最多 10 张参考图，单次 1 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedream-5.0-pro`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：1 |
| `size` | 否 | 本页示例使用 2K；其他尺寸等级或像素尺寸须符合该型号限制 |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-5.0-pro",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

最多 10 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 1。

quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-5.0-pro",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "doubao-seedream-5.0-pro",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedream-5.0-pro" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedream-5.0-pro` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedream-5.0-lite`

生图、参考图改图、组图；最多 10 张参考图、15 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedream-5.0-lite`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：15 |
| `size` | 否 | 本页示例使用 2K；其他尺寸等级或像素尺寸须符合该型号限制 |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |
| `sequential_image_generation` / `sequential_image_generation_options` | 否 | 组图参数，结果数量不得超过 maxN |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-5.0-lite",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

最多 10 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 15。

quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-5.0-lite",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "doubao-seedream-5.0-lite",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedream-5.0-lite" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedream-5.0-lite` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedream-5.0`

生图、参考图改图；最多 10 张参考图，单次 1 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedream-5.0`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：1 |
| `size` | 否 | 本页示例使用 2K；其他尺寸等级或像素尺寸须符合该型号限制 |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-5.0",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

最多 10 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 1。

quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-5.0",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "doubao-seedream-5.0",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedream-5.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedream-5.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedream-4.5`

生图、参考图改图、组图；最多 10 张参考图、15 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedream-4.5`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：15 |
| `size` | 否 | 本页示例使用 2K；其他尺寸等级或像素尺寸须符合该型号限制 |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |
| `sequential_image_generation` / `sequential_image_generation_options` | 否 | 组图参数，结果数量不得超过 maxN |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-4.5",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

最多 10 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 15。

quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-4.5",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "doubao-seedream-4.5",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedream-4.5" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedream-4.5` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedream-4.0`

生图、参考图改图、组图；最多 10 张参考图、15 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedream-4.0`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：15 |
| `size` | 否 | 本页示例使用 2K；其他尺寸等级或像素尺寸须符合该型号限制 |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |
| `sequential_image_generation` / `sequential_image_generation_options` | 否 | 组图参数，结果数量不得超过 maxN |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-4.0",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

最多 10 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 15。

quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedream-4.0",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "doubao-seedream-4.0",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedream-4.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedream-4.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-2.1-pro`

文本、识图

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-2.1-pro`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-pro",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-pro",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-pro",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-pro",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-2.1-pro",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-2.1-pro" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-2.1-pro` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-2.1-turbo`

文本、识图

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-2.1-turbo`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-turbo",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-turbo",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-turbo",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.1-turbo",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-2.1-turbo",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-2.1-turbo" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-2.1-turbo` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-2.0-pro`

文本、识图

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-2.0-pro`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-pro",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-pro",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-pro",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-pro",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-2.0-pro",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-2.0-pro" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-2.0-pro` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-2.0-lite`

文本、识图

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-2.0-lite`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-lite",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-lite",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-lite",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-lite",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-2.0-lite",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-2.0-lite" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-2.0-lite` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-2.0-mini`

文本、识图

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-2.0-mini`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-mini",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-mini",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-mini",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-mini",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-2.0-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-2.0-mini" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-2.0-mini` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-evolving`

文本、识图、Coding 与 Agent

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-evolving`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-evolving",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-evolving",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-evolving",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-evolving",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-evolving",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-evolving" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-evolving` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-character`

文本对话、角色扮演

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-character`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-character",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-character",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-character",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 输入限制

该模型当前不接受图片输入；需要识图时选择 /v1/models 中 imageInput=true 的模型。

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-character",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-character" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-character` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-2.0-code`

文本、识图、编程

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/chat/completions` · `POST /v1/responses`


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-2.0-code`，最长 128 个字符 |
| `messages` | Chat 必填 | 消息数组，包含 role 和 content |
| `input` | Responses 必填 | 文本或结构化输入；不要同时套用 Chat 消息体 |
| `stream` | 否 | 布尔值；true 为 SSE，false 为同步 JSON |
| `stream_options` | 否 | Chat 流式用量可使用 `{"include_usage":true}` |
| `max_completion_tokens` / `max_tokens` | 否 | Chat 输出上限，具体支持情况由模型决定 |
| `max_output_tokens` | 否 | Responses 输出上限，具体支持情况由模型决定 |
| `temperature` / `top_p` | 否 | 采样参数，模型支持范围以实际能力为准 |

顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。

#### 请求示例

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-code",
  "messages": [
    {
      "role": "user",
      "content": "用一句话介绍你自己"
    }
  ],
  "stream": false
}'
```

#### 流式调用

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-code",
  "messages": [
    {
      "role": "user",
      "content": "用一句话描述春天"
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  }
}'
```

逐段消费 `choices[].delta`。不能等待整个响应完成后才解析，也不能将中断当作完整成功。

#### Responses 调用

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-code",
  "input": "列出三条产品发布检查项",
  "stream": false
}'
```

#### 图片理解

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-2.0-code",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "描述图片中的商品"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://customer.example.com/product.jpg"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "model": "doubao-seed-2.0-code",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 3,
    "total_tokens": 11
  }
}
```

以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-2.0-code" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-2.0-code` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-translation`

文本翻译

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/responses`

只支持非流式 Responses 翻译，不支持 Chat Completions。每个文本项必须提供目标语言。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seed-translation`，最长 128 个字符 |
| `input` | 是 | 结构化消息数组，文本项使用 `input_text` |
| `translation_options.target_language` | 是 | 字符串，目标语言，例如 en |
| `translation_options.source_language` | 否 | 源语言；省略时自动识别 |
| `stream` | 否 | 仅支持 false |

#### 请求示例

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-translation",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "你好",
          "translation_options": {
            "source_language": "zh",
            "target_language": "en"
          }
        }
      ]
    }
  ],
  "stream": false
}'
```

#### 返回结果

按 Responses 的 `output` 消息读取 `output_text` 内容，不使用 Chat 的 choices 结构。用量只包含实际返回的 usage。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-translation" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-translation` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedance-2.5`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedance-2.5`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～30 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedance-2.5",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "doubao-seedance-2.5",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedance-2.5" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedance-2.5` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedance-2.0`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedance-2.0`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedance-2.0",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "doubao-seedance-2.0",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedance-2.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedance-2.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedance-2.0-fast`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedance-2.0-fast`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedance-2.0-fast",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "doubao-seedance-2.0-fast",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedance-2.0-fast" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedance-2.0-fast` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedance-2.0-mini`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedance-2.0-mini`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedance-2.0-mini",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "doubao-seedance-2.0-mini",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedance-2.0-mini" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedance-2.0-mini` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedance-1.0-pro`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedance-1.0-pro`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 2～12 秒 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedance-1.0-pro",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "doubao-seedance-1.0-pro",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedance-1.0-pro" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedance-1.0-pro` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedance-1.0-pro-fast`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `doubao-seedance-1.0-pro-fast`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 2～12 秒 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "doubao-seedance-1.0-pro-fast",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "doubao-seedance-1.0-pro-fast",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedance-1.0-pro-fast" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedance-1.0-pro-fast` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-embedding-vision`

文本、图片和视频多模态向量化

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：火山引擎。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_ark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。



使用项目可用的 `doubao-embedding-vision`，请求和响应均为 JSON。

#### 请求参数

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

#### 文本向量

文本向量化示例：

```bash
curl "$BASE_URL/v1/embeddings" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-embedding-vision","input":"星辰平台模型中转服务","dimensions":2048}'
```

#### 多模态向量

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


#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-embedding-vision" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-embedding-vision` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

## BytePlus

### `dreamina-seedance-2.5`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[ModelTop](#dreamina-seedance-25-modeltop-供应商)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.5`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～30 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |
| `output_format` | 否 | mp4、mov |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.5",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 30 张，视频最多 10 个，音频最多 10 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 BytePlus。不接受 seed、camera_fixed、frames、draft 或 service_tier=flex。支持 return_last_frame。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.5",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.5" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.5` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.0`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[ModelTop](#dreamina-seedance-20-modeltop-供应商)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 BytePlus。不接受 seed、camera_fixed、frames、draft 或 service_tier=flex。不支持 return_last_frame=true。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.0-fast`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[ModelTop](#dreamina-seedance-20-fast-modeltop-供应商)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-fast`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-fast",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 BytePlus。不接受 seed、camera_fixed、frames、draft 或 service_tier=flex。不支持 return_last_frame=true。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-fast",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-fast" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-fast` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.0-mini`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[ModelTop](#dreamina-seedance-20-mini-modeltop-供应商)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

`DELETE /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。支持取消；BytePlus 仅允许取消排队任务，运行中任务可能被拒绝。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-mini`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-mini",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 BytePlus。不接受 seed、camera_fixed、frames、draft 或 service_tier=flex。不支持 return_last_frame=true。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-mini",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

#### 取消任务

```bash
curl -X DELETE "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-mini" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-mini` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dola-seedream-5.0-pro`

生图、参考图改图；单次 1 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dola-seedream-5.0-pro`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：1 |
| `size` | 否 | 支持 1K、1.5K、2K，默认 2K |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dola-seedream-5.0-pro",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

参考图单张 Data URL 解码后不超过 30 MiB。每次只输出 1 张，不接受组图参数。

Pro/Flash 自定义尺寸总像素为 921,600～4,624,220；Lite 为 3,686,400～16,777,216，宽高比为 1/16～16。三款支持 png/jpeg，不接受 quality、style、background；Pro 的提示词优化额外支持 fast。

完整型号差异见[海外 Seedream 参数](images.md#byteplus-seedream)。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dola-seedream-5.0-pro",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "dola-seedream-5.0-pro",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dola-seedream-5.0-pro" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dola-seedream-5.0-pro` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dola-seedream-5.0-flash`

生图、参考图改图；单次 1 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dola-seedream-5.0-flash`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：1 |
| `size` | 否 | 支持 1K、1.5K、2K，默认 2K |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 10 张参考图 |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dola-seedream-5.0-flash",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

参考图单张 Data URL 解码后不超过 30 MiB。每次只输出 1 张，不接受组图参数。

Pro/Flash 自定义尺寸总像素为 921,600～4,624,220；Lite 为 3,686,400～16,777,216，宽高比为 1/16～16。三款支持 png/jpeg，不接受 quality、style、background；Pro 的提示词优化额外支持 fast。

完整型号差异见[海外 Seedream 参数](images.md#byteplus-seedream)。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dola-seedream-5.0-flash",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "dola-seedream-5.0-flash",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dola-seedream-5.0-flash" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dola-seedream-5.0-flash` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dola-seedream-5.0-lite`

生图、参考图改图、组图；最多 15 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：BytePlus。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`byteplus_modelark` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dola-seedream-5.0-lite`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：15 |
| `size` | 否 | 支持 2K、3K、4K，默认 2K |
| `response_format` | 否 | url 或 b64_json；默认 url |
| `image` | 否 | URL、Data URL 或数组；最多 14 张参考图 |
| `sequential_image_generation` / `sequential_image_generation_options` | 否 | 组图参数，结果数量不得超过 maxN |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dola-seedream-5.0-lite",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K"
}'
```

#### 模型限制

参考图单张 Data URL 解码后不超过 30 MiB。参考图与结果图合计不能超过 15。

Pro/Flash 自定义尺寸总像素为 921,600～4,624,220；Lite 为 3,686,400～16,777,216，宽高比为 1/16～16。三款支持 png/jpeg，不接受 quality、style、background；Pro 的提示词优化额外支持 fast。

完整型号差异见[海外 Seedream 参数](images.md#byteplus-seedream)。

#### 参考图示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dola-seedream-5.0-lite",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "response_format": "url",
  "size": "2K",
  "image": "https://customer.example.com/reference.jpg"
}'
```

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "dola-seedream-5.0-lite",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dola-seedream-5.0-lite" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dola-seedream-5.0-lite` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

## MaxModel

### `gpt-image-2`

同步文生图；单次 1 张结果

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：MaxModel。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`maxmodel` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[ModelTop](#gpt-image-2-modeltop-供应商)。请选择项目实际绑定的供应商。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `gpt-image-2`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：1 |
| `size` | 否 | 像素尺寸，例如 1024x1024；不能使用 1K/2K 简写 |
| `response_format` | 否 | url 或 b64_json；默认 url |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "gpt-image-2",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "size": "1024x1024",
  "response_format": "url"
}'
```

#### 模型限制

此页只适用于 MaxModel。当前单次只能生成 1 张；不要套用 ModelTop 的多图、自定义尺寸、透明背景或图片 Token 能力。示例仅使用当前已接入的同步文生图字段。其他兼容选项由该渠道校验，不作为本页可用能力承诺。

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "gpt-image-2",
  "data": [
    {
      "url": "https://provider.example.com/result.png"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=gpt-image-2" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `gpt-image-2` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

## ModelTop

### dreamina-seedance-2.5 ModelTop 供应商

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[BytePlus](#dreamina-seedance-25)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.5`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～30 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.5",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 30 张，视频最多 10 个，音频最多 10 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.5",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.5" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.5` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### dreamina-seedance-2.0 ModelTop 供应商

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[BytePlus](#dreamina-seedance-20)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p、4k |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### dreamina-seedance-2.0-fast ModelTop 供应商

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[BytePlus](#dreamina-seedance-20-fast)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-fast`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-fast",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-fast",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-fast" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-fast` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### dreamina-seedance-2.0-mini ModelTop 供应商

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[BytePlus](#dreamina-seedance-20-mini)。请选择项目实际绑定的供应商。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-mini`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-mini",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-mini",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-mini" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-mini` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### gpt-image-2 ModelTop 供应商

同步文生图；最多 10 张，原生返回 Base64

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

同名模型的其他供应商参考：[MaxModel](#gpt-image-2)。请选择项目实际绑定的供应商。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `gpt-image-2`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：10 |
| `size` | 否 | 像素尺寸，例如 1024x1024；不能使用 1K/2K 简写 |
| `response_format` | 否 | url 或 b64_json；ModelTop 原生返回 Base64，此参数不传往上游，按 data[].b64_json 读取 |
| `quality` | 否 | auto、low、medium、high；默认 auto |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "gpt-image-2",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "size": "1024x1024",
  "response_format": "b64_json"
}'
```

#### 模型限制

此页只适用于 ModelTop。当前只开放文生图，不提供参考图编辑、流式或 -gp 异步生图。

最多 10 张，不支持自定义尺寸、透明背景或显式 output_format/output_compression。可选背景仅 auto、opaque。

size 可选 auto、1024x1024、1536x1024、1024x1536、2048x2048、2048x1152、3840x2160、2160x3840。不能使用 1K/2K 简写。

不接受 image、watermark、style、seed、tools、moderation 等其他渠道字段。原生返回 Base64，响应中的 usage 保留实际细分 Token，不按固定张价推算。

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "gpt-image-2",
  "data": [
    {
      "b64_json": "BASE64_IMAGE_DATA"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=gpt-image-2" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `gpt-image-2` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `gpt-image-2.5-flare`

文生图；最多 10 张

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `gpt-image-2.5-flare`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：10 |
| `size` | 否 | 像素尺寸，例如 1024x1024；不能使用 1K/2K 简写 |
| `response_format` | 否 | url 或 b64_json；ModelTop 原生返回 Base64，此参数不传往上游，按 data[].b64_json 读取 |
| `quality` | 否 | auto、low、medium、high、xhigh、max；默认 auto |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "gpt-image-2.5-flare",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "size": "1024x1024",
  "response_format": "b64_json"
}'
```

#### 模型限制

此页只适用于 ModelTop。当前只开放文生图，不提供参考图编辑、流式或 -gp 异步生图。

支持透明背景、自定义尺寸、png/jpeg/webp 和输出压缩率。透明背景不能输出 JPEG。

size 可选 auto、1024x1024、1536x1024、1024x1536、2048x2048、2048x1152、3840x2160、2160x3840。不能使用 1K/2K 简写。

自定义尺寸边长≤3840，均为16的倍数，宽高比≤3:1，总像素655360～8294400。background 为 auto/opaque/transparent；output_format 为 png/jpeg/webp；仅 JPEG/WebP 可设置整数 output_compression=0..100。

不接受 image、watermark、style、seed、tools、moderation 等其他渠道字段。原生返回 Base64，响应中的 usage 保留实际细分 Token，不按固定张价推算。

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "gpt-image-2.5-flare",
  "data": [
    {
      "b64_json": "BASE64_IMAGE_DATA"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=gpt-image-2.5-flare" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `gpt-image-2.5-flare` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `gpt-image-2.5-sunburst`

文生图；最多 10 张

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /v1/images/generations`

请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `gpt-image-2.5-sunburst`，最长 128 个字符 |
| `prompt` | 是 | 字符串，1～32000 个字符 |
| `n` | 否 | 整数；该模型数量限制：10 |
| `size` | 否 | 像素尺寸，例如 1024x1024；不能使用 1K/2K 简写 |
| `response_format` | 否 | url 或 b64_json；ModelTop 原生返回 Base64，此参数不传往上游，按 data[].b64_json 读取 |
| `quality` | 否 | auto、low、medium、high、xhigh、max；默认 auto |

#### 请求示例

```bash
curl "$BASE_URL/v1/images/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "gpt-image-2.5-sunburst",
  "prompt": "白色背景上的蓝色陶瓷杯",
  "n": 1,
  "size": "1024x1024",
  "response_format": "b64_json"
}'
```

#### 模型限制

此页只适用于 ModelTop。当前只开放文生图，不提供参考图编辑、流式或 -gp 异步生图。

支持透明背景、自定义尺寸、png/jpeg/webp 和输出压缩率。透明背景不能输出 JPEG。

size 可选 auto、1024x1024、1536x1024、1024x1536、2048x2048、2048x1152、3840x2160、2160x3840。不能使用 1K/2K 简写。

自定义尺寸边长≤3840，均为16的倍数，宽高比≤3:1，总像素655360～8294400。background 为 auto/opaque/transparent；output_format 为 png/jpeg/webp；仅 JPEG/WebP 可设置整数 output_compression=0..100。

不接受 image、watermark、style、seed、tools、moderation 等其他渠道字段。原生返回 Base64，响应中的 usage 保留实际细分 Token，不按固定张价推算。

#### 返回结果

```json
{
  "created": 1792108800,
  "model": "gpt-image-2.5-sunburst",
  "data": [
    {
      "b64_json": "BASE64_IMAGE_DATA"
    }
  ]
}
```

结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。

完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=gpt-image-2.5-sunburst" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `gpt-image-2.5-sunburst` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.5-filter-off`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.5-filter-off`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～30 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.5-filter-off",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 30 张，视频最多 10 个，音频最多 10 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.5-filter-off",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.5-filter-off" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.5-filter-off` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.0-filter-off`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-filter-off`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p、1080p、4k |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-filter-off",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-filter-off",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-filter-off" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-filter-off` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.0-fast-filter-off`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-fast-filter-off`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-fast-filter-off",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-fast-filter-off",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-fast-filter-off" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-fast-filter-off` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `dreamina-seedance-2.0-mini-filter-off`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：ModelTop。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`modeltop` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `dreamina-seedance-2.0-mini-filter-off`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 4～15 秒；支持 -1 智能时长 |
| `resolution` | 否 | 480p、720p |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |
| `seed` | 否 | 随机种子；当前渠道接受，具体范围由供应商校验 |
| `return_last_frame` | 否 | 布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取 |
| `service_tier` | 否 | 仅 default |
| `execution_expires_after` | 否 | 3600～259200 的整数秒 |
| `task_type` | 否 | t2v 或 i2v |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "dreamina-seedance-2.0-mini-filter-off",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。

图片最多 9 张，视频最多 3 个，音频最多 3 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。

此页只适用于 ModelTop。接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。

素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "dreamina-seedance-2.0-mini-filter-off",
  "status": "succeeded",
  "resolution": "480p",
  "ratio": "16:9",
  "duration": 4,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=dreamina-seedance-2.0-mini-filter-off" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `dreamina-seedance-2.0-mini-filter-off` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

## 豆包语音

### `doubao-seed-tts-2.0`

语音合成

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：豆包语音。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_speech` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口与参数

`POST /v1/audio/speech`

请求：JSON。成功响应：音频二进制。

语音合成字段：

| 字段 | 必填 | 默认值与约束 |
|---|---:|---|
| `model` | 是 | 必须为可用的 `doubao-seed-tts-2.0` 别名 |
| `input` | 是 | 1～10000 个字符 |
| `voice` | 是 | 当前语音项目已开通的 TTS 2.0 音色 ID，最长 128 个字符 |
| `response_format` | 否 | 默认 `mp3`；可选 `mp3`、`pcm`、`ogg_opus` |
| `sample_rate` | 否 | 默认 `24000`；可选 `8000`、`16000`、`22050`、`24000`、`32000`、`44100`、`48000` |
| `speed` | 否 | 默认 `0`；范围 `-50`～`100` 的整数 |

语音合成成功时直接返回音频二进制，Content-Type 分别为 `audio/mpeg`、`audio/L16` 或 `audio/ogg`，响应头包含 `X-Request-Id`，不要把响应体按 JSON 解析。

语音合成示例（`voice` 必须是当前语音项目已开通的 TTS 2.0 音色 ID）：

```bash
curl "$BASE_URL/v1/audio/speech" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"doubao-seed-tts-2.0",
    "input":"欢迎使用星辰平台创作空间",
    "voice":"zh_female_vv_uranus_bigtts",
    "response_format":"mp3"
  }' \
  --output speech.mp3
```

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-tts-2.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-tts-2.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seedasr-2.0`

异步录音识别

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：豆包语音。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_speech` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口与参数

`POST /v1/audio/transcriptions`

请求：JSON（音频 URL），不是文件 multipart。成功返回 `202`，然后查询任务。

录音识别字段：

| 字段 | 必填 | 默认值与约束 |
|---|---:|---|
| `model` | 是 | 必须为可用的 `doubao-seedasr-2.0` 别名 |
| `url` | 是 | 公网可访问的 HTTPS 音频 URL，最长 2048 个字符 |
| `language` | 否 | 语言提示；省略时由供应商处理 |
| `enable_speaker_info` | 否 | 默认 `false`，是否返回说话人信息 |

录音识别创建成功返回 `202`。创建和查询都必须使用同一枚业务 Key；`Idempotency-Key` 可选，见[幂等与断线恢复](errors.md#幂等与断线恢复)。任务响应固定包含 `id`、`object=audio.transcription`、`model`、`status` 和 `created_at`；成功后增加 `text` 和可用时的 `duration`，失败时增加 `error.code` 与 `error.message`。

录音识别只接受公网可访问的 HTTPS 音频 URL，并使用异步任务：

```bash
curl "$BASE_URL/v1/audio/transcriptions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: asr-order-001" \
  -d '{"model":"doubao-seedasr-2.0","url":"https://example.com/meeting.mp3"}'
```

保存 `202` 响应中的 `id`，作为下文的 `TASK_ID`；不要使用示例 ID 查询自己的任务。

#### 查询结果

`GET /v1/audio/transcriptions/{taskId}`

任务状态为 `queued`、`running`、`succeeded` 或 `failed`；成功时响应包含 `text` 和供应商返回的真实 `duration`。不要将创建返回 `202` 当成识别完成。

将创建返回的 `id` 设置为环境变量 `TASK_ID`，使用创建时的同一枚业务 Key 每 5～10 秒查询，直到终态：

```bash
curl "$BASE_URL/v1/audio/transcriptions/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

```json
{
  "id": "asr_example",
  "object": "audio.transcription",
  "model": "doubao-seedasr-2.0",
  "status": "succeeded",
  "created_at": 1792108800,
  "text": "欢迎使用星辰平台。",
  "duration": 2.5
}
```

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seedasr-2.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seedasr-2.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

### `doubao-seed-audio-1.0`

音频生成

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：豆包语音。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`volcengine_speech` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口与参数

`POST /v1/audio/generations`

请求、响应：JSON。

音频生成字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `model` | 是 | 必须为可用的 `doubao-seed-audio-1.0` 别名 |
| `prompt` | 是 | 1～4000 个字符 |
| `speaker` | 否 | 供应商支持的音色或说话人参数 |
| `audio_url` / `audio_data` | 否 | 可选音频参考输入 |
| `image_url` / `image_data` | 否 | 可选图片参考输入 |
| `duration` | 否 | 期望时长，由供应商校验 |
| `format` | 否 | 期望输出格式，由供应商校验 |

音频生成成功响应包含 `created`、公开模型别名 `model` 和 `data` 数组；`data[0]` 可能包含 `url`、`audio`、`duration`、`original_duration` 或 `subtitle`，只返回供应商实际提供的字段，响应头包含 `X-Request-Id`。

音频生成示例：

```bash
curl "$BASE_URL/v1/audio/generations" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-audio-1.0","prompt":"雨夜咖啡馆，轻柔爵士乐与窗外雨声","format":"mp3"}'
```

响应可能包含临时 `url` 或音频 Base64。临时 URL 由供应商托管并可能过期，调用方应及时下载；中转站不会自动归档媒体。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=doubao-seed-audio-1.0" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `doubao-seed-audio-1.0` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

## 阿里百炼

### `wan3.0-video`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：阿里百炼。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`aliyun_bailian` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `wan3.0-video`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 模型支持的时长，按当前能力和返回校验结果设置 |
| `resolution` | 否 | 当前默认 1080P |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 按模型能力决定是否接受，示例中省略 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "wan3.0-video",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 8,
  "resolution": "1080P",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

最多一张 HTTP(S) 首帧图片，role 必须为 first_frame。只支持 duration、resolution、ratio、generate_audio、watermark，不支持 seed 等额外参数。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "wan3.0-video",
  "status": "succeeded",
  "resolution": "1080P",
  "ratio": "16:9",
  "duration": 8,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=wan3.0-video" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `wan3.0-video` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。

## MiniMax

### `minimax-h3`

异步视频

[鉴权](basics.md) · [错误与安全重试](errors.md)

需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。

供应商：MiniMax。本页适用于项目绑定的该供应商渠道；公开路径及 model 名称保持不变。用 /v1/pricing 中同名项的 provider=`minimax` 确认当前供应商，再用 /v1/models 核对能力。目录只用于查阅，不会切换供应商；不要向请求体增加 provider/channel 字段。

#### 接口

`POST /api/v3/contents/generations/tasks`

`GET /api/v3/contents/generations/tasks/{taskId}`

创建为异步操作。当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。


#### 请求参数

| 参数 | 必填 | 类型与说明 |
|---|---|---|
| `model` | 是 | 固定填写 `minimax-h3`，最长 128 个字符 |
| `content` | 是 | 内容数组，包含文本及模型支持的参考素材 |
| `duration` | 否 | 模型支持的时长，按当前能力和返回校验结果设置 |
| `resolution` | 否 | 当前默认 768P |
| `ratio` | 否 | 画幅比例，例如 16:9；不使用 aspect_ratio |
| `generate_audio` | 否 | 不支持该字段 |
| `watermark` | 否 | 布尔值，按模型能力决定是否支持 |

#### 创建示例

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: customer-order-unique-id" \
  -d '{
  "model": "minimax-h3",
  "content": [
    {
      "type": "text",
      "text": "晨光下的海面，镜头缓慢推进"
    }
  ],
  "duration": 6,
  "resolution": "768P",
  "ratio": "16:9"
}'
```

#### 模型与素材限制

只接受 HTTP(S) 图片，内容总计不超过 20 项。支持 duration、resolution、ratio、seed、watermark，不支持 generate_audio 与取消任务。

#### 创建响应

```json
{
  "id": "vid_example"
}
```

#### 查询结果

```bash
curl "$BASE_URL/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Authorization: Bearer $API_KEY"
```

必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。

#### 成功结果示例

```json
{
  "id": "vid_example",
  "model": "minimax-h3",
  "status": "succeeded",
  "resolution": "768P",
  "ratio": "16:9",
  "duration": 6,
  "content": {
    "video_url": "https://provider.example.com/result.mp4"
  }
}
```

若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在供应商返回时出现，尤其 Wan 不保证返回全部维度。

公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。

#### 查询模型价格

```bash
curl "$BASE_URL/v1/pricing?model=minimax-h3" \
  -H "Authorization: Bearer $API_KEY"
```

价格查询按名称包含匹配，请从 data 中选择 id 完全等于 `minimax-h3` 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。
