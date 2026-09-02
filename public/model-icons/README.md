# 本地模型图标库

这里保存控制台可直接使用的 AI 模型及供应商品牌 SVG。资源从项目锁定的
`@lobehub/icons-static-svg@1.94.0` 中复制，页面运行时不请求第三方 CDN。

- 上游项目：https://github.com/lobehub/lobe-icons
- 上游许可：MIT
- 当前数量：49 个 SVG
- 代码索引：`app/model-icon-library.ts`

## 覆盖范围

- 通用模型：OpenAI、Claude/Anthropic、Gemini、DeepSeek、Grok/xAI、Qwen、Mistral、Meta、Cohere 等。
- 国内模型：百炼、GLM/智谱、豆包/火山、MiniMax、Kimi/月之暗面、文心、混元、阶跃、百川、Yi 等。
- 图片和视频：Midjourney、Stability AI、Flux、Ideogram、Recraft、Runway、Luma、可灵、海螺、Sora、PixVerse、Pika、Vidu 等。
- 音频：ElevenLabs、Fish Audio。

## 模型别名约定

模型自身没有独立品牌图标时使用所属模型家族或供应商图标：

- Seedream、Seedance → 豆包
- Wan → 阿里百炼
- Veo → Gemini
- Llama → Meta
- GLM → ChatGLM
- Image 2.0、GPT Image → OpenAI

新增模型时，优先在 `MODEL_ICON_OVERRIDES` 增加精确映射；同一系列模型较多时，
再向 `MODEL_PREFIX_ICONS` 增加前缀映射。不要在业务组件里重复导入 SVG。

图标仅用于识别对应品牌或产品，相关商标权归各自所有者。
