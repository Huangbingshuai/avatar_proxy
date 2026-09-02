export const MODEL_ICON_ASSETS = {
  openai: "/model-icons/openai.svg",
  anthropic: "/model-icons/anthropic.svg",
  claude: "/model-icons/claude.svg",
  gemini: "/model-icons/gemini.svg",
  deepseek: "/model-icons/deepseek.svg",
  xai: "/model-icons/xai.svg",
  grok: "/model-icons/grok.svg",
  qwen: "/model-icons/qwen.svg",
  mistral: "/model-icons/mistral.svg",
  meta: "/model-icons/meta.svg",
  cohere: "/model-icons/cohere.svg",
  huggingface: "/model-icons/huggingface.svg",
  openrouter: "/model-icons/openrouter.svg",
  ollama: "/model-icons/ollama.svg",
  groq: "/model-icons/groq.svg",
  perplexity: "/model-icons/perplexity.svg",
  bailian: "/model-icons/bailian.svg",
  alibabaCloud: "/model-icons/alibaba-cloud.svg",
  chatglm: "/model-icons/chatglm.svg",
  zhipu: "/model-icons/zhipu.svg",
  doubao: "/model-icons/doubao.svg",
  volcengine: "/model-icons/volcengine.svg",
  minimax: "/model-icons/minimax.svg",
  moonshot: "/model-icons/moonshot.svg",
  kimi: "/model-icons/kimi.svg",
  wenxin: "/model-icons/wenxin.svg",
  baidu: "/model-icons/baidu.svg",
  hunyuan: "/model-icons/hunyuan.svg",
  tencentCloud: "/model-icons/tencent-cloud.svg",
  stepfun: "/model-icons/stepfun.svg",
  baichuan: "/model-icons/baichuan.svg",
  yi: "/model-icons/yi.svg",
  siliconCloud: "/model-icons/silicon-cloud.svg",
  midjourney: "/model-icons/midjourney.svg",
  stabilityAi: "/model-icons/stability-ai.svg",
  flux: "/model-icons/flux.svg",
  ideogram: "/model-icons/ideogram.svg",
  recraft: "/model-icons/recraft.svg",
  runway: "/model-icons/runway.svg",
  luma: "/model-icons/luma.svg",
  kling: "/model-icons/kling.svg",
  hailuo: "/model-icons/hailuo.svg",
  sora: "/model-icons/sora.svg",
  pixverse: "/model-icons/pixverse.svg",
  pika: "/model-icons/pika.svg",
  vidu: "/model-icons/vidu.svg",
  fal: "/model-icons/fal.svg",
  elevenlabs: "/model-icons/elevenlabs.svg",
  fishAudio: "/model-icons/fish-audio.svg",
} as const;

export type ModelIconKey = keyof typeof MODEL_ICON_ASSETS;

const MODEL_ICON_OVERRIDES: Record<string, ModelIconKey> = {
  "image2.0": "openai",
  "gpt-image-2": "openai",
  "seedream-5.0-pro": "doubao",
  "doubao-seedream-5-0-260128": "doubao",
  "deepseek-v4-flash": "deepseek",
  "glm-5.2": "chatglm",
  "minimax-h3": "minimax",
  "wan3.0-video": "bailian",
};

const PROVIDER_ICON_KEYS: Record<string, ModelIconKey> = {
  openai: "openai",
  anthropic: "anthropic",
  google: "gemini",
  google_vertex: "gemini",
  xai: "xai",
  deepseek: "deepseek",
  aliyun_bailian: "bailian",
  alibaba_cloud: "alibabaCloud",
  zhipu: "zhipu",
  volcengine_ark: "volcengine",
  bytedance: "doubao",
  minimax: "minimax",
  moonshot: "moonshot",
  baidu: "baidu",
  tencent: "tencentCloud",
  mistral: "mistral",
  meta: "meta",
  cohere: "cohere",
  openrouter: "openrouter",
  groq: "groq",
  perplexity: "perplexity",
  silicon_cloud: "siliconCloud",
  fal: "fal",
};

const MODEL_PREFIX_ICONS: Array<[string, ModelIconKey]> = [
  ["seedream", "doubao"], ["seedance", "doubao"], ["doubao", "doubao"],
  ["deepseek", "deepseek"], ["glm", "chatglm"], ["chatglm", "chatglm"],
  ["minimax", "minimax"], ["wan", "bailian"], ["qwen", "qwen"],
  ["claude", "claude"], ["gemini", "gemini"], ["veo", "gemini"],
  ["grok", "grok"], ["llama", "meta"], ["mistral", "mistral"],
  ["kimi", "kimi"], ["moonshot", "moonshot"], ["ernie", "wenxin"],
  ["wenxin", "wenxin"], ["hunyuan", "hunyuan"], ["stepfun", "stepfun"],
  ["baichuan", "baichuan"], ["yi-", "yi"], ["midjourney", "midjourney"],
  ["stable-diffusion", "stabilityAi"], ["sdxl", "stabilityAi"], ["flux", "flux"],
  ["ideogram", "ideogram"], ["recraft", "recraft"], ["runway", "runway"],
  ["luma", "luma"], ["kling", "kling"], ["hailuo", "hailuo"],
  ["sora", "sora"], ["pixverse", "pixverse"], ["pika", "pika"],
  ["vidu", "vidu"], ["elevenlabs", "elevenlabs"], ["fish-audio", "fishAudio"],
  ["gpt", "openai"], ["o1", "openai"], ["o3", "openai"], ["o4", "openai"],
];

export function getProviderIconPath(provider: string): string | undefined {
  const key = PROVIDER_ICON_KEYS[provider.trim().toLowerCase()];
  return key ? MODEL_ICON_ASSETS[key] : undefined;
}

export function getModelIconPath(model: string, provider?: string): string | undefined {
  const normalized = model.trim().toLowerCase();
  const exactKey = MODEL_ICON_OVERRIDES[normalized];
  if (exactKey) return MODEL_ICON_ASSETS[exactKey];
  const prefixMatch = MODEL_PREFIX_ICONS.find(([prefix]) => normalized.startsWith(prefix));
  if (prefixMatch) return MODEL_ICON_ASSETS[prefixMatch[1]];
  return provider ? getProviderIconPath(provider) : undefined;
}
