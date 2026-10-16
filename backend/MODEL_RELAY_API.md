# 模型中转接入入口

客户公开接口统一见 [CLIENT_API.md](CLIENT_API.md)，或直接打开 [HTML 完整文档](CLIENT_API.html)。本页不再重复维护参数、模型清单和价格规则。

| 内容 | 入口 |
|---|---|
| 首次接入 | [快速开始](CLIENT_API.md#快速开始) |
| 全部模型对应接口 | [模型目录](docs/client-api/models.md#模型与接口对照表) |
| 模型价格与名称过滤 | [价格查询](docs/client-api/models.md#查询模型价格) |
| Chat / Responses / 视觉 / 翻译 | [文本接口](docs/client-api/text.md) |
| Seedream / GPT Image | [图片接口](docs/client-api/images.md) |
| Seedance / Wan / MiniMax | [视频接口](docs/client-api/videos.md) |
| 向量 | [向量接口](docs/client-api/embeddings.md) |
| TTS / ASR / 音频生成 | [音频接口](docs/client-api/audio.md) |
| 幂等、超时与错误 | [安全重试](docs/client-api/errors.md) |

视频画幅只使用 `ratio`，其余约束以视频接口参考为准。特定调用方 RichiDrama 的改造说明仍见 [RICHIDRAMA_RELAY_ALIGNMENT.md](RICHIDRAMA_RELAY_ALIGNMENT.md)，不得覆盖客户公开契约。
