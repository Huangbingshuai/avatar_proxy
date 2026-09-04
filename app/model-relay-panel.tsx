"use client";

import {
  Activity,
  AudioLines,
  Bot,
  Boxes,
  Check,
  CloudCog,
  Image as ImageIcon,
  KeyRound,
  MessageSquareText,
  Network,
  RefreshCw,
  Route,
  Search,
  ServerCog,
  ShieldCheck,
  Video,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { AdminApi } from "./admin-api";
import { getModelIconPath, getProviderIconPath } from "./model-icon-library";

type Project = { name: string; displayName: string };
type ApiKey = {
  id: string;
  name: string;
  projectName: string;
  keyPrefix: string;
  status: string;
};
type CatalogModel = {
  id: string;
  displayName: string;
  provider: string;
  modality: string;
  enabled: boolean;
};
type Channel = {
  id: string;
  projectName: string;
  name: string;
  provider: string;
  status: string;
};
type ProjectModel = {
  model: string;
  displayName: string;
  provider: string;
  modality: string;
  channelId?: string | null;
  upstreamModel?: string | null;
  enabled: boolean;
};
type Usage = {
  id: string;
  projectName: string;
  apiKeyId: string;
  model: string;
  provider: string;
  status: string;
  inputTokens?: number | null;
  outputTokens?: number | null;
  generatedImages?: number | null;
  videoSeconds?: number | null;
  inputCharacters?: number | null;
  audioSeconds?: number | null;
  createdAt: string;
};
type Task = {
  id: string;
  object: string;
  model: string;
  status: string;
  progress?: number;
  created_at: string | number;
};

const providerLabel: Record<string, string> = {
  openai: "OpenAI",
  volcengine_ark: "火山方舟",
  volcengine_speech: "豆包语音",
  aliyun_bailian: "阿里百炼",
  minimax: "MiniMax",
};
const modalityLabel: Record<string, string> = {
  text: "文本",
  image: "图片",
  video: "视频",
  embedding: "向量",
  audio: "音频",
};
function ModelGlyph({
  modality,
  size = 20,
}: {
  modality: string;
  size?: number;
}) {
  if (modality === "image") return <ImageIcon size={size} />;
  if (modality === "video") return <Video size={size} />;
  if (modality === "embedding") return <Network size={size} />;
  if (modality === "audio") return <AudioLines size={size} />;
  return <MessageSquareText size={size} />;
}

function ModelBrandIcon({
  model,
  name,
  size = 28,
}: {
  model: string;
  name: string;
  size?: number;
}) {
  const icon = getModelIconPath(model);
  if (!icon) return <Bot aria-hidden="true" size={size} />;
  return <img src={icon} width={size} height={size} alt={`${name} 图标`} />;
}

function ProviderBrandIcon({
  provider,
  size = 16,
}: {
  provider: string;
  size?: number;
}) {
  const icon = getProviderIconPath(provider);
  if (!icon) return <CloudCog aria-hidden="true" size={size} />;
  return (
    <img src={icon} width={size} height={size} alt="" aria-hidden="true" />
  );
}

export default function ModelRelayPanel({
  projects,
  apiKeys,
  adminApi,
}: {
  projects: Project[];
  apiKeys: ApiKey[];
  adminApi: AdminApi;
}) {
  const [projectName, setProjectName] = useState(projects[0]?.name || "");
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [models, setModels] = useState<ProjectModel[]>([]);
  const [usage, setUsage] = useState<Usage[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [modelFilter, setModelFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const [catalogProvider, setCatalogProvider] = useState("");
  const [catalogModality, setCatalogModality] = useState("");
  const [catalogSearch, setCatalogSearch] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const activeProjectName = projects.some((item) => item.name === projectName)
    ? projectName
    : projects[0]?.name || "";
  const projectKeys = useMemo(
    () => apiKeys.filter((item) => item.projectName === activeProjectName),
    [apiKeys, activeProjectName],
  );
  const enabledModelCount = models.filter((item) => item.enabled).length;
  const filteredModels = useMemo(() => {
    const needle = catalogSearch.trim().toLowerCase();
    return models.filter((model) => {
      if (catalogProvider && model.provider !== catalogProvider) return false;
      if (catalogModality && model.modality !== catalogModality) return false;
      return (
        !needle ||
        model.displayName.toLowerCase().includes(needle) ||
        model.model.toLowerCase().includes(needle)
      );
    });
  }, [catalogModality, catalogProvider, catalogSearch, models]);

  const loadProject = useCallback(async () => {
    if (!activeProjectName) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const usageQuery = new URLSearchParams({
        projectName: activeProjectName,
        limit: "200",
      });
      if (modelFilter) usageQuery.set("model", modelFilter);
      if (providerFilter) usageQuery.set("provider", providerFilter);
      if (startTime) usageQuery.set("start", startTime);
      if (endTime) usageQuery.set("end", endTime);
      const [catalogData, channelData, modelData, usageData, taskData] =
        await Promise.all([
          adminApi("/api/internal/model/catalog"),
          adminApi(
            `/api/internal/provider/channels?projectName=${encodeURIComponent(activeProjectName)}`,
          ),
          adminApi(
            `/api/internal/project/${encodeURIComponent(activeProjectName)}/models`,
          ),
          adminApi(`/api/internal/inference/usage?${usageQuery.toString()}`),
          adminApi(
            `/api/internal/inference/tasks?projectName=${encodeURIComponent(activeProjectName)}&limit=100`,
          ),
        ]);
      setCatalog((catalogData.models ?? []) as CatalogModel[]);
      setChannels((channelData.channels ?? []) as Channel[]);
      setModels((modelData.models ?? []) as ProjectModel[]);
      setUsage((usageData.usage ?? []) as Usage[]);
      setTasks((taskData.tasks ?? []) as Task[]);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "项目模型配置加载失败",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeProjectName,
    adminApi,
    endTime,
    modelFilter,
    providerFilter,
    startTime,
  ]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadProject(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProject]);

  async function persistProjectModels(
    alias: string,
    nextModels: ProjectModel[],
    previousModels: ProjectModel[],
  ) {
    setModels(nextModels);
    setBusy(`project-model:${alias}`);
    setError("");
    setMessage("");
    try {
      const bindings = nextModels
        .filter((item) => item.enabled)
        .map((item) => ({
          model: item.model,
          channelId: item.channelId,
          upstreamModel: item.upstreamModel,
          enabled: true,
        }));
      const data = await adminApi(
        `/api/internal/project/${encodeURIComponent(activeProjectName)}/models`,
        { method: "PUT", body: JSON.stringify({ bindings }) },
      );
      if (Array.isArray(data.models)) setModels(data.models as ProjectModel[]);
      const changed = nextModels.find((item) => item.model === alias);
      setMessage(
        changed?.enabled ? `${alias} 已启用并立即生效` : `${alias} 已停用`,
      );
    } catch (caught) {
      setModels(previousModels);
      setError(
        caught instanceof Error ? caught.message : "项目模型状态更新失败",
      );
    } finally {
      setBusy("");
    }
  }

  function changeModelChannel(model: ProjectModel, channelId: string) {
    const previousModels = models;
    const nextModels = models.map((item) =>
      item.model === model.model ? { ...item, channelId } : item,
    );
    setModels(nextModels);
    if (model.enabled)
      void persistProjectModels(model.model, nextModels, previousModels);
  }

  function changeModelEnabled(
    model: ProjectModel,
    enabled: boolean,
    candidates: Channel[],
  ) {
    const channelId =
      model.channelId || (candidates.length === 1 ? candidates[0].id : "");
    if (enabled && !channelId) {
      setError("请先为该模型选择供应商渠道");
      return;
    }
    const previousModels = models;
    const nextModels = models.map((item) =>
      item.model === model.model ? { ...item, enabled, channelId } : item,
    );
    void persistProjectModels(model.model, nextModels, previousModels);
  }

  return (
    <div className="content modelRelayPanel">
      <section className="panel relayIntro">
        <div className="relayIntroCopy">
          <span>
            <CloudCog size={22} />
          </span>
          <div>
            <small>MODEL ROUTER</small>
            <h3>多供应商模型中转</h3>
            <p>
              为项目统一启用模型能力，项目下所有有效业务 Key 自动共享相同权限。
            </p>
          </div>
        </div>
        <label>
          <span>当前客户项目</span>
          <select
            value={activeProjectName}
            onChange={(event) => setProjectName(event.target.value)}
          >
            {projects.map((project) => (
              <option key={project.name} value={project.name}>
                {project.displayName} · {project.name}
              </option>
            ))}
          </select>
        </label>
      </section>
      {error && <div className="errorBanner">{error}</div>}
      {message && (
        <div className="successBanner">
          <Check size={16} />
          {message}
        </div>
      )}

      <section className="relaySummary" aria-label="模型中转概览">
        <article>
          <span className="coral">
            <Route size={19} />
          </span>
          <div>
            <small>已绑定模型</small>
            <b>
              {enabledModelCount}
              <em> / {models.length}</em>
            </b>
          </div>
        </article>
        <article>
          <span className="cyan">
            <ServerCog size={19} />
          </span>
          <div>
            <small>可用渠道</small>
            <b>
              {channels.filter((item) => item.status === "active").length}
              <em> 个</em>
            </b>
          </div>
        </article>
        <article>
          <span className="amber">
            <KeyRound size={19} />
          </span>
          <div>
            <small>项目业务 Key</small>
            <b>
              {projectKeys.length}
              <em> 枚</em>
            </b>
          </div>
        </article>
        <article>
          <span className="purple">
            <ShieldCheck size={19} />
          </span>
          <div>
            <small>权限范围</small>
            <b>
              项目级<em> 全部 Key</em>
            </b>
          </div>
        </article>
      </section>

      <section className="panel relayCatalogPanel">
        <div className="panelHead">
          <div>
            <div className="relaySectionLabel">
              <Boxes size={14} />
              模型目录
            </div>
            <h3>项目模型绑定</h3>
            <p>
              选择渠道后直接启用，开关状态会立即保存；只有多个可用渠道时才需要手动选择。
            </p>
          </div>
        </div>
        <div className="relayMarketFilters">
          <div className="relayFilterLine">
            <span>厂商</span>
            <div>
              <button
                type="button"
                className={!catalogProvider ? "active" : ""}
                onClick={() => setCatalogProvider("")}
              >
                全部
              </button>
              {Object.entries(providerLabel)
                .filter(([provider]) =>
                  models.some((model) => model.provider === provider),
                )
                .map(([provider, label]) => (
                  <button
                    type="button"
                    className={catalogProvider === provider ? "active" : ""}
                    onClick={() => setCatalogProvider(provider)}
                    key={provider}
                  >
                    <ProviderBrandIcon provider={provider} />
                    {label}
                  </button>
                ))}
            </div>
          </div>
          <div className="relayFilterLine">
            <span>类型</span>
            <div>
              <button
                type="button"
                className={!catalogModality ? "active" : ""}
                onClick={() => setCatalogModality("")}
              >
                全部
              </button>
              {Object.entries(modalityLabel)
                .filter(([modality]) =>
                  models.some((model) => model.modality === modality),
                )
                .map(([modality, label]) => (
                  <button
                    type="button"
                    className={catalogModality === modality ? "active" : ""}
                    onClick={() => setCatalogModality(modality)}
                    key={modality}
                  >
                    <ModelGlyph modality={modality} size={14} />
                    {label}
                  </button>
                ))}
            </div>
          </div>
          <div className="relayFilterLine search">
            <span>搜索</span>
            <label>
              <Search size={16} />
              <input
                aria-label="搜索项目模型"
                value={catalogSearch}
                onChange={(event) => setCatalogSearch(event.target.value)}
                placeholder="搜索模型名称或别名..."
              />
            </label>
            <small>{filteredModels.length} 个模型</small>
          </div>
        </div>
        <div className="relayModelTable">
          <div className="relayModelTableHead">
            <span>模型</span>
            <span>类型</span>
            <span>供应商渠道</span>
            <span>固定上游模型</span>
            <span>状态</span>
          </div>
          {filteredModels.map((model) => {
            const candidates = channels.filter(
              (channel) =>
                channel.provider === model.provider &&
                channel.status === "active",
            );
            return (
              <article
                key={model.model}
                className={`relayModelTableRow ${model.enabled ? "enabled" : "disabled"}`}
              >
                <div className="relayModelCell">
                  <span
                    className={`relayModelIcon brand ${model.modality}`}
                    data-model={model.model}
                  >
                    <ModelBrandIcon
                      model={model.model}
                      name={model.displayName}
                      size={30}
                    />
                  </span>
                  <div className="relayModelIdentity">
                    <b>{model.model}</b>
                    <small>
                      {providerLabel[model.provider] || model.provider}
                    </small>
                  </div>
                </div>
                <span className={`relayTypePill ${model.modality}`}>
                  <ModelGlyph modality={model.modality} size={13} />
                  {modalityLabel[model.modality] || model.modality}
                </span>
                <label className="relayInlineControl">
                  <select
                    aria-label={`${model.displayName}渠道`}
                    disabled={
                      busy === `project-model:${model.model}` ||
                      !candidates.length
                    }
                    value={model.channelId || ""}
                    onChange={(event) =>
                      changeModelChannel(model, event.target.value)
                    }
                  >
                    <option value="">选择渠道</option>
                    {candidates.map((channel) => (
                      <option key={channel.id} value={channel.id}>
                        {channel.name}
                      </option>
                    ))}
                  </select>
                  {!candidates.length && <small>暂无可用渠道</small>}
                </label>
                <div className="relayFixedModel">
                  <code>{model.upstreamModel || "未配置"}</code>
                  <small>系统固定映射</small>
                </div>
                <label className="relaySwitch">
                  <input
                    aria-label={`启用${model.displayName}`}
                    type="checkbox"
                    checked={model.enabled}
                    disabled={busy === `project-model:${model.model}`}
                    onChange={(event) =>
                      changeModelEnabled(
                        model,
                        event.target.checked,
                        candidates,
                      )
                    }
                  />
                  <span aria-hidden="true">
                    <i />
                  </span>
                  <em>
                    {busy === `project-model:${model.model}`
                      ? "保存中"
                      : model.enabled
                        ? "已启用"
                        : "未启用"}
                  </em>
                </label>
              </article>
            );
          })}
          {!loading && catalog.length > 0 && models.length === 0 && (
            <div className="emptyRow">
              目录已加载，但项目模型状态为空，请刷新重试。
            </div>
          )}
          {!loading && models.length > 0 && filteredModels.length === 0 && (
            <div className="emptyRow">没有符合当前筛选条件的模型。</div>
          )}
        </div>
      </section>

      <section className="panel relayUsagePanel">
        <div className="panelHead">
          <div>
            <div className="relaySectionLabel">
              <Activity size={14} />
              可观测性
            </div>
            <h3>中转用量与任务</h3>
            <p>
              只记录供应商真实返回的 Token、图片数和视频时长；未知值保持为空。
            </p>
          </div>
          <button
            className="iconButton"
            onClick={() => void loadProject()}
            disabled={loading}
            aria-label="刷新中转用量"
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </div>
        <div className="relayFilters">
          <select
            aria-label="按模型筛选"
            value={modelFilter}
            onChange={(event) => setModelFilter(event.target.value)}
          >
            <option value="">全部模型</option>
            {catalog.map((model) => (
              <option key={model.id} value={model.id}>
                {model.displayName}
              </option>
            ))}
          </select>
          <select
            aria-label="按供应商筛选"
            value={providerFilter}
            onChange={(event) => setProviderFilter(event.target.value)}
          >
            <option value="">全部供应商</option>
            {Object.entries(providerLabel).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input
            aria-label="用量开始时间"
            type="datetime-local"
            value={startTime}
            onChange={(event) => setStartTime(event.target.value)}
          />
          <input
            aria-label="用量结束时间"
            type="datetime-local"
            value={endTime}
            onChange={(event) => setEndTime(event.target.value)}
          />
        </div>
        <div className="dataTable relayUsageTable">
          <div className="tableRow tableHead">
            <span>时间</span>
            <span>模型 / 供应商</span>
            <span>业务 Key</span>
            <span>真实用量</span>
            <span>状态</span>
          </div>
          {usage.map((item) => (
            <div className="tableRow" key={item.id}>
              <span>{item.createdAt}</span>
              <div>
                <b>{item.model}</b>
                <small>{providerLabel[item.provider] || item.provider}</small>
              </div>
              <code>
                {apiKeys.find((key) => key.id === item.apiKeyId)?.name ||
                  item.apiKeyId.slice(0, 8)}
              </code>
              <span>
                {item.inputTokens != null || item.outputTokens != null
                  ? `${item.inputTokens ?? "—"} / ${item.outputTokens ?? "—"} tokens`
                  : item.generatedImages != null
                    ? `${item.generatedImages} 张图片`
                    : item.videoSeconds != null
                      ? `${item.videoSeconds} 秒视频`
                      : item.inputCharacters != null
                        ? `${item.inputCharacters} 字符`
                        : item.audioSeconds != null
                          ? `${item.audioSeconds} 秒音频`
                          : "未返回"}
              </span>
              <i className={item.status}>{item.status}</i>
            </div>
          ))}
          {!loading && !usage.length && (
            <div className="emptyRow">当前筛选条件下暂无中转用量。</div>
          )}
        </div>
        <div className="relayTaskStrip">
          <Activity size={15} />
          <span>最近任务</span>
          {tasks.slice(0, 8).map((task) => (
            <code key={task.id}>
              {task.model} · {task.status}
              {task.progress != null ? ` ${task.progress}%` : ""}
            </code>
          ))}
          {!tasks.length && <small>暂无异步任务</small>}
        </div>
      </section>
    </div>
  );
}
