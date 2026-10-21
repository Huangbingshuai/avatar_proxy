# 客户 API 文档工具

## 内容来源

`backend/CLIENT_API.md` 是客户入口，`backend/docs/client-api/` 是接口参考。左侧按供应商组织，每个模型条目展示适用的示例、参数和结果；11 项素材接口归入“火山引擎 → 素材接口”，按操作独立展示。独立文件 `backend/CLIENT_API.html` 与控制台的 `public/docs/client-api.html` 必须字节一致。

`models.json` 仅保存公开模型名称、类型和静态能力，不含真实上游 ID 或凭证。`model-guides.mjs` 与已有通用参考生成 48 个供应商/模型页，同时生成 Markdown 阅读版 `backend/docs/client-api/model-reference.md`；不要手工修改生成文件。新增模型时同步更新模型元数据，契约测试会校验模型别名覆盖。素材操作从 `assets.md` 的独立章节生成，不维护第二份参数。

## 设计参考

2026-10-16 调研的文档：

| 来源 | 采用的组织方式 |
|---|---|
| [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart) | 从最小请求开始，再引导到模型、能力及接口参考 |
| [SiliconFlow Quickstart](https://docs.siliconflow.cn/docs/userguide/quickstart) | 使用指南与 API 参考分层，按文本、图片、视频和音频分类 |
| [New API Chat 文档](https://doc.newapi.pro/api/openai-chat/) | 将端点、请求示例、参数与响应集中在能力章节中 |
| [OpenRouter 错误处理](https://openrouter.ai/docs/api_reference/errors-and-debugging) | 区分 HTTP 错误和流式响应开始之后的错误 |
| [用户指定的 Apifox 参考页](https://bu5j51zafx.apifox.cn/436644314e0) | 最终阅读页采用分组树、独立操作、方法标签、参数和请求/响应分区；不复制其接口契约 |

这里只借鉴文档组织，不引入其他平台的接口、字段或可用性承诺。星辰平台实际路径、字段白名单、项目鉴权及供应商能力以本仓库代码和文档契约测试为准。客户文档不包含部署记录、付费验收数据或管理接口。

## 生成与检查

在仓库根目录执行：

```bash
npm ci --prefix tools/client-docs
npm run docs:build
npm run docs:check
npm run docs:test
```

阅读器测试使用根项目已有的 `jsdom`；首次使用也需安装根项目开发依赖。Markdown 渲染使用此目录锁定的 `marked`，不作为控制台或 API 运行时依赖。

构建会验证所有文档中的相对链接及锚点，拒绝不在文档集合内的链接和任意原始 HTML（表格换行 `<br>` 除外）。代码示例全部转义；单条 JSON curl 请求同时生成 JavaScript 和 Python 示例，multipart 上传保留 Shell 示例。输出内嵌样式、全文搜索和阅读脚本，不依赖 CDN，不联网读取 Markdown，也没有发送 API 请求或填写真实 Key 的功能。

控制台使用不授予同源权限的沙箱 iframe 加载静态 HTML，并提供独立窗口和下载。打印输出包含全部章节。修改 Markdown、阅读器或样式后均须重新生成；构建一致性测试会阻止遗忘更新任一 HTML 副本。

构建同时更新 `app/client-docs-manifest.ts`，以 HTML 内容哈希生成控制台文档 URL 的版本参数，避免升级后继续读取浏览器缓存中的旧标题或内容。

文档页左上角使用 `ruichi-logo.png`（用户提供的瑞池传媒原图）。构建时将图片内嵌为 PNG Data URL，保持原比例完整显示；独立下载、沙箱 iframe 和离线打开均不额外请求图片。更换此图片后也须重新生成两份 HTML 和版本清单。

`supplier-guides.mjs` 将 43 个模型整理为 7 个供应商、48 个“供应商/模型”条目；同名模型可以分别出现在不同供应商下面，不再增加渠道对照或隔离层。内容仍复用公共模板，参数能力按实际供应商适配。请求中不增加渠道字段；读者通过 `/v1/pricing` 中同名项的 `provider` 确认当前供应商。契约测试会逐条核对供应商和能力并回放示例；素材示例覆盖全部 11 项操作，供应商、TOS 均使用模拟实现。

额外契约检查：在 `backend` 中运行 `python -m pytest tests/test_public_docs_contract.py`，覆盖模型清单、路由与方法、字段白名单、JSON/curl 示例、跨文件链接和敏感信息边界。不使用真实供应商，不产生费用。
