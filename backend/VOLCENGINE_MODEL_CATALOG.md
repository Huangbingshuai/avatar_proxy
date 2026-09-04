# 火山方舟模型目录维护与验收记录

更新日期：2026-09-04

本文档供项目维护人员使用，记录方舟模型进入 Star Proxy 内置目录的判定标准、固定映射和验收方法。客户可见的实时模型清单始终以业务 Key 请求 `GET /v1/models` 的结果为准，完整调用契约以 [CLIENT_API.md](CLIENT_API.md) 为准。

## 当前新增模型

| 对外别名 | 固定上游模型 ID | 支持接口 | 响应方式 |
|---|---|---|---|
| `deepseek-v4-pro` | `deepseek-v4-pro-ga-260813` | `/v1/chat/completions`、`/v1/responses` | JSON、SSE |
| `doubao-seed-evolving` | `doubao-seed-evolving` | `/v1/chat/completions`、`/v1/responses` | JSON、SSE |
| `doubao-seed-character` | `doubao-seed-character-260628` | `/v1/chat/completions`、`/v1/responses` | JSON、SSE |
| `doubao-seed-2.0-code` | `doubao-seed-2-0-code-preview-260215` | `/v1/chat/completions`、`/v1/responses` | JSON、SSE |
| `doubao-seed-translation` | `doubao-seed-translation-250915` | `/v1/responses` | 同步 JSON |
| `doubao-embedding-vision` | `doubao-embedding-vision-251215` | `/v1/embeddings`、`/v1/embeddings/multimodal` | 同步 JSON |
| `doubao-seed-tts-2.0` | `seed-tts-2.0` | `/v1/audio/speech` | 音频二进制 |
| `doubao-seedasr-2.0` | `volc.seedasr.auc` | `/v1/audio/transcriptions` | 异步任务 |
| `seed-audio-1.0` | `seed-audio-1.0` | `/v1/audio/generations` | 同步 JSON |

模型别名与上游 ID 在 `backend/app/database.py` 中一一固定。管理员只为项目选择供应商渠道并启用模型，客户和管理员都不能在请求中改写上游模型 ID。

向量模型复用项目的火山方舟渠道。后三个语音模型属于豆包语音产品线，必须创建独立的 `volcengine_speech` 渠道并填写语音技术控制台新建的 API Key；方舟 Key 与语音 Key 不可混用。语音渠道没有免费的鉴权探测接口，控制台“测试”只提示需要真实模型调用，不会为了探测凭证自动产生费用。

## 对外别名命名规范与 5.5 迁移

Star Proxy 对外模型别名是稳定的客户接口契约，不等同于火山方舟带日期的上游模型 ID。豆包产品线统一保留 `doubao-` 前缀：

| 旧别名（停止接受） | 标准别名 |
|---|---|
| `seedream-5.0` | `doubao-seedream-5.0` |
| `seedream-5.0-lite` | `doubao-seedream-5.0-lite` |
| `seedance-2.0` | `doubao-seedance-2.0` |
| `seedance-2.0-fast` | `doubao-seedance-2.0-fast` |
| `seedance-2.5` | `doubao-seedance-2.5` |

其余 Seedream 4.x、Seedream 5.0 Pro、Seedance 1.0 Pro 与 Seedance 2.0 Mini 采用相同规则。未使用 Doubao 品牌的官方模型系列（例如 `seed-audio-1.0`）保留其官方名称，不机械增加前缀。

本次变更不提供旧请求别名兼容层：客户端必须先通过 `GET /v1/models` 获取可用模型，并将静态配置更新为标准别名；继续传旧别名会返回 `model_not_allowed`。服务启动时只对已有数据库引用执行一次原子迁移，覆盖项目模型绑定、API Key 模型权限、推理任务、用量、费率与账单记录，避免历史数据和权限断裂。上游固定 ID 继续由中转站维护，客户不得直接传入或依赖它。

## 2026-09-04 验收记录

使用本地 `test_hb` 项目及其业务 Key 从客户视角发起真实请求，文本模型新增项均返回 HTTP 200。真实用量合计 307 Tokens，供应商请求 ID 和分项用量保存在本地 `inference_usage` 中；文档、测试输出和 Git 变更均不保存业务 Key 或供应商凭证明文。向量和语音模型需使用对应产品渠道另行验收，自动测试不会产生真实调用费用。

翻译模型必须使用 Responses 结构化输入：

```json
{
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
  ]
}
```

该模型不支持 Chat Completions 和 SSE。服务端会在请求上游前返回明确的 `422 model_operation_unsupported`，客户工具则自动切换到非流式 Responses 请求。

## 模型进入目录的条件

新增模型必须同时满足：

1. 官方模型列表仍处于可调用状态，并取得完整、稳定的上游模型 ID；
2. 当前项目渠道能够访问该模型；
3. 使用供应商官方请求结构完成至少一次真实端到端调用；
4. 明确验证支持的接口、流式能力、多模态输入和用量字段；
5. 使用 MockTransport 补齐 URL、请求头、请求体、响应和错误转换测试；
6. 更新 `BUILTIN_MODEL_CATALOG`、客户接口文档、图标映射及必要的客户工具表单；
7. 运行后端测试、客户工具 lint、TypeScript 检查和生产构建；
8. 扫描工作树，确认业务 Key、供应商凭证和管理员密码没有进入 Git。

仅出现在供应商模型枚举中，不代表能够通过当前中转接口调用。未经端到端验证的候选模型不得作为禁用占位保留在内置目录中。

## 下线与删除规则

确认不可调用且没有任务、用量或账单历史的模型，应删除项目绑定、Key 权限、价目和模型目录记录，不在控制台或 `/v1/models` 中保留隐藏占位。

若模型已有成功用量、异步任务或冻结账单，必须先保留历史对账数据并制定迁移方案，不能为了清理目录破坏既有账单。公开客户文档只维护当前支持清单，不展示内部候选或下架模型列表。

真实供应商验证会产生费用，只能在用户明确授权后手动执行；自动测试不得连接真实方舟服务。
