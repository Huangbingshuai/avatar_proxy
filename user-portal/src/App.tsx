import {
  ArrowLeft,
  ArrowUp,
  AtSign,
  BarChart3,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock3,
  Download,
  Eye,
  EyeOff,
  Image as ImageIcon,
  KeyRound,
  Layers3,
  LoaderCircle,
  LogOut,
  MessageCirclePlus,
  PauseCircle,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Trash2,
  Video,
  WandSparkles,
  X,
} from "lucide-react";
import { type FormEvent, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import AssetLibrary from "./AssetLibrary";
import type { AssetPromptEditorHandle, AssetPromptValue } from "./AssetPromptEditor";
import {
  DEFAULT_MODEL,
  VIDEO_MODELS,
  assetUri,
  authenticateApiKey,
  cancelVideoTask,
  clearVideoHistory,
  generateVideo,
  getArkVideoUsage,
  getLastFrameUrl,
  getVideoHistory,
  getVideoTask,
  getVideoUsage,
  getVideoUrl,
  importVideoHistory,
  isAssetActive,
  removeVideoHistoryTask,
  type Asset,
  type ArkUsageStats,
  type VideoTask,
  type UsageStats,
} from "./api";

type Workspace = "create" | "library" | "tasks" | "usage";
type BusyAction = "generate" | "query" | "cancel" | null;
type TaskAsset = Pick<Asset, "id" | "groupId" | "name" | "status" | "previewUrl">;

type TaskRecord = {
  id: string;
  createdAt: number;
  prompt: string;
  promptDocument?: string;
  assetName?: string;
  assetNames?: string[];
  assets?: TaskAsset[];
  model?: string;
  ratio?: string;
  duration?: number;
  durationMode?: "seconds" | "smart";
  resolution?: string;
  generationCount?: number;
  generateAudio?: boolean;
  status?: string;
  videoUrl?: string;
  lastFrameUrl?: string;
};

const AssetPromptEditor = lazy(() => import("./AssetPromptEditor"));
const SESSION_KEY = "avatar-studio:api-key";
const HISTORY_PREFIX = "avatar-studio:task-ids:v2";
const ACTIVE_STATUSES = new Set(["queued", "pending", "running", "processing"]);
const SUCCESS_STATUSES = new Set(["succeeded", "success", "completed", "done"]);
const FAILED_STATUSES = new Set(["failed", "error"]);
const TASK_REFRESH_BATCH_SIZE = 4;
const RATIO_OPTIONS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"] as const;
const RESOLUTION_OPTIONS = ["480p", "720p", "1080p", "4k"] as const;
const DURATION_OPTIONS = Array.from({ length: 12 }, (_, index) => index + 4);

const workspaceItems: Array<{ id: Workspace; label: string; icon: typeof WandSparkles }> = [
  { id: "create", label: "视频生成", icon: WandSparkles },
  { id: "library", label: "素材库", icon: Layers3 },
  { id: "tasks", label: "任务记录", icon: Clock3 },
  { id: "usage", label: "用量统计", icon: BarChart3 },
];

function compactTokens(value: number) {
  if (value >= 10000) return `${(value / 10000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}万`;
  return value.toLocaleString("zh-CN");
}

function shortDate(value: string) {
  const [, month, day] = value.split("-");
  return `${month}/${day}`;
}

function dateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultArkUsageStart() {
  const value = new Date();
  value.setDate(value.getDate() - 13);
  return dateInputValue(value);
}

function UsagePanel({ apiKey, apiKeyValid }: { apiKey: string; apiKeyValid: boolean }) {
  const [days, setDays] = useState(14);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [arkApiKey, setArkApiKey] = useState("");
  const [showArkApiKey, setShowArkApiKey] = useState(false);
  const [arkStart, setArkStart] = useState(defaultArkUsageStart);
  const [arkEnd, setArkEnd] = useState(() => dateInputValue(new Date()));
  const [arkInterval, setArkInterval] = useState<"Day" | "Hour">("Day");
  const [arkUsage, setArkUsage] = useState<ArkUsageStats | null>(null);
  const [arkLoading, setArkLoading] = useState(false);
  const [arkError, setArkError] = useState("");

  useEffect(() => {
    if (!apiKeyValid) return undefined;
    let disposed = false;
    async function loadUsage() {
      await Promise.resolve();
      if (disposed) return;
      setUsage(null);
      setLoading(true);
      setLoadError("");
      try {
        const result = await getVideoUsage(apiKey, days);
        if (!disposed) setUsage(result);
      } catch (caught) {
        if (!disposed) setLoadError(caught instanceof Error ? caught.message : "用量加载失败");
      } finally {
        if (!disposed) setLoading(false);
      }
    }
    void loadUsage();
    return () => { disposed = true; };
  }, [apiKey, apiKeyValid, days, refreshToken]);

  async function queryArkUsage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = arkApiKey.trim();
    setArkError("");
    setArkUsage(null);
    if (!key) {
      setArkError("请输入火山方舟 API Key");
      return;
    }
    if (!arkStart || !arkEnd || arkEnd < arkStart) {
      setArkError("请选择有效的开始和结束日期");
      return;
    }
    const rangeDays = Math.round((Date.parse(arkEnd) - Date.parse(arkStart)) / 86_400_000);
    if (rangeDays > 31) {
      setArkError("单次最多查询 31 天");
      return;
    }
    setArkLoading(true);
    try {
      setArkUsage(await getArkVideoUsage(key, arkStart, arkEnd, arkInterval));
    } catch (caught) {
      setArkError(caught instanceof Error ? caught.message : "方舟用量查询失败");
    } finally {
      setArkLoading(false);
    }
  }

  if (!apiKeyValid) return <div className="officialEmpty usageLocked"><KeyRound size={28} /><b>请先连接服务</b><p>输入业务 API Key 后，仅显示这个 Key 的视频生成用量。</p></div>;

  const summary = usage?.summary || { inputTokens: 0, outputTokens: 0, totalTokens: 0, requestCount: 0 };
  const daily = usage?.daily || [];
  const maxTokens = Math.max(1, ...daily.map((item) => item.totalTokens));
  const range = daily.length ? `${daily[0].date} — ${daily[daily.length - 1].date}` : "正在读取统计区间";

  return <section className="usageWorkspace" aria-labelledby="usage-title">
    <div className="usageHeader">
      <div><span className="usageEyebrow">CURRENT API KEY</span><h1 id="usage-title">用量统计</h1><p>按视频任务去重统计，任务完成并刷新状态后更新 token 用量。</p></div>
      <div className="usageControls"><span className="usageRange">{range}</span><div className="usagePeriod" aria-label="统计周期">{[7, 14, 30].map((value) => <button key={value} type="button" className={days === value ? "active" : ""} onClick={() => setDays(value)}>{value}天</button>)}</div><button type="button" className="usageRefresh" disabled={loading} onClick={() => setRefreshToken((value) => value + 1)} aria-label="刷新用量">{loading ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}</button></div>
    </div>
    {loadError ? <div className="officialMessage error" role="alert"><CircleAlert size={17} /><span>{loadError}</span></div> : null}
    <div className="usageCard">
      <div className="usageMetrics">
        <article className="usageMetric primaryMetric"><span>调用总量 tokens</span><strong>{compactTokens(summary.totalTokens)}</strong></article>
        <article className="usageMetric"><span>输出 tokens</span><strong>{compactTokens(summary.outputTokens)}</strong></article>
        <article className="usageMetric"><span>调用次数</span><strong>{summary.requestCount.toLocaleString("zh-CN")}</strong></article>
      </div>
      <div className="usageChartHead"><span>单位：tokens</span><span><i />每日用量</span></div>
      <div className="usageChart" role="img" aria-label={`${days}天 token 用量柱状图`}>
        <div className="usageGridLines" aria-hidden="true"><i /><i /><i /><i /></div>
        <div className="usageBars">{daily.map((item, index) => {
          const height = item.totalTokens ? Math.max(4, item.totalTokens / maxTokens * 100) : 0;
          const showLabel = days <= 14 || index % 3 === 0 || index === daily.length - 1;
          return <div className="usageBarSlot" key={item.date} title={`${item.date}：${item.totalTokens.toLocaleString("zh-CN")} tokens`}><div className="usageBarTrack"><span style={{ height: `${height}%` }} /></div><small>{showLabel ? shortDate(item.date) : ""}</small></div>;
        })}</div>
      </div>
      {!loading && summary.requestCount === 0 ? <div className="usageEmptyNote"><BarChart3 size={18} /><span>这个周期还没有视频生成记录；创建任务后会从这里开始累计。</span></div> : null}
    </div>
    <section className="arkUsageCard" aria-labelledby="ark-usage-title">
      <div className="arkUsageHeading">
        <div><span className="usageEyebrow">VOLCENGINE ARK</span><h2 id="ark-usage-title">查询火山方舟 Key 用量</h2><p>查询这个方舟 Key 直接调用 Seedance 产生的聚合用量，与上方业务 Key 统计相互独立。</p></div>
        <span className="arkPrivacyBadge"><ShieldCheck size={15} />仅随本次请求发送</span>
      </div>
      <form className="arkUsageForm" onSubmit={queryArkUsage}>
        <label className="arkKeyField"><span>方舟 API Key</span><div><input type={showArkApiKey ? "text" : "password"} value={arkApiKey} onChange={(event) => setArkApiKey(event.target.value)} placeholder="请输入客户自己的方舟 API Key" autoComplete="off" spellCheck={false} aria-describedby="ark-key-security" /><button type="button" onClick={() => setShowArkApiKey((value) => !value)} aria-label={showArkApiKey ? "隐藏方舟 API Key" : "显示方舟 API Key"}>{showArkApiKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
        <label><span>开始日期</span><input type="date" value={arkStart} max={arkEnd} onChange={(event) => setArkStart(event.target.value)} /></label>
        <label><span>结束日期</span><input type="date" value={arkEnd} min={arkStart} onChange={(event) => setArkEnd(event.target.value)} /></label>
        <label><span>统计粒度</span><select value={arkInterval} onChange={(event) => setArkInterval(event.target.value as "Day" | "Hour")}><option value="Day">按天</option><option value="Hour">按小时</option></select></label>
        <button className="primaryButton arkUsageSubmit" type="submit" disabled={arkLoading}>{arkLoading ? <LoaderCircle size={16} className="spin" /> : <BarChart3 size={16} />}{arkLoading ? "查询中" : "查询用量"}</button>
      </form>
      <p className="arkSecurityNote" id="ark-key-security"><KeyRound size={14} />完整 Key 不会写入浏览器存储或本系统数据库；响应只显示末 12 位。聚合数据通常延迟 5～30 分钟，且不包含人民币账单金额。</p>
      {arkError ? <div className="officialMessage error" role="alert"><CircleAlert size={17} /><span>{arkError}</span></div> : null}
      {arkUsage ? <div className="arkUsageResult">
        <div className="arkUsageResultHead"><div><span>查询结果</span><strong>Key ····{arkUsage.keySuffix}</strong></div><span>{arkUsage.start} — {arkUsage.end} · {arkUsage.interval === "Day" ? "按天" : "按小时"}</span></div>
        <div className="arkUsageMetrics">
          <article><span>总 tokens</span><strong>{compactTokens(arkUsage.summary.totalTokens)}</strong></article>
          <article><span>输出 tokens</span><strong>{compactTokens(arkUsage.summary.outputTokens)}</strong></article>
          <article><span>输入 tokens</span><strong>{compactTokens(arkUsage.summary.inputTokens)}</strong></article>
          <article><span>调用次数</span><strong>{arkUsage.summary.requestCount.toLocaleString("zh-CN")}</strong></article>
        </div>
        {arkUsage.records.length ? <div className="arkUsageTableWrap"><table className="arkUsageTable"><thead><tr><th>时间</th><th>Seedance 模型</th><th>接入点</th><th>调用次数</th><th>总 tokens</th></tr></thead><tbody>{arkUsage.records.map((record, index) => <tr key={`${record.date || "unknown"}-${record.modelName}-${record.endpointId || index}`}><td>{record.date || "—"}</td><td>{record.modelName}</td><td>{record.endpointId || "—"}</td><td>{record.requestCount.toLocaleString("zh-CN")}</td><td>{record.totalTokens.toLocaleString("zh-CN")}</td></tr>)}</tbody></table></div> : <div className="usageEmptyNote arkUsageEmpty"><BarChart3 size={18} /><span>查询区间内没有匹配到这个 Key 的 Seedance 聚合用量。</span></div>}
      </div> : null}
    </section>
  </section>;
}

function readTaskAssets(value: unknown): TaskAsset[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const assets = value.flatMap((item): TaskAsset[] => {
    if (!item || typeof item !== "object" || !("id" in item) || typeof item.id !== "string") return [];
    const asset = item as Partial<TaskAsset> & { id: string };
    return [{
      id: asset.id,
      groupId: typeof asset.groupId === "string" ? asset.groupId : "",
      name: typeof asset.name === "string" ? asset.name : "参考素材",
      status: typeof asset.status === "string" ? asset.status : "Active",
      previewUrl: typeof asset.previewUrl === "string" ? asset.previewUrl : "",
    }];
  });
  return assets.length ? assets : undefined;
}

function apiKeyFingerprint(apiKey: string) {
  let hash = 2166136261;
  for (let index = 0; index < apiKey.length; index += 1) {
    hash ^= apiKey.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function taskHistoryKey(apiKey: string) {
  return `${HISTORY_PREFIX}:${apiKeyFingerprint(apiKey)}`;
}

function readTaskHistory(apiKey: string): TaskRecord[] {
  if (!apiKey) return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(taskHistoryKey(apiKey)) || "[]") as unknown;
    const source = Array.isArray(parsed)
      ? parsed
      : parsed && typeof parsed === "object" && "items" in parsed && Array.isArray(parsed.items)
        ? parsed.items
        : [];
    return source.flatMap((item): TaskRecord[] => {
      if (typeof item === "string") return [{ id: item, createdAt: 0, prompt: "历史视频任务" }];
      if (!item || typeof item !== "object" || !("id" in item) || typeof item.id !== "string") return [];
      const record = item as Partial<TaskRecord> & { id: string };
      return [{
        id: record.id,
        createdAt: typeof record.createdAt === "number" ? record.createdAt : 0,
        prompt: typeof record.prompt === "string" && record.prompt ? record.prompt : "历史视频任务",
        promptDocument: typeof record.promptDocument === "string" ? record.promptDocument : undefined,
        assetName: typeof record.assetName === "string" ? record.assetName : undefined,
        assetNames: Array.isArray(record.assetNames) ? record.assetNames.filter((name): name is string => typeof name === "string") : undefined,
        assets: readTaskAssets(record.assets),
        model: typeof record.model === "string" ? record.model : undefined,
        ratio: typeof record.ratio === "string" ? record.ratio : undefined,
        duration: typeof record.duration === "number" ? record.duration : undefined,
        durationMode: record.durationMode === "smart" ? "smart" : "seconds",
        resolution: typeof record.resolution === "string" ? record.resolution : undefined,
        generationCount: typeof record.generationCount === "number" ? record.generationCount : undefined,
        generateAudio: typeof record.generateAudio === "boolean" ? record.generateAudio : undefined,
        status: typeof record.status === "string" ? record.status : undefined,
        videoUrl: typeof record.videoUrl === "string" ? record.videoUrl : undefined,
        lastFrameUrl: typeof record.lastFrameUrl === "string" ? record.lastFrameUrl : undefined,
      }];
    }).slice(0, 20);
  } catch {
    return [];
  }
}

async function loadPersistentTaskHistory(apiKey: string) {
  const cached = readTaskHistory(apiKey);
  if (cached.length) await importVideoHistory(cached, apiKey);
  try {
    const response = await getVideoHistory(apiKey);
    return response.tasks as TaskRecord[];
  } catch {
    return cached;
  }
}

function taskLabel(status?: string) {
  const value = status?.toLowerCase() || "idle";
  if (value === "queued" || value === "pending") return "排队中";
  if (value === "running" || value === "processing") return "生成中";
  if (SUCCESS_STATUSES.has(value)) return "已完成";
  if (FAILED_STATUSES.has(value)) return "生成失败";
  if (value === "cancelled" || value === "canceled") return "已取消";
  return status || "等待查询";
}

function taskTone(status?: string) {
  const value = status?.toLowerCase() || "";
  if (SUCCESS_STATUSES.has(value)) return "success";
  if (FAILED_STATUSES.has(value)) return "error";
  if (ACTIVE_STATUSES.has(value)) return "active";
  return "muted";
}

function progressFor(status?: string, serverProgress?: number) {
  if (typeof serverProgress === "number") {
    return Math.max(0, Math.min(100, serverProgress <= 1 ? serverProgress * 100 : serverProgress));
  }
  const value = status?.toLowerCase();
  if (value === "queued" || value === "pending") return 22;
  if (value === "running" || value === "processing") return 68;
  if (value && (SUCCESS_STATUSES.has(value) || FAILED_STATUSES.has(value))) return 100;
  return 0;
}

function formatTaskTime(value: number, withDate = false) {
  if (!value) return "较早创建";
  return new Intl.DateTimeFormat("zh-CN", withDate
    ? { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }
    : { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function modelLabel(model?: string) {
  const id = model || DEFAULT_MODEL;
  return VIDEO_MODELS.find((item) => item.id === id)?.label || id;
}

function ModelPicker({ value, onChange, onOpen }: {
  value: string;
  onChange: (value: string) => void;
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function closeOnOutside(event: PointerEvent) {
      if (!pickerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return <div className={`modelPicker ${open ? "open" : ""}`} ref={pickerRef}>
    <button type="button" className="modelPickerTrigger" aria-label="选择视频模型" aria-haspopup="listbox" aria-expanded={open} onClick={() => {
      setOpen((current) => {
        if (!current) onOpen?.();
        return !current;
      });
    }}><Video size={15} /><span>{modelLabel(value)}</span><ChevronDown size={13} /></button>
    {open ? <div className="modelPickerMenu" role="listbox" aria-label="视频模型列表">
      <span className="modelPickerTitle">选择视频模型</span>
      {VIDEO_MODELS.map((option) => <button key={option.id} type="button" role="option" aria-selected={value === option.id} className={value === option.id ? "selected" : ""} onClick={() => { onChange(option.id); setOpen(false); }}><span><b>{option.label}</b><small>{option.id}</small></span>{value === option.id ? <Check size={15} /> : null}</button>)}
    </div> : null}
  </div>;
}

async function fetchTaskStatuses(ids: string[], apiKey: string) {
  const results: PromiseSettledResult<VideoTask>[] = [];
  for (let index = 0; index < ids.length; index += TASK_REFRESH_BATCH_SIZE) {
    const batch = ids.slice(index, index + TASK_REFRESH_BATCH_SIZE);
    results.push(...await Promise.allSettled(batch.map((id) => getVideoTask(id, apiKey))));
  }
  return results;
}

function StatusBadge({ status }: { status?: string }) {
  const tone = taskTone(status);
  return (
    <span className={`officialStatus ${tone}`}>
      {tone === "active" ? <LoaderCircle size={13} className="spin" /> : null}
      {tone === "success" ? <CircleCheck size={13} /> : null}
      {tone === "error" ? <CircleAlert size={13} /> : null}
      {taskLabel(status)}
    </span>
  );
}

function PromptWithMentions({ text }: { text: string }) {
  return <>{text.split(/(图片\d+)/g).map((part, index) => /^图片\d+$/.test(part)
    ? <span className="inlineMention" key={`${part}-${index}`}>@{part}</span>
    : <span key={`${part}-${index}`}>{part}</span>)}</>;
}

function ResultPanel({ task, busy, onRefresh, onCancel }: {
  task: VideoTask | null;
  busy: BusyAction;
  onRefresh: (id: string) => void;
  onCancel: () => void;
}) {
  if (!task) return null;
  const outputUrl = getVideoUrl(task);
  const lastFrameUrl = getLastFrameUrl(task);
  const active = ACTIVE_STATUSES.has(task.status.toLowerCase());
  const progress = progressFor(task.status, task.progress);
  return (
    <section className="resultPanel" aria-labelledby="result-title">
      <div className="sectionTitleRow">
        <div><h2 id="result-title">生成结果</h2><p>任务状态会自动刷新，完成后可直接预览和下载。</p></div>
        <StatusBadge status={task.status} />
      </div>
      <div className="resultContent">
        <div className="officialPreview">
          {outputUrl ? <video src={outputUrl} controls playsInline preload="metadata" poster={lastFrameUrl || undefined} /> : <div className="officialPreviewEmpty">{active ? <LoaderCircle size={32} className="spin" /> : <Video size={32} />}<b>{taskLabel(task.status)}</b><span>{active ? "正在生成视频，请稍候" : "暂时没有可预览的视频"}</span></div>}
        </div>
        <div className="resultMeta">
          <div className="progressHeader"><span>{taskLabel(task.status)}</span><b>{Math.round(progress)}%</b></div>
          <div className={`progressTrack ${active ? "isMoving" : ""}`}><span style={{ width: `${progress}%` }} /></div>
          {task.error ? <div className="taskError"><CircleAlert size={16} /><span><b>{task.error.code || "生成失败"}</b>{task.error.message || "请检查输入内容后重试。"}</span></div> : null}
          <div className="taskActions">
            <button type="button" className="secondaryButton" disabled={busy === "query"} onClick={() => onRefresh(task.id)}>{busy === "query" ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}刷新</button>
            {active ? <button type="button" className="dangerButton" disabled={busy === "cancel"} onClick={onCancel}>{busy === "cancel" ? <LoaderCircle size={15} className="spin" /> : <PauseCircle size={15} />}取消任务</button> : null}
            {outputUrl ? <a className="downloadButton" href={outputUrl} download target="_blank" rel="noreferrer"><Download size={15} />下载视频</a> : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function VideoSettingsPanel({
  ratio,
  resolution,
  duration,
  durationMode,
  generateAudio,
  generationCount,
  onRatioChange,
  onResolutionChange,
  onDurationChange,
  onDurationModeChange,
  onAudioChange,
  onGenerationCountChange,
}: {
  ratio: string;
  resolution: string;
  duration: number;
  durationMode: "seconds" | "smart";
  generateAudio: boolean;
  generationCount: number;
  onRatioChange: (value: string) => void;
  onResolutionChange: (value: string) => void;
  onDurationChange: (value: number) => void;
  onDurationModeChange: (value: "seconds" | "smart") => void;
  onAudioChange: (value: boolean) => void;
  onGenerationCountChange: (value: number) => void;
}) {
  return (
    <div className="videoSettingsPopover" role="dialog" aria-label="视频生成设置">
      <section className="settingsSection">
        <h3>视频比例</h3>
        <div className="ratioSettingsGrid">
          {RATIO_OPTIONS.map((value) => <button type="button" key={value} className={ratio === value ? "selected" : ""} aria-pressed={ratio === value} onClick={() => onRatioChange(value)}>
            <span className={`ratioShape ${value === "adaptive" ? "adaptive" : ""}`} style={{ aspectRatio: value === "adaptive" ? "1 / 1" : value.replace(":", " / ") }}>{value === "adaptive" ? <WandSparkles size={12} /> : null}</span>
            <b>{value === "adaptive" ? "智能" : value}</b>
          </button>)}
        </div>
      </section>
      <section className="settingsSection">
        <h3>分辨率</h3>
        <div className="settingsSegments resolutionSegments">
          {RESOLUTION_OPTIONS.map((value) => <button type="button" key={value} className={resolution === value ? "selected" : ""} aria-pressed={resolution === value} onClick={() => onResolutionChange(value)}>{value.toUpperCase()}</button>)}
        </div>
      </section>
      <section className="settingsSection">
        <h3>视频时长</h3>
        <div className="settingsSegments"><button type="button" className={durationMode === "seconds" ? "selected" : ""} aria-pressed={durationMode === "seconds"} onClick={() => onDurationModeChange("seconds")}>按秒数</button><button type="button" className={durationMode === "smart" ? "selected" : ""} aria-pressed={durationMode === "smart"} onClick={() => onDurationModeChange("smart")}>智能时长</button></div>
        {durationMode === "seconds" ? <div className="durationStrip">{DURATION_OPTIONS.map((value) => <button type="button" key={value} className={duration === value ? "selected" : ""} aria-pressed={duration === value} onClick={() => onDurationChange(value)}>{value}s</button>)}</div> : <p className="smartDurationNote">由模型根据画面内容自动决定合适时长</p>}
      </section>
      <section className="settingsSection">
        <h3>输出声音</h3>
        <div className="settingsSegments"><button type="button" className={generateAudio ? "selected" : ""} aria-pressed={generateAudio} onClick={() => onAudioChange(true)}>开</button><button type="button" className={!generateAudio ? "selected" : ""} aria-pressed={!generateAudio} onClick={() => onAudioChange(false)}>关</button></div>
      </section>
      <section className="settingsSection">
        <h3>选择生成数量</h3>
        <div className="countSegments">{Array.from({ length: 8 }, (_, index) => index + 1).map((value) => <button type="button" key={value} className={generationCount === value ? "selected" : ""} aria-pressed={generationCount === value} onClick={() => onGenerationCountChange(value)}>{value}</button>)}</div>
      </section>
    </div>
  );
}

function ConversationTaskCard({ record, task, busy, onOpen, onRefresh, onCancel }: {
  record: TaskRecord;
  task?: VideoTask;
  busy: BusyAction;
  onOpen: () => void;
  onRefresh: () => void;
  onCancel: () => void;
}) {
  const status = task?.status || record.status || "queued";
  const active = ACTIVE_STATUSES.has(status.toLowerCase());
  const failed = FAILED_STATUSES.has(status.toLowerCase());
  const videoUrl = getVideoUrl(task || null) || record.videoUrl || "";
  const poster = getLastFrameUrl(task || null) || record.lastFrameUrl || "";
  const progress = progressFor(status, task?.progress);
  const assetCount = record.assets?.length || record.assetNames?.length || (record.assetName ? 1 : 0);
  return (
    <article className="conversationTask">
      <div className="conversationPromptLine"><PromptWithMentions text={record.prompt} /></div>
      <div className="conversationMetaChips">
        <span><Video size={13} />{assetCount ? "参考生成" : "文本生成"}</span>
        <span>{(record.resolution || "720p").toUpperCase()}</span><span>{record.ratio === "adaptive" ? "智能比例" : record.ratio || "16:9"}</span><span>{record.durationMode === "smart" ? "智能时长" : `${record.duration || 5}秒`}</span>
        {assetCount ? <span>{assetCount}张</span> : null}<span>{record.generateAudio === false ? "无声" : "有声"}</span><span>{record.generationCount || 1}条</span>
        <span className="modelChip">{modelLabel(record.model)}</span>
      </div>
      {videoUrl ? (
        <button type="button" className="conversationVideoOpen" onClick={onOpen} aria-label="打开视频详情">
          <video src={videoUrl} muted playsInline preload="metadata" poster={poster || undefined} />
          <span className="openVideoHint"><Play size={18} fill="currentColor" />查看视频详情</span>
        </button>
      ) : (
        <div className={`conversationVideoStage ${failed ? "failed" : "running"}`}>
          <div className="stageAurora" />
          <span className="stageProgressBadge">{failed ? "生成失败" : `${Math.round(progress)}% 生成中`}</span>
          <div className="stageStatus">
            {failed ? <CircleAlert size={30} /> : <LoaderCircle size={32} className="spin" />}
            <b>{taskLabel(status)}</b>
            <small>{failed ? task?.error?.message || "请修改描述后重新生成" : "正在生成视频，完成后会自动显示"}</small>
          </div>
          {!failed ? <div className="stageProgressTrack"><span style={{ width: `${progress}%` }} /></div> : null}
        </div>
      )}
      <div className="conversationTaskActions">
        <StatusBadge status={status} />
        <button type="button" disabled={busy === "query"} onClick={onRefresh}><RefreshCw size={14} />刷新</button>
        {active ? <button type="button" className="cancelInline" disabled={busy === "cancel"} onClick={onCancel}><PauseCircle size={14} />取消</button> : null}
        {videoUrl ? <a href={videoUrl} download target="_blank" rel="noreferrer"><Download size={14} />下载</a> : null}
      </div>
    </article>
  );
}

function VideoDetailView({ record, task, onBack, onRegenerate, onEdit, onRemove }: {
  record: TaskRecord;
  task?: VideoTask;
  onBack: () => void;
  onRegenerate: () => void;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const videoUrl = getVideoUrl(task || null) || record.videoUrl || "";
  const poster = getLastFrameUrl(task || null) || record.lastFrameUrl || "";
  const status = task?.status || record.status;
  return (
    <section className="videoDetailShell" aria-label="视频详情">
      <div className="videoDetailCanvas">
        <div className="videoDetailToolbar">
          <button type="button" onClick={onBack}><ArrowLeft size={17} />返回创作</button>
          <div>
            {videoUrl ? <a href={videoUrl} download target="_blank" rel="noreferrer" aria-label="下载视频"><Download size={18} /></a> : null}
            <button type="button" onClick={onRemove} aria-label="从记录中移除"><Trash2 size={18} /></button>
          </div>
        </div>
        <div className="videoDetailPlayer">
          {videoUrl ? <video src={videoUrl} controls autoPlay playsInline preload="metadata" poster={poster || undefined} /> : <div className="officialPreviewEmpty"><LoaderCircle size={34} className="spin" /><b>{taskLabel(status)}</b><span>视频生成完成后将在这里播放</span></div>}
        </div>
      </div>
      <aside className="videoDetailSidebar">
        <div className="detailModel"><span><Video size={19} /></span><div><b>{modelLabel(record.model)}</b><small>{formatTaskTime(record.createdAt, true)}</small></div><StatusBadge status={status} /></div>
        <div className="detailSection"><h2>创意描述（Prompt）</h2><p><PromptWithMentions text={record.prompt} /></p></div>
        {record.assets?.length ? <div className="detailAssets">{record.assets.map((asset, index) => <div key={asset.id}>{asset.previewUrl ? <img src={asset.previewUrl} alt="" /> : <ImageIcon size={18} />}<span>图片{index + 1}</span></div>)}</div> : null}
        <div className="detailTags"><span>{(record.resolution || "720p").toUpperCase()}</span><span>{record.ratio === "adaptive" ? "智能比例" : record.ratio || "16:9"}</span><span>{record.durationMode === "smart" ? "智能时长" : `${record.duration || 5}秒`}</span><span>{record.generateAudio === false ? "无声" : "有声"}</span></div>
        <div className="detailSection detailInvocation"><h2>调用说明</h2><dl><dt>任务状态</dt><dd>{taskLabel(status)}</dd><dt>Task ID</dt><dd>{record.id}</dd></dl></div>
        <div className="detailBottomActions"><button type="button" onClick={onRegenerate}><RotateCcw size={15} />重新生成</button><button type="button" onClick={onEdit}><Pencil size={15} />重新编辑</button></div>
      </aside>
    </section>
  );
}

function App() {
  const [workspace, setWorkspace] = useState<Workspace>("create");
  const [apiKey, setApiKey] = useState("");
  const [loginDraft, setLoginDraft] = useState(() => sessionStorage.getItem(SESSION_KEY) || "");
  const [rememberKey, setRememberKey] = useState(() => Boolean(sessionStorage.getItem(SESSION_KEY)));
  const [authStatus, setAuthStatus] = useState<"checking" | "signed-out" | "signed-in">(
    () => sessionStorage.getItem(SESSION_KEY) ? "checking" : "signed-out",
  );
  const [loginError, setLoginError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [promptDocument, setPromptDocument] = useState("");
  const [mentionedAssetIds, setMentionedAssetIds] = useState<string[]>([]);
  const [selectedAssets, setSelectedAssets] = useState<Asset[]>([]);
  const [assetPickerOpen, setAssetPickerOpen] = useState(false);
  const [model, setModel] = useState(VIDEO_MODELS[0]?.id || DEFAULT_MODEL);
  const [ratio, setRatio] = useState("16:9");
  const [resolution, setResolution] = useState("720p");
  const [duration, setDuration] = useState("5");
  const [durationMode, setDurationMode] = useState<"seconds" | "smart">("seconds");
  const [generateAudio, setGenerateAudio] = useState(true);
  const [generationCount, setGenerationCount] = useState(1);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [currentTask, setCurrentTask] = useState<VideoTask | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskRecord[]>([]);
  const [taskSnapshots, setTaskSnapshots] = useState<Record<string, VideoTask>>({});
  const [conversationTaskIds, setConversationTaskIds] = useState<string[]>([]);
  const [conversationVersion, setConversationVersion] = useState(0);
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);
  const [historyRefreshing, setHistoryRefreshing] = useState(false);
  const [historyRefreshToken, setHistoryRefreshToken] = useState(0);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const normalizedKey = apiKey.trim();
  const keyValid = authStatus === "signed-in" && Boolean(normalizedKey);
  const hasPrompt = prompt.trim().length >= 2;
  const promptEditorRef = useRef<AssetPromptEditorHandle>(null);
  const selectedAssetsReady = selectedAssets.every(isAssetActive);
  const unusedAssetCount = selectedAssets.filter((asset) => !mentionedAssetIds.includes(asset.id)).length;
  const historyIds = useMemo(() => taskHistory.map((item) => item.id).join("\u0000"), [taskHistory]);
  const conversationIds = useMemo(() => conversationTaskIds.join("\u0000"), [conversationTaskIds]);
  const recordsById = useMemo(() => new Map(taskHistory.map((record) => [record.id, record])), [taskHistory]);
  const conversationRecords = useMemo(() => conversationTaskIds.flatMap((id) => {
    const record = recordsById.get(id);
    return record ? [record] : [];
  }), [conversationTaskIds, recordsById]);
  const detailRecord = detailTaskId ? recordsById.get(detailTaskId) : undefined;

  const persistTaskHistory = useCallback((updater: TaskRecord[] | ((current: TaskRecord[]) => TaskRecord[])) => {
    setTaskHistory((current) => {
      const next = typeof updater === "function" ? updater(current) : updater;
      if (normalizedKey) localStorage.setItem(taskHistoryKey(normalizedKey), JSON.stringify({ version: 6, items: next }));
      return next;
    });
  }, [normalizedKey]);

  const updateRecordFromTask = useCallback((task: VideoTask, metadata?: Partial<TaskRecord>) => {
    if (!task.id) return;
    persistTaskHistory((current) => {
      const previous = current.find((item) => item.id === task.id);
      const record: TaskRecord = {
        id: task.id,
        createdAt: metadata?.createdAt || previous?.createdAt || (task.created_at ? task.created_at * 1000 : Date.now()),
        prompt: metadata?.prompt || previous?.prompt || "视频生成任务",
        promptDocument: metadata?.promptDocument ?? previous?.promptDocument,
        assetName: metadata?.assetName ?? previous?.assetName,
        assetNames: metadata?.assetNames ?? previous?.assetNames,
        assets: metadata?.assets ?? previous?.assets,
        model: metadata?.model ?? previous?.model ?? task.model,
        ratio: metadata?.ratio ?? previous?.ratio,
        duration: metadata?.duration ?? previous?.duration,
        durationMode: metadata?.durationMode ?? previous?.durationMode,
        resolution: metadata?.resolution ?? previous?.resolution,
        generationCount: metadata?.generationCount ?? previous?.generationCount,
        generateAudio: metadata?.generateAudio ?? previous?.generateAudio,
        status: task.status || previous?.status,
        videoUrl: getVideoUrl(task) || previous?.videoUrl,
        lastFrameUrl: getLastFrameUrl(task) || previous?.lastFrameUrl,
      };
      return [record, ...current.filter((item) => item.id !== task.id)].slice(0, 20);
    });
  }, [persistTaskHistory]);

  const applyTask = useCallback((task: VideoTask, fallbackId?: string, metadata?: Partial<TaskRecord>) => {
    const normalized = { ...task, id: task.id || fallbackId || "", status: task.status || "queued" };
    if (!normalized.id) return normalized;
    setCurrentTask(normalized);
    setTaskSnapshots((current) => ({ ...current, [normalized.id]: normalized }));
    updateRecordFromTask(normalized, metadata);
    return normalized;
  }, [updateRecordFromTask]);

  useEffect(() => {
    const storedKey = sessionStorage.getItem(SESSION_KEY)?.trim() || "";
    if (!storedKey) return undefined;
    let disposed = false;
    Promise.all([authenticateApiKey(storedKey), loadPersistentTaskHistory(storedKey)])
      .then(([, history]) => {
        if (disposed) return;
        setApiKey(storedKey);
        setLoginDraft(storedKey);
        setTaskHistory(history);
        setAuthStatus("signed-in");
      })
      .catch(() => {
        if (disposed) return;
        sessionStorage.removeItem(SESSION_KEY);
        setRememberKey(false);
        setLoginDraft("");
        setLoginError("保存的 API Key 已失效，请重新登录");
        setAuthStatus("signed-out");
      });
    return () => { disposed = true; };
  }, []);

  useEffect(() => {
    if (workspace !== "create" || !keyValid || !conversationIds) return undefined;
    let disposed = false;
    let timer: number | undefined;
    const ids = conversationIds.split("\u0000").filter(Boolean);
    async function refreshConversation() {
      const activeIds = ids.filter((id) => {
        const status = taskSnapshots[id]?.status || recordsById.get(id)?.status;
        return !status || ACTIVE_STATUSES.has(status.toLowerCase());
      });
      if (!activeIds.length) return;
      const results = await fetchTaskStatuses(activeIds, normalizedKey);
      if (disposed) return;
      let hasActive = false;
      for (const result of results) {
        if (result.status !== "fulfilled") continue;
        const task = result.value;
        setTaskSnapshots((current) => ({ ...current, [task.id]: task }));
        updateRecordFromTask(task);
        if (currentTask?.id === task.id) setCurrentTask(task);
        if (ACTIVE_STATUSES.has(task.status.toLowerCase())) hasActive = true;
      }
      if (hasActive) timer = window.setTimeout(refreshConversation, 6000);
    }
    timer = window.setTimeout(refreshConversation, 4000);
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [conversationIds, currentTask?.id, keyValid, normalizedKey, recordsById, taskSnapshots, updateRecordFromTask, workspace]);

  useEffect(() => {
    if (workspace !== "tasks" || !keyValid || !historyIds) return undefined;
    let disposed = false;
    let timer: number | undefined;
    const ids = historyIds.split("\u0000").filter(Boolean);
    async function refreshAll() {
      await Promise.resolve();
      if (!disposed) setHistoryRefreshing(true);
      const results = await fetchTaskStatuses(ids, normalizedKey);
      if (disposed) return;
      const snapshots: Record<string, VideoTask> = {};
      let hasActive = false;
      const successful: VideoTask[] = [];
      for (const result of results) {
        if (result.status !== "fulfilled") continue;
        const task = result.value;
        snapshots[task.id] = task;
        successful.push(task);
        if (ACTIVE_STATUSES.has(task.status.toLowerCase())) hasActive = true;
      }
      setTaskSnapshots((current) => ({ ...current, ...snapshots }));
      if (successful.length) {
        const successfulById = new Map(successful.map((task) => [task.id, task]));
        persistTaskHistory((current) => current.map((record) => {
          const task = successfulById.get(record.id);
          return task ? { ...record, status: task.status, videoUrl: getVideoUrl(task) || record.videoUrl, lastFrameUrl: getLastFrameUrl(task) || record.lastFrameUrl } : record;
        }));
      }
      setHistoryRefreshing(false);
      if (hasActive) timer = window.setTimeout(refreshAll, 10_000);
    }
    void refreshAll();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [historyIds, historyRefreshToken, keyValid, normalizedKey, persistTaskHistory, workspace]);

  const handleLibraryMessage = useCallback((message: string, tone: "notice" | "error") => {
    if (tone === "error") { setError(message); setNotice(""); }
    else { setNotice(message); setError(""); }
  }, []);

  async function loginWithApiKey(event: FormEvent) {
    event.preventDefault();
    const candidate = loginDraft.trim();
    if (!candidate.startsWith("vap_live_") || candidate.length <= 12) {
      setLoginError("请输入完整的 vap_live_ API Key");
      return;
    }
    setLoginBusy(true);
    setLoginError("");
    try {
      const [, history] = await Promise.all([
        authenticateApiKey(candidate),
        loadPersistentTaskHistory(candidate),
      ]);
      setApiKey(candidate);
      setTaskHistory(history);
      setSelectedAssets([]);
      setTaskSnapshots({});
      setAuthStatus("signed-in");
      if (rememberKey) sessionStorage.setItem(SESSION_KEY, candidate);
      else sessionStorage.removeItem(SESSION_KEY);
    } catch (caught) {
      setLoginError(caught instanceof Error ? caught.message : "API Key 登录失败");
      setAuthStatus("signed-out");
    } finally {
      setLoginBusy(false);
    }
  }

  function logout() {
    sessionStorage.removeItem(SESSION_KEY);
    setApiKey("");
    setLoginDraft("");
    setRememberKey(false);
    setAuthStatus("signed-out");
    setTaskHistory([]);
    setTaskSnapshots({});
    setSelectedAssets([]);
    setWorkspace("create");
    startNewConversation();
  }

  function changeWorkspace(next: Workspace) {
    setWorkspace(next);
    setDetailTaskId(null);
    setError("");
    setNotice("");
  }

  function startNewConversation() {
    setConversationTaskIds([]);
    setCurrentTask(null);
    setPrompt("");
    setPromptDocument("");
    setMentionedAssetIds([]);
    setSelectedAssets([]);
    setAssetPickerOpen(false);
    setSettingsOpen(false);
    setDetailTaskId(null);
    setConversationVersion((value) => value + 1);
    setError("");
    setNotice("");
  }

  const handlePromptChange = useCallback((value: AssetPromptValue) => {
    setPrompt(value.text);
    setPromptDocument(value.serialized);
    setMentionedAssetIds(value.mentionedAssetIds);
  }, []);

  function removeSelectedAsset(assetId: string) {
    setSelectedAssets((current) => current.filter((asset) => asset.id !== assetId));
  }

  function moveSelectedAsset(assetId: string, offset: -1 | 1) {
    setSelectedAssets((current) => {
      const index = current.findIndex((asset) => asset.id === assetId);
      const target = index + offset;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function taskMetadata(overrides: Partial<TaskRecord> = {}): Partial<TaskRecord> {
    return {
      createdAt: Date.now(), prompt: prompt.trim(), promptDocument,
      assetName: selectedAssets[0]?.name, assetNames: selectedAssets.map((asset) => asset.name),
      assets: selectedAssets.map((asset) => ({ id: asset.id, groupId: asset.groupId, name: asset.name, status: asset.status, previewUrl: asset.previewUrl })),
      model, ratio, resolution, duration: durationMode === "smart" ? undefined : Number(duration), durationMode,
      generationCount, generateAudio, ...overrides,
    };
  }

  async function submitVideoTask(metadata: Partial<TaskRecord>, sourceAssets: TaskAsset[]) {
    const content: Array<Record<string, unknown>> = [{ type: "text", text: metadata.prompt?.trim() || "" }];
    for (const asset of sourceAssets) content.push({ type: "image_url", image_url: { url: assetUri(asset.id) }, role: "reference_image" });
    const task = await generateVideo({
      model: metadata.model || DEFAULT_MODEL,
      content,
      ratio: metadata.ratio === "adaptive" ? undefined : metadata.ratio || "16:9",
      duration: metadata.durationMode === "smart" ? undefined : metadata.duration || 5,
      resolution: metadata.resolution || "720p",
      generateAudio: metadata.generateAudio !== false,
      returnLastFrame: false,
      metadata: {
        prompt: metadata.prompt?.trim() || "",
        promptDocument: metadata.promptDocument,
        assets: sourceAssets,
        durationMode: metadata.durationMode,
        generationCount: metadata.generationCount,
      },
    }, normalizedKey);
    const normalized = applyTask(task, undefined, metadata);
    if (!normalized.id) throw new Error("视频服务未返回任务 ID");
    setConversationTaskIds((current) => current.includes(normalized.id) ? current : [...current, normalized.id]);
    return normalized;
  }

  async function createTask() {
    setError(""); setNotice("");
    if (!keyValid) return setError("请先填写有效的业务 API Key");
    if (!hasPrompt) return setError("请至少输入两个字描述要生成的视频");
    if (!selectedAssetsReady) return setError("所选素材中有暂不可用的图片，请重新选择");
    setBusy("generate");
    let createdCount = 0;
    try {
      const metadata = taskMetadata();
      for (let index = 0; index < generationCount; index += 1) {
        await submitVideoTask(metadata, selectedAssets);
        createdCount += 1;
      }
      setSettingsOpen(false);
      setNotice(`${createdCount} 个视频任务已加入当前对话，生成状态会自动更新`);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "创建视频任务失败";
      if (createdCount) {
        setNotice(`已成功创建 ${createdCount} 个任务，其余任务未能创建`);
        setError(message);
      } else setError(message);
    } finally {
      setBusy(null);
    }
  }

  async function regenerateTask(record: TaskRecord) {
    if (!keyValid) return setError("请先填写对应项目的业务 API Key");
    if ((record.assetNames?.length || record.assetName) && !record.assets?.length) {
      return setError("这条旧任务没有保存素材引用，请使用“重新编辑”重新选择素材");
    }
    setBusy("generate"); setError(""); setNotice("");
    try {
      await submitVideoTask({
        ...record, id: undefined, createdAt: Date.now(), status: "queued", videoUrl: undefined, lastFrameUrl: undefined,
        model: record.model || DEFAULT_MODEL,
        ratio: record.ratio || "16:9",
        resolution: record.resolution || "720p",
        duration: record.durationMode === "smart" ? undefined : record.duration || 5,
        durationMode: record.durationMode || "seconds",
        generationCount: 1,
      }, record.assets || []);
      setDetailTaskId(null);
      setWorkspace("create");
      setNotice("已按原参数创建新的生成任务");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重新生成失败");
    } finally {
      setBusy(null);
    }
  }

  async function queryTask(taskId: string, select = true) {
    if (!keyValid) return setError("请先填写对应项目的业务 API Key");
    setBusy("query"); setError("");
    try {
      const task = await getVideoTask(taskId, normalizedKey);
      if (select) applyTask(task, taskId); else updateRecordFromTask(task);
      setTaskSnapshots((current) => ({ ...current, [taskId]: task }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "任务刷新失败");
    } finally {
      setBusy(null);
    }
  }

  async function cancelTask(task = currentTask) {
    if (!task?.id || !keyValid) return;
    setBusy("cancel"); setError("");
    try {
      await cancelVideoTask(task.id, normalizedKey);
      const cancelled = { ...task, status: "cancelled" };
      applyTask(cancelled, task.id);
      setNotice("任务已取消");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "取消任务失败");
    } finally {
      setBusy(null);
    }
  }

  function editTask(record: TaskRecord) {
    setModel(record.model || DEFAULT_MODEL);
    setRatio(record.ratio || "16:9");
    setResolution(record.resolution || "720p");
    setDuration(String(record.duration || 5));
    setDurationMode(record.durationMode || "seconds");
    setGenerationCount(1);
    setGenerateAudio(record.generateAudio !== false);
    setSelectedAssets((record.assets || []) as Asset[]);
    setPrompt(record.prompt);
    setPromptDocument(record.promptDocument || "");
    setMentionedAssetIds([]);
    setAssetPickerOpen(false);
    setSettingsOpen(false);
    setDetailTaskId(null);
    setWorkspace("create");
    setConversationVersion((value) => value + 1);
  }

  function openTask(record: TaskRecord) {
    const snapshot = taskSnapshots[record.id];
    if (snapshot) { setCurrentTask(snapshot); return; }
    void queryTask(record.id);
  }

  async function removeTask(record: TaskRecord) {
    if (!window.confirm("从任务记录中移除这条视频？已生成的视频文件不会被删除。")) return;
    try {
      await removeVideoHistoryTask(record.id, normalizedKey);
      persistTaskHistory((current) => current.filter((item) => item.id !== record.id));
      setConversationTaskIds((current) => current.filter((id) => id !== record.id));
      setDetailTaskId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "移除任务记录失败");
    }
  }

  async function clearTaskHistory() {
    if (!window.confirm("清空当前 API Key 的全部任务记录？已生成的视频文件不会被删除。")) return;
    setHistoryRefreshing(true);
    try {
      await clearVideoHistory(normalizedKey);
      persistTaskHistory([]);
      setConversationTaskIds([]);
      setCurrentTask(null);
      setDetailTaskId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "清空任务记录失败");
    } finally {
      setHistoryRefreshing(false);
    }
  }

  if (authStatus !== "signed-in") {
    const checking = authStatus === "checking";
    return (
      <div className="loginShell">
        <header className="officialHeader loginHeader">
          <a className="officialBrand" href="#login"><span className="brandLogoFrame"><img src="/ruichi-logo.jpg" alt="" /></span><b>瑞池创作空间</b></a>
        </header>
        <main id="login" className="loginMain">
          <section className="loginCard" aria-labelledby="login-title">
            <div className="loginIntro">
              <span className="loginEyebrow">PROJECT ACCESS</span>
              <h1 id="login-title">进入专属创作空间</h1>
              <p>登录后，即可查看所属项目的素材库、视频任务和用量数据。</p>
              <div className="loginBoundary" aria-hidden="true"><span>API KEY</span><i /><span>PROJECT</span><i /><span>STUDIO</span></div>
            </div>
            <form className="loginForm" onSubmit={loginWithApiKey}>
              <div className="loginFormTitle"><ShieldCheck size={20} /><span><b>{checking ? "正在恢复登录" : "项目登录"}</b><small>{checking ? "正在验证当前标签页保存的凭证" : "请输入管理员分配给你的业务 API Key"}</small></span></div>
              <label className="loginKeyLabel" htmlFor="api-key-login">API Key</label>
              <div className="loginKeyField">
                <KeyRound size={17} />
                <input id="api-key-login" type={showKey ? "text" : "password"} value={loginDraft} disabled={checking || loginBusy} onChange={(event) => setLoginDraft(event.target.value)} placeholder="vap_live_..." autoComplete="off" spellCheck={false} />
                <button type="button" disabled={checking} onClick={() => setShowKey((value) => !value)} aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
              <label className="loginRemember"><input type="checkbox" checked={rememberKey} disabled={checking} onChange={(event) => setRememberKey(event.target.checked)} />在当前标签页保持登录</label>
              {loginError ? <div className="loginError" role="alert"><CircleAlert size={15} /><span>{loginError}</span></div> : null}
              <button className="loginButton" type="submit" disabled={checking || loginBusy || !loginDraft.trim()}>{checking || loginBusy ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}{checking ? "验证登录状态" : loginBusy ? "正在登录" : "使用 API Key 登录"}</button>
              <p className="loginSecurityNote">API Key 只发送到当前配置的服务端进行验证，不会写入页面内容。</p>
            </form>
          </section>
        </main>
        <footer className="officialFooter"><span>瑞池创作空间</span><p>素材与视频任务按项目隔离</p></footer>
      </div>
    );
  }

  return (
    <div className="officialShell">
      <header className="officialHeader">
        <a className="officialBrand" href="#main" onClick={() => changeWorkspace("create")}><span className="brandLogoFrame"><img src="/ruichi-logo.jpg" alt="" /></span><b>瑞池创作空间</b></a>
        <nav className="officialNav" aria-label="工作区">
          {workspaceItems.map((item) => { const Icon = item.icon; return <button key={item.id} type="button" className={workspace === item.id ? "active" : ""} onClick={() => changeWorkspace(item.id)}><Icon size={15} />{item.label}</button>; })}
        </nav>
        <div className="sessionControl"><button type="button" onClick={logout}><LogOut size={15} />退出</button></div>
      </header>

      <main id="main" className={`officialMain ${detailRecord ? "detailMain" : ""}`}>
        {error ? <div className="officialMessage error" role="alert"><CircleAlert size={17} /><span>{error}</span><button type="button" onClick={() => setError("")}><X size={15} /></button></div> : null}
        {notice ? <div className="officialMessage success" role="status"><CircleCheck size={17} /><span>{notice}</span><button type="button" onClick={() => setNotice("")}><X size={15} /></button></div> : null}

        {workspace === "create" && detailRecord ? <VideoDetailView
          record={detailRecord}
          task={taskSnapshots[detailRecord.id]}
          onBack={() => setDetailTaskId(null)}
          onRegenerate={() => void regenerateTask(detailRecord)}
          onEdit={() => editTask(detailRecord)}
          onRemove={() => removeTask(detailRecord)}
        /> : null}

        {workspace === "create" && !detailRecord ? (
          <div className={`createWorkspace ${conversationRecords.length ? "hasConversation" : ""}`}>
            <div className="conversationHeader"><span>{conversationRecords.length ? "创作会话" : ""}</span><button type="button" onClick={startNewConversation}><MessageCirclePlus size={16} />新对话</button></div>
            {!conversationRecords.length ? <div className="officialPageTitle"><h1>体验视频生成，让创意生动</h1><p>从项目素材库选择多张图片，并在描述中用 @ 精确指定素材。</p></div> : null}
            {conversationRecords.length ? <div className="conversationFeed">{conversationRecords.map((record) => {
              const task = taskSnapshots[record.id];
              return <ConversationTaskCard key={record.id} record={record} task={task} busy={busy} onOpen={() => setDetailTaskId(record.id)} onRefresh={() => void queryTask(record.id, false)} onCancel={() => void cancelTask(task || { id: record.id, status: record.status || "running" })} />;
            })}</div> : null}

            <section className="generatorCard conversationComposer" aria-label="视频生成输入">
              <div className="generatorInputArea">
                <div className="selectedAssetRail" aria-label="已选参考素材">
                  {selectedAssets.map((asset, index) => <article className="selectedAssetTile" key={asset.id}>
                    <button type="button" className="selectedAssetInsert" onClick={() => promptEditorRef.current?.insertAsset(asset.id)} aria-label={`在描述中引用图片${index + 1}`}>{asset.previewUrl ? <img src={asset.previewUrl} alt="" /> : <ImageIcon size={20} />}<span>图片{index + 1}</span></button>
                    <div className="selectedAssetControls"><button type="button" disabled={index === 0} onClick={() => moveSelectedAsset(asset.id, -1)} aria-label={`将图片${index + 1}前移`}><ChevronLeft size={12} /></button><button type="button" disabled={index === selectedAssets.length - 1} onClick={() => moveSelectedAsset(asset.id, 1)} aria-label={`将图片${index + 1}后移`}><ChevronRight size={12} /></button><button type="button" onClick={() => removeSelectedAsset(asset.id)} aria-label={`移除图片${index + 1}`}><X size={12} /></button></div>
                  </article>)}
                  {selectedAssets.length < 9 ? <button type="button" className="referenceSlot" onClick={() => setAssetPickerOpen(true)}><span>+</span><small>{selectedAssets.length ? "继续添加" : "参考素材"}</small></button> : null}
                </div>
                <Suspense fallback={<div className="assetPromptLoading"><LoaderCircle size={18} className="spin" />正在准备创作输入框</div>}>
                  <AssetPromptEditor key={conversationVersion} ref={promptEditorRef} selectedAssets={selectedAssets} initialState={promptDocument} initialText={promptDocument ? undefined : prompt} onChange={handlePromptChange} placeholder="描述你想生成的视频；输入 @ 可以指定已选素材，例如：@图片1 中的人物拿起 @图片2 中的产品……" />
                </Suspense>
                <span className="promptCount">{prompt.length}/2000</span>
              </div>
              <div className="generatorToolbar">
                 <ModelPicker value={model} onChange={setModel} onOpen={() => { setSettingsOpen(false); setAssetPickerOpen(false); }} />
                <button type="button" className="referenceMenuButton" onClick={() => { setSettingsOpen(false); setAssetPickerOpen((value) => !value); }}><ImageIcon size={15} />{selectedAssets.length ? `${selectedAssets.length} 张参考素材` : "选择参考素材"}<ChevronDown size={14} /></button>
                {selectedAssets.length ? <button type="button" className="mentionHintButton" onClick={() => promptEditorRef.current?.focus()}><AtSign size={13} />输入 @ 引用素材</button> : null}
                {selectedAssets.length ? <button type="button" className="clearReference" onClick={() => setSelectedAssets([])}><X size={13} />清除</button> : null}
                <button type="button" className={`videoSettingsTrigger ${settingsOpen ? "active" : ""}`} aria-expanded={settingsOpen} aria-haspopup="dialog" onClick={() => { setAssetPickerOpen(false); setSettingsOpen((value) => !value); }}>
                  <span className="triggerRatioIcon" />
                  <b>{ratio === "adaptive" ? "智能比例" : ratio}</b><i />
                  <span>{resolution.toUpperCase()}</span><i />
                  <Clock3 size={14} /><span>{durationMode === "smart" ? "智能时长" : `${duration}秒`}</span><i />
                  <span>{generateAudio ? "有声" : "无声"}</span><i /><span>{generationCount}条</span>
                  <ChevronDown size={13} className="settingsChevron" />
                </button>
                {selectedAssets.length && unusedAssetCount ? <span className="unusedAssetNotice">{unusedAssetCount} 张未在描述中点名</span> : null}
                <button type="button" className="generateButton" onClick={() => void createTask()} disabled={busy === "generate" || !keyValid || !hasPrompt || !selectedAssetsReady || prompt.length > 2000} aria-label="生成视频">{busy === "generate" ? <LoaderCircle size={19} className="spin" /> : <ArrowUp size={20} />}</button>
              </div>
              {settingsOpen ? <VideoSettingsPanel
                ratio={ratio}
                resolution={resolution}
                duration={Number(duration)}
                durationMode={durationMode}
                generateAudio={generateAudio}
                generationCount={generationCount}
                onRatioChange={setRatio}
                onResolutionChange={setResolution}
                onDurationChange={(value) => setDuration(String(value))}
                onDurationModeChange={setDurationMode}
                onAudioChange={setGenerateAudio}
                onGenerationCountChange={setGenerationCount}
              /> : null}
            </section>

            {assetPickerOpen ? <section className="officialPicker" aria-labelledby="picker-title"><div className="sectionTitleRow"><div><h2 id="picker-title">选择参考素材</h2><p>按选择顺序编号为图片1至图片9，完成后可在描述中输入 @ 引用。</p></div><button type="button" className="closePanel" onClick={() => setAssetPickerOpen(false)}><Check size={16} />完成（{selectedAssets.length}/9）</button></div><AssetLibrary apiKey={normalizedKey} apiKeyValid={keyValid} mode="select" selectedAssets={selectedAssets} maxSelection={9} onSelectionChange={setSelectedAssets} onMessage={handleLibraryMessage} /></section> : null}
          </div>
        ) : null}

        {workspace === "library" ? <section className="officialSection" aria-labelledby="library-title"><div className="sectionTitleRow"><div><h1 id="library-title">项目素材库</h1><p>按照方舟素材规范上传并管理图片、视频和音频，处理状态以方舟返回结果为准。</p></div></div><AssetLibrary apiKey={normalizedKey} apiKeyValid={keyValid} mode="manage" selectedAssets={selectedAssets} onSelectionChange={setSelectedAssets} onMessage={handleLibraryMessage} /></section> : null}

        {workspace === "tasks" ? <section className="officialSection taskSection" aria-labelledby="tasks-title">
          <div className="sectionTitleRow"><div><h1 id="tasks-title">任务记录</h1><p>任务保存在服务端，使用同一个 API Key 登录即可继续查看。</p></div><div className="taskHeaderActions"><button type="button" className="secondaryButton" disabled={!keyValid || historyRefreshing} onClick={() => setHistoryRefreshToken((value) => value + 1)}>{historyRefreshing ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}刷新状态</button>{taskHistory.length ? <button type="button" className="quietDanger" disabled={historyRefreshing} onClick={() => void clearTaskHistory()}><Trash2 size={14} />清空</button> : null}</div></div>
          {!keyValid ? <div className="officialEmpty"><KeyRound size={28} /><b>请先连接服务</b><p>输入业务 API Key 后会自动加载对应项目的任务状态。</p></div> : null}
          {keyValid && !taskHistory.length ? <div className="officialEmpty"><Video size={30} /><b>还没有视频任务</b><p>创建的视频会自动出现在这里。</p><button type="button" className="primaryButton" onClick={() => changeWorkspace("create")}><Play size={15} />创建视频</button></div> : null}
          {keyValid && taskHistory.length ? <div className="taskListLayout"><div className="officialTaskList">{taskHistory.map((record) => {
            const snapshot = taskSnapshots[record.id]; const status = snapshot?.status || record.status; const preview = getLastFrameUrl(snapshot || null) || record.lastFrameUrl; const videoUrl = getVideoUrl(snapshot || null) || record.videoUrl; const assetSummary = record.assetNames?.length ? record.assetNames.join("、") : record.assetName;
            return <article key={record.id} className={`officialTaskCard ${currentTask?.id === record.id ? "selected" : ""}`}><button type="button" className="taskMainButton" onClick={() => openTask(record)}><span className="taskThumb">{preview ? <img src={preview} alt="" /> : <Video size={22} />}</span><span className="taskSummary"><b>{record.prompt}</b><small>{formatTaskTime(record.createdAt)} · {record.ratio === "adaptive" ? "智能比例" : record.ratio || "16:9"} · {record.durationMode === "smart" ? "智能时长" : `${record.duration || 5}秒`}{assetSummary ? ` · ${assetSummary}` : ""}</small></span><StatusBadge status={status} /></button><div className="taskCardActions"><button type="button" onClick={() => void queryTask(record.id)}><RefreshCw size={14} />刷新</button>{videoUrl ? <button type="button" onClick={() => { setWorkspace("create"); setDetailTaskId(record.id); }}><Play size={14} />详情</button> : null}{videoUrl ? <a href={videoUrl} download target="_blank" rel="noreferrer"><Download size={14} />下载</a> : null}<button type="button" className="removeTask" onClick={() => removeTask(record)}><Trash2 size={14} />移除</button></div></article>;
          })}</div><ResultPanel task={currentTask} busy={busy} onRefresh={(id) => void queryTask(id)} onCancel={() => void cancelTask()} /></div> : null}
        </section> : null}

        {workspace === "usage" ? <UsagePanel apiKey={normalizedKey} apiKeyValid={keyValid} /> : null}
      </main>
      <footer className="officialFooter"><span>瑞池创作空间</span><p>素材与视频任务按项目隔离</p></footer>
    </div>
  );
}

export default App;
