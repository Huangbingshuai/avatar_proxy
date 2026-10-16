# 文本对话、视觉理解与翻译

[文档首页](../../CLIENT_API.md) · [鉴权与通用约定](basics.md) · [错误与安全重试](errors.md)

## 文本接口概览

接口分别为：

```text
POST /v1/chat/completions
POST /v1/responses
```

## Chat Completions

`POST /v1/chat/completions`

请求格式兼容对应的 OpenAI JSON/SSE 习惯，`model` 必须使用 `/v1/models` 返回的别名。示例：

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5.2",
    "messages": [{"role": "user", "content": "请用三句话介绍产品"}],
    "stream": false
  }'
```

流式调用把 `stream` 设置为 `true`，响应类型为 `text/event-stream`。每个公开模型别名由服务端固定映射到一个真实上游模型，客户不能在请求中覆盖该 ID；中转层会把响应中的真实模型 ID 改回稳定别名。供应商没有返回 `usage` 时，系统不会伪造 Token 数。

流式示例（`-N` 用于关闭 curl 输出缓冲）：

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "用一句话介绍杭州"}],
    "stream": true,
    "stream_options": {"include_usage": true}
  }'
```

服务端逐段透传标准 SSE 数据，并以供应商的结束事件为准。客户端应逐行消费 `data:` 事件，不能等待整个响应完成后再一次性解析。流式连接中断后，服务端不会自动重放写请求；供应商没有返回最终 `usage` 时，用量字段保持未知。

Chat Completions 当前接受的顶层字段为：

```text
model, messages, stream, stream_options, frequency_penalty, function_call,
functions, logit_bias, logprobs, top_logprobs, max_completion_tokens,
max_tokens, n, parallel_tool_calls, presence_penalty, reasoning_effort,
response_format, seed, service_tier, stop, store, temperature, tool_choice,
tools, top_p, user, metadata
```

Responses 当前接受的顶层字段为：

```text
model, input, stream, background, conversation, include, instructions,
max_output_tokens, max_tool_calls, metadata, parallel_tool_calls,
previous_response_id, prompt, reasoning, safety_identifier, service_tier,
store, stream_options, temperature, text, tool_choice, tools, top_logprobs,
top_p, truncation, user
```

两类接口的 `model` 均必填且最长 128 个字符，`stream` 如提供必须为布尔值。上述字段表示中转站允许接收的顶层字段；具体模型是否支持其中某项能力，仍以 `/v1/models` 和供应商响应为准。

## Responses

`POST /v1/responses`

Responses 示例：

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5.2",
    "input": "列出三条新品发布检查项",
    "stream": false
  }'
```

## 翻译模型

`doubao-seed-translation` 只支持 Responses API，不支持 Chat Completions 或 SSE。每个待翻译文本需要在 `input_text` 中提供 `translation_options.target_language`；`source_language` 可省略并由模型自动识别：

```bash
curl "$BASE_URL/v1/responses" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-translation",
    "input": [{
      "role": "user",
      "content": [{
        "type": "input_text",
        "text": "你好",
        "translation_options": {
          "source_language": "zh",
          "target_language": "en"
        }
      }]
    }],
    "stream": false
  }'
```

文本接口会拒绝未列入兼容白名单的顶层字段，并返回 `422 text_parameter_unsupported`。请求中出现 `provider`、`channel`、`base_url`、`api_key`、`project` 或 `project_name` 等内部路由字段时返回 `422 route_override_forbidden`。

## 视觉理解

识图模型使用 OpenAI 兼容的图文消息，例如：

```bash
curl "$BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2.0-lite",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://customer.example.com/product.jpg"}},
        {"type": "text", "text": "描述图片中的商品和可见文字"}
      ]
    }],
    "stream": false
  }'
```

只有 `/v1/models` 返回的 `capabilities.imageInput=true` 模型接受图片内容；其他文本模型传入图片会返回 `model_image_input_unsupported`。

## 读取结果

非流式 Chat Completions 从 `choices[].message.content` 读取文本，Token 用量见供应商实际返回的 `usage`。Responses 从 `output` 中的消息及 `output_text` 内容项读取文本，不要按 Chat 的 `choices` 结构解析。

Chat 成功响应结构示例（内容和用量仅为示意）：

```json
{
  "id": "chatcmpl_example",
  "object": "chat.completion",
  "created": 1792108800,
  "model": "glm-5.2",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "你好。"}, "finish_reason": "stop"}
  ],
  "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11}
}
```

流式 Chat 消费 `choices[].delta`，不能把每个增量当成完整消息。Chat 通常以 `data: [DONE]` 结束；Responses 使用自己的事件类型与终态事件，二者不能混用解析器。流中可能出现错误事件，见[流式错误](errors.md#流式错误)。
