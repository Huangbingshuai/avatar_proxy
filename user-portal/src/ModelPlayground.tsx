import {
  AudioLines,
  Bot,
  CheckCircle2,
  Clock3,
  Image as ImageIcon,
  KeyRound,
  LoaderCircle,
  MessageSquareText,
  Play,
  RefreshCw,
  Radio,
  Send,
  Sparkles,
  Square,
  Video,
  Network,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  getRelayVideoTask,
  getRelayTranscription,
  listRelayModels,
  testRelayImage,
  testRelayEmbedding,
  testRelaySpeech,
  testRelayTranscription,
  testRelayAudioGeneration,
  testRelayTranslation,
  testRelayTextStream,
  testRelayVideo,
  type RelayApiResult,
  type RelayModel,
} from "./api";

type PlaygroundResult = RelayApiResult & {
  elapsedMs: number;
  modality: RelayModel["modality"];
};

const ACTIVE_VIDEO_STATUSES = new Set([
  "queued",
  "pending",
  "running",
  "processing",
]);

function requestKey(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function textValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        const part = record(item);
        return typeof part.text === "string" ? part.text : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function responseText(body: Record<string, unknown>) {
  const choice = record(
    Array.isArray(body.choices) ? body.choices[0] : undefined,
  );
  const message = record(choice.message);
  const output = Array.isArray(body.output) ? body.output : [];
  const outputText = output
    .map((item) => {
      const value = record(item);
      return textValue(value.content) || textValue(value.text);
    })
    .filter(Boolean)
    .join("\n");
  return (
    textValue(message.content) ||
    textValue(message.reasoning_content) ||
    textValue(body.output_text) ||
    outputText ||
    "模型已返回响应，但没有可显示的文本内容。"
  );
}

function imageSource(body: Record<string, unknown>) {
  const item = record(Array.isArray(body.data) ? body.data[0] : undefined);
  if (typeof item.url === "string") return item.url;
  if (typeof item.b64_json === "string")
    return `data:image/png;base64,${item.b64_json}`;
  return "";
}

function taskId(body: Record<string, unknown>) {
  const value = body.id ?? body.task_id ?? body.taskId;
  return typeof value === "string" ? value : "";
}

function taskStatus(body: Record<string, unknown>) {
  const value = body.status;
  return typeof value === "string" ? value : "";
}

function usageItems(body: Record<string, unknown>) {
  const usage = record(body.usage);
  const labels: Record<string, string> = {
    prompt_tokens: "输入 tokens",
    completion_tokens: "输出 tokens",
    input_tokens: "输入 tokens",
    output_tokens: "输出 tokens",
    total_tokens: "总 tokens",
    generated_images: "生成图片",
    video_seconds: "视频秒数",
  };
  return Object.entries(labels).flatMap(([key, label]) => {
    const value = usage[key];
    return typeof value === "number" ? [{ label, value }] : [];
  });
}

function ModelIcon({ modality }: { modality: RelayModel["modality"] }) {
  if (modality === "image") return <ImageIcon size={19} />;
  if (modality === "video") return <Video size={19} />;
  if (modality === "embedding") return <Network size={19} />;
  if (modality === "audio") return <AudioLines size={19} />;
  return <MessageSquareText size={19} />;
}

export default function ModelPlayground({
  apiKey,
  apiKeyValid,
}: {
  apiKey: string;
  apiKeyValid: boolean;
}) {
  const [models, setModels] = useState<RelayModel[]>([]);
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [referenceImage, setReferenceImage] = useState("");
  const [duration, setDuration] = useState("5");
  const [sourceLanguage, setSourceLanguage] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("en");
  const [audioUrl, setAudioUrl] = useState("");
  const [voice, setVoice] = useState("zh_female_vv_uranus_bigtts");
  const [loadingModels, setLoadingModels] = useState(false);
  const [running, setRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const streamController = useRef<AbortController | null>(null);

  const selectedModel = useMemo(
    () => models.find((item) => item.id === modelId) ?? models[0],
    [modelId, models],
  );
  const isTranslation = selectedModel?.capabilities.translation === true;
  const supportsTextStream =
    selectedModel?.modality === "text" &&
    selectedModel.capabilities.stream === true;

  useEffect(() => {
    if (!apiKeyValid) return undefined;
    let disposed = false;
    async function load() {
      await Promise.resolve();
      if (disposed) return;
      setLoadingModels(true);
      setError("");
      try {
        const items = await listRelayModels(apiKey);
        if (disposed) return;
        setModels(items);
        setModelId((current) =>
          items.some((item) => item.id === current)
            ? current
            : items[0]?.id || "",
        );
      } catch (caught) {
        if (!disposed)
          setError(
            caught instanceof Error ? caught.message : "模型列表加载失败",
          );
      } finally {
        if (!disposed) setLoadingModels(false);
      }
    }
    void load();
    return () => {
      disposed = true;
    };
  }, [apiKey, apiKeyValid]);

  useEffect(() => () => streamController.current?.abort(), []);

  async function runTest() {
    if (!selectedModel) return setError("当前项目没有已启用的可用模型");
    const isTranscription = selectedModel.capabilities.transcriptions === true;
    if (!isTranscription && prompt.trim().length < 2)
      return setError("请输入至少两个字的测试提示词");
    if (isTranscription && !audioUrl.trim())
      return setError("请填写公网可访问的 HTTPS 音频 URL");
    if (
      selectedModel.modality === "video" &&
      selectedModel.capabilities.imageRequired === true &&
      !referenceImage.trim()
    ) {
      return setError("当前视频模型必须填写参考图片 URL");
    }
    setRunning(true);
    setError("");
    setResult(null);
    setStreamingText("");
    const startedAt = performance.now();
    const model = selectedModel;
    try {
      let response: RelayApiResult;
      if (model.modality === "text") {
        if (model.capabilities.translation === true) {
          response = await testRelayTranslation(
            apiKey,
            model.id,
            prompt.trim(),
            targetLanguage,
            sourceLanguage || undefined,
          );
        } else {
          const controller = new AbortController();
          streamController.current = controller;
          response = await testRelayTextStream(
            apiKey,
            model.id,
            prompt.trim(),
            {
              signal: controller.signal,
              image:
                model.capabilities.imageInput === true
                  ? referenceImage.trim() || undefined
                  : undefined,
              onDelta: (_delta, accumulated) => setStreamingText(accumulated),
            },
          );
        }
      } else if (model.modality === "image") {
        response = await testRelayImage(
          apiKey,
          model.id,
          prompt.trim(),
          requestKey("portal-image"),
          model.capabilities.imageInput === true
            ? referenceImage.trim() || undefined
            : undefined,
        );
      } else if (model.modality === "embedding") {
        response = await testRelayEmbedding(apiKey, model.id, prompt.trim());
      } else if (model.modality === "audio") {
        if (model.capabilities.speech === true) {
          response = await testRelaySpeech(
            apiKey,
            model.id,
            prompt.trim(),
            voice.trim(),
          );
        } else if (model.capabilities.transcriptions === true) {
          response = await testRelayTranscription(
            apiKey,
            model.id,
            audioUrl.trim(),
            requestKey("portal-asr"),
          );
        } else {
          response = await testRelayAudioGeneration(
            apiKey,
            model.id,
            prompt.trim(),
          );
        }
      } else {
        const parsedDuration = Number(duration);
        response = await testRelayVideo(
          apiKey,
          {
            model: model.id,
            prompt: prompt.trim(),
            image:
              model.capabilities.image === true
                ? referenceImage.trim() || undefined
                : undefined,
            duration: Number.isFinite(parsedDuration)
              ? parsedDuration
              : undefined,
          },
          requestKey("portal-video"),
        );
      }
      setResult({
        ...response,
        elapsedMs: Math.round(performance.now() - startedAt),
        modality: model.modality,
      });
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError("已停止本次流式生成");
      } else {
        setError(caught instanceof Error ? caught.message : "模型测试失败");
      }
    } finally {
      streamController.current = null;
      setRunning(false);
    }
  }

  function stopStream() {
    streamController.current?.abort();
  }

  async function refreshVideo() {
    const id = result ? taskId(result.body) : "";
    if (!id || !result) return;
    setRefreshing(true);
    setError("");
    const startedAt = performance.now();
    try {
      const response = await getRelayVideoTask(apiKey, id);
      setResult({
        ...response,
        elapsedMs: Math.round(performance.now() - startedAt),
        modality: "video",
      });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "视频任务状态刷新失败",
      );
    } finally {
      setRefreshing(false);
    }
  }

  async function refreshTranscription() {
    const id = result ? taskId(result.body) : "";
    if (!id || !result) return;
    setRefreshing(true);
    setError("");
    const startedAt = performance.now();
    try {
      const response = await getRelayTranscription(apiKey, id);
      setResult({
        ...response,
        elapsedMs: Math.round(performance.now() - startedAt),
        modality: "audio",
      });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "转写任务状态刷新失败",
      );
    } finally {
      setRefreshing(false);
    }
  }

  if (!apiKeyValid) {
    return (
      <section className="officialSection modelLabSection">
        <div className="officialEmpty">
          <KeyRound size={30} />
          <b>请先连接服务</b>
          <p>登录后即可用当前业务 Key 测试项目已启用的文本、图片和视频模型。</p>
        </div>
      </section>
    );
  }

  const usage = result ? usageItems(result.body) : [];
  const videoId = result ? taskId(result.body) : "";
  const videoStatus = result ? taskStatus(result.body) : "";
  const image = result?.modality === "image" ? imageSource(result.body) : "";
  const videoSupportsImage =
    selectedModel?.modality === "video" &&
    selectedModel.capabilities.image === true;
  const videoRequiresImage =
    videoSupportsImage && selectedModel.capabilities.imageRequired === true;
  const supportsReferenceImage =
    videoSupportsImage || selectedModel?.capabilities.imageInput === true;
  const isTranscription = selectedModel?.capabilities.transcriptions === true;
  const isSpeech = selectedModel?.capabilities.speech === true;
  const audioResultUrl =
    result?.modality === "audio"
      ? typeof result.body.audio_url === "string"
        ? result.body.audio_url
        : typeof record(
              Array.isArray(result.body.data) ? result.body.data[0] : undefined,
            ).url === "string"
          ? String(
              record(
                Array.isArray(result.body.data)
                  ? result.body.data[0]
                  : undefined,
              ).url,
            )
          : ""
      : "";
  const embeddingItem =
    result?.modality === "embedding"
      ? record(
          Array.isArray(result.body.data) ? result.body.data[0] : undefined,
        )
      : {};
  const embeddingVector = Array.isArray(embeddingItem.embedding)
    ? embeddingItem.embedding
    : [];

  return (
    <section
      className="officialSection modelLabSection"
      aria-labelledby="model-lab-title"
    >
      <div className="sectionTitleRow modelLabHeader">
        <div>
          <span className="modelLabEyebrow">
            <Sparkles size={13} />
            MODEL LAB
          </span>
          <h1 id="model-lab-title">模型在线测试</h1>
          <p>
            使用当前登录的业务 Key 发起真实中转请求，测试结果会计入该 Key
            的实际用量。
          </p>
        </div>
        <button
          type="button"
          className="secondaryButton"
          disabled={loadingModels}
          onClick={() => {
            setLoadingModels(true);
            setError("");
            void listRelayModels(apiKey)
              .then((items) => {
                setModels(items);
                setModelId((current) =>
                  items.some((item) => item.id === current)
                    ? current
                    : items[0]?.id || "",
                );
              })
              .catch((caught) =>
                setError(
                  caught instanceof Error ? caught.message : "模型列表加载失败",
                ),
              )
              .finally(() => setLoadingModels(false));
          }}
        >
          {loadingModels ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          刷新模型
        </button>
      </div>

      {error ? (
        <div className="modelLabError" role="alert">
          {error}
        </div>
      ) : null}
      {!loadingModels && !models.length ? (
        <div className="officialEmpty modelLabEmpty">
          <Bot size={30} />
          <b>当前项目暂无可测试模型</b>
          <p>请先在控制台为项目绑定可用渠道并启用模型。</p>
        </div>
      ) : null}

      {models.length ? (
        <div className="modelLabWorkbench">
          <div className="modelLabComposer">
            <div
              className="modelLabModelGrid"
              role="list"
              aria-label="可测试模型"
            >
              {models.map((model) => (
                <button
                  type="button"
                  disabled={running}
                  key={model.id}
                  className={selectedModel?.id === model.id ? "selected" : ""}
                  onClick={() => {
                    setModelId(model.id);
                    setResult(null);
                    setStreamingText("");
                    setError("");
                  }}
                >
                  <span className={model.modality}>
                    <ModelIcon modality={model.modality} />
                  </span>
                  <b>{model.id}</b>
                  <small>
                    {model.modality === "text"
                      ? model.capabilities.vision === true
                        ? "识图 / 对话"
                        : "文本对话"
                      : model.modality === "image"
                        ? model.capabilities.imageInput === true
                          ? "生图 / 改图"
                          : "图片生成"
                        : model.modality === "video"
                          ? "视频生成"
                          : model.modality === "embedding"
                            ? "多模态向量"
                            : model.capabilities.transcriptions === true
                              ? "录音识别"
                              : model.capabilities.speech === true
                                ? "语音合成"
                                : "音频生成"}
                  </small>
                  {selectedModel?.id === model.id ? (
                    <CheckCircle2 size={16} />
                  ) : null}
                </button>
              ))}
            </div>

            {!isTranscription ? (
              <div className="modelLabPrompt">
                <label htmlFor="model-test-prompt">测试提示词</label>
                <textarea
                  id="model-test-prompt"
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  maxLength={4000}
                  rows={6}
                  placeholder={
                    isTranslation
                      ? "输入需要翻译的文本"
                      : selectedModel?.capabilities.vision === true
                        ? "例如：请详细描述参考图片中的人物、场景和文字"
                        : selectedModel?.modality === "text"
                          ? "例如：用三句话介绍人工智能的实际用途"
                          : selectedModel?.modality === "embedding"
                            ? "输入需要向量化的文本"
                            : selectedModel?.modality === "audio"
                              ? isSpeech
                                ? "输入需要合成语音的文本"
                                : "描述想要生成的音乐、音效或声音"
                              : selectedModel?.modality === "image"
                                ? "例如：电影感产品摄影，暖色灯光，精致细节"
                                : "例如：海边日出，镜头缓慢向前推进"
                  }
                />
                <span>{prompt.length}/4000</span>
              </div>
            ) : null}

            {isTranscription ? (
              <div className="modelLabVideoFields">
                <label>
                  公网音频 URL（必填）
                  <input
                    type="url"
                    required
                    value={audioUrl}
                    onChange={(event) => setAudioUrl(event.target.value)}
                    placeholder="https://example.com/audio.mp3"
                  />
                </label>
              </div>
            ) : null}
            {isSpeech ? (
              <div className="modelLabVideoFields">
                <label>
                  TTS 2.0 音色 ID
                  <input
                    required
                    value={voice}
                    onChange={(event) => setVoice(event.target.value)}
                    placeholder="zh_female_vv_uranus_bigtts"
                  />
                </label>
              </div>
            ) : null}

            {isTranslation ? (
              <div className="modelLabVideoFields">
                <label>
                  源语言
                  <select
                    value={sourceLanguage}
                    onChange={(event) => setSourceLanguage(event.target.value)}
                  >
                    <option value="">自动识别</option>
                    <option value="zh">中文</option>
                    <option value="en">英语</option>
                    <option value="ja">日语</option>
                    <option value="ko">韩语</option>
                    <option value="fr">法语</option>
                    <option value="de">德语</option>
                    <option value="es">西班牙语</option>
                  </select>
                </label>
                <label>
                  目标语言
                  <select
                    value={targetLanguage}
                    onChange={(event) => setTargetLanguage(event.target.value)}
                  >
                    <option value="en">英语</option>
                    <option value="zh">中文</option>
                    <option value="ja">日语</option>
                    <option value="ko">韩语</option>
                    <option value="fr">法语</option>
                    <option value="de">德语</option>
                    <option value="es">西班牙语</option>
                  </select>
                </label>
              </div>
            ) : null}

            {supportsReferenceImage || selectedModel?.modality === "video" ? (
              <div className="modelLabVideoFields">
                {supportsReferenceImage ? (
                  <label>
                    参考图片 URL{videoRequiresImage ? "（必填）" : "（可选）"}
                    <input
                      type="url"
                      required={videoRequiresImage}
                      value={referenceImage}
                      onChange={(event) =>
                        setReferenceImage(event.target.value)
                      }
                      placeholder="https://..."
                    />
                  </label>
                ) : null}
                {selectedModel?.modality === "video" ? (
                  <label>
                    视频时长
                    <select
                      value={duration}
                      onChange={(event) => setDuration(event.target.value)}
                    >
                      <option value="5">5 秒</option>
                      <option value="8">8 秒</option>
                      <option value="10">10 秒</option>
                    </select>
                  </label>
                ) : null}
              </div>
            ) : null}

            <div className="modelLabSubmitRow">
              <span>
                <KeyRound size={14} />
                使用当前登录 Key，不会在页面显示完整密钥
                {supportsTextStream ? (
                  <em>
                    <Radio size={12} />
                    流式输出
                  </em>
                ) : isTranslation ? (
                  <em>Responses 翻译</em>
                ) : null}
              </span>
              <div className="modelLabActions">
                {running && supportsTextStream ? (
                  <button
                    type="button"
                    className="modelLabStopButton"
                    onClick={stopStream}
                  >
                    <Square size={13} fill="currentColor" />
                    停止生成
                  </button>
                ) : null}
                <button
                  type="button"
                  className="modelLabRunButton"
                  disabled={
                    running ||
                    !selectedModel ||
                    (!isTranscription && prompt.trim().length < 2) ||
                    (isTranscription && !audioUrl.trim()) ||
                    (isSpeech && !voice.trim()) ||
                    Boolean(videoRequiresImage && !referenceImage.trim())
                  }
                  onClick={() => void runTest()}
                >
                  {running ? (
                    <LoaderCircle size={17} className="spin" />
                  ) : (
                    <Send size={17} />
                  )}
                  {running
                    ? supportsTextStream
                      ? "正在流式生成"
                      : "正在调用模型"
                    : "发送真实测试"}
                </button>
              </div>
            </div>
          </div>

          <aside
            className={`modelLabResult ${result ? "hasResult" : ""}`}
            aria-live="polite"
          >
            {!result && !running ? (
              <div className="modelLabResultEmpty">
                <Play size={26} />
                <b>等待测试</b>
                <p>选择模型并输入提示词，响应会显示在这里。</p>
              </div>
            ) : null}
            {running && supportsTextStream ? (
              <>
                <header className="modelLabStreamingHeader">
                  <span>
                    <Radio size={16} />
                    实时生成中
                  </span>
                  <small>
                    {streamingText.length.toLocaleString("zh-CN")} 字符
                  </small>
                </header>
                <div className="modelLabTextResult streaming">
                  <MessageSquareText size={18} />
                  <p>
                    {streamingText || "正在等待模型返回首个内容片段…"}
                    <i className="modelLabTypingCursor" aria-hidden="true" />
                  </p>
                </div>
              </>
            ) : null}
            {running && !supportsTextStream ? (
              <div className="modelLabResultEmpty">
                <LoaderCircle size={28} className="spin" />
                <b>模型处理中</b>
                <p>
                  {isTranslation
                    ? "正在翻译文本，请稍候。"
                    : "图片和视频模型可能需要更长时间，请不要重复提交。"}
                </p>
              </div>
            ) : null}
            {result ? (
              <>
                <header>
                  <span>
                    <CheckCircle2 size={16} />
                    HTTP {result.status}
                  </span>
                  <small>
                    <Clock3 size={13} />
                    {result.elapsedMs.toLocaleString("zh-CN")} ms
                  </small>
                </header>
                {result.modality === "text" ? (
                  <div className="modelLabTextResult">
                    <MessageSquareText size={18} />
                    <p>{responseText(result.body)}</p>
                  </div>
                ) : null}
                {result.modality === "image" ? (
                  image ? (
                    <figure className="modelLabImageResult">
                      <img
                        src={image}
                        alt="模型生成结果"
                        referrerPolicy="no-referrer"
                      />
                      <figcaption>图片生成成功</figcaption>
                    </figure>
                  ) : (
                    <div className="modelLabTextResult">
                      <ImageIcon size={18} />
                      <p>请求成功，但响应中没有可显示的图片。</p>
                    </div>
                  )
                ) : null}
                {result.modality === "video" ? (
                  <div className="modelLabVideoResult">
                    <Video size={22} />
                    <div>
                      <b>{videoStatus || "任务已创建"}</b>
                      <code>{videoId || "未返回任务 ID"}</code>
                    </div>
                    {videoId &&
                    ACTIVE_VIDEO_STATUSES.has(videoStatus.toLowerCase()) ? (
                      <button
                        type="button"
                        className="secondaryButton"
                        disabled={refreshing}
                        onClick={() => void refreshVideo()}
                      >
                        {refreshing ? (
                          <LoaderCircle size={14} className="spin" />
                        ) : (
                          <RefreshCw size={14} />
                        )}
                        刷新状态
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {result.modality === "embedding" ? (
                  <div className="modelLabTextResult">
                    <Network size={18} />
                    <p>
                      向量生成成功：
                      {embeddingVector.length.toLocaleString("zh-CN")} 维<br />
                      前 8 项：
                      {embeddingVector
                        .slice(0, 8)
                        .map((value) => Number(value).toFixed(6))
                        .join(", ")}
                    </p>
                  </div>
                ) : null}
                {result.modality === "audio" ? (
                  <div className="modelLabVideoResult">
                    <AudioLines size={22} />
                    <div>
                      <b>
                        {typeof result.body.text === "string"
                          ? result.body.text
                          : videoStatus || "音频处理成功"}
                      </b>
                      <code>{videoId || result.requestId || "同步结果"}</code>
                    </div>
                    {audioResultUrl ? (
                      <audio controls src={audioResultUrl} />
                    ) : null}
                    {videoId &&
                    ACTIVE_VIDEO_STATUSES.has(videoStatus.toLowerCase()) ? (
                      <button
                        type="button"
                        className="secondaryButton"
                        disabled={refreshing}
                        onClick={() => void refreshTranscription()}
                      >
                        {refreshing ? (
                          <LoaderCircle size={14} className="spin" />
                        ) : (
                          <RefreshCw size={14} />
                        )}
                        刷新状态
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {usage.length ? (
                  <dl className="modelLabUsage">
                    {usage.map((item) => (
                      <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.value.toLocaleString("zh-CN")}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                {result.requestId ? (
                  <div className="modelLabRequestId">
                    <span>Request ID</span>
                    <code>{result.requestId}</code>
                  </div>
                ) : null}
              </>
            ) : null}
          </aside>
        </div>
      ) : null}
    </section>
  );
}
