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

模型别名与上游 ID 在 `backend/app/database.py` 中一一固定。管理员只为项目选择供应商渠道并启用模型，客户和管理员都不能在请求中改写上游模型 ID。

## 2026-09-04 验收记录

使用本地 `test_hb` 项目及其业务 Key 从客户视角发起真实请求，以上五个模型均返回 HTTP 200。真实用量合计 307 Tokens，供应商请求 ID 和分项用量保存在本地 `inference_usage` 中；文档、测试输出和 Git 变更均不保存业务 Key 或供应商凭证明文。

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
