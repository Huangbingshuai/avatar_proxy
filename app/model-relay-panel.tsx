"use client";

import { Activity, Check, RefreshCw, Save, ServerCog } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { AdminApi } from "./admin-api";

type Project = { name: string; displayName: string };
type ApiKey = { id: string; name: string; projectName: string; keyPrefix: string; status: string };
type CatalogModel = { id: string; displayName: string; provider: string; modality: string; enabled: boolean };
type Channel = { id: string; projectName: string; name: string; provider: string; status: string };
type ProjectModel = { model: string; displayName: string; provider: string; modality: string; channelId?: string | null; upstreamModel?: string | null; enabled: boolean };
type KeyModel = { model: string; displayName: string; modality: string; enabled: boolean };
type Usage = { id: string; projectName: string; apiKeyId: string; model: string; provider: string; status: string; inputTokens?: number | null; outputTokens?: number | null; generatedImages?: number | null; videoSeconds?: number | null; createdAt: string };
type Task = { id: string; object: string; model: string; status: string; progress?: number; created_at: string | number };

const providerLabel: Record<string, string> = { openai: "OpenAI", volcengine_ark: "火山方舟", aliyun_bailian: "阿里百炼", minimax: "MiniMax" };

export default function ModelRelayPanel({ projects, apiKeys, adminApi }: { projects: Project[]; apiKeys: ApiKey[]; adminApi: AdminApi }) {
  const [projectName, setProjectName] = useState(projects[0]?.name || "");
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [models, setModels] = useState<ProjectModel[]>([]);
  const [keyId, setKeyId] = useState("");
  const [keyModels, setKeyModels] = useState<KeyModel[]>([]);
  const [usage, setUsage] = useState<Usage[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [modelFilter, setModelFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const activeProjectName = projects.some((item) => item.name === projectName) ? projectName : projects[0]?.name || "";
  const projectKeys = useMemo(() => apiKeys.filter((item) => item.projectName === activeProjectName), [apiKeys, activeProjectName]);
  const activeKeyId = projectKeys.some((item) => item.id === keyId) ? keyId : projectKeys[0]?.id || "";

  const loadProject = useCallback(async () => {
    if (!activeProjectName) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const usageQuery = new URLSearchParams({ projectName: activeProjectName, limit: "200" });
      if (modelFilter) usageQuery.set("model", modelFilter);
      if (providerFilter) usageQuery.set("provider", providerFilter);
      if (startTime) usageQuery.set("start", startTime);
      if (endTime) usageQuery.set("end", endTime);
      const [catalogData, channelData, modelData, usageData, taskData] = await Promise.all([
        adminApi("/api/internal/model/catalog"),
        adminApi(`/api/internal/provider/channels?projectName=${encodeURIComponent(activeProjectName)}`),
        adminApi(`/api/internal/project/${encodeURIComponent(activeProjectName)}/models`),
        adminApi(`/api/internal/inference/usage?${usageQuery.toString()}`),
        adminApi(`/api/internal/inference/tasks?projectName=${encodeURIComponent(activeProjectName)}&limit=100`),
      ]);
      setCatalog((catalogData.models ?? []) as CatalogModel[]);
      setChannels((channelData.channels ?? []) as Channel[]);
      setModels((modelData.models ?? []) as ProjectModel[]);
      setUsage((usageData.usage ?? []) as Usage[]);
      setTasks((taskData.tasks ?? []) as Task[]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "项目模型配置加载失败");
    } finally {
      setLoading(false);
    }
  }, [activeProjectName, adminApi, endTime, modelFilter, providerFilter, startTime]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadProject(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProject]);

  useEffect(() => {
    if (!activeKeyId) return;
    let cancelled = false;
    void adminApi(`/api/internal/apikey/${encodeURIComponent(activeKeyId)}/models`)
      .then((data) => { if (!cancelled) setKeyModels((data.models ?? []) as KeyModel[]); })
      .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : "Key模型权限加载失败"); });
    return () => { cancelled = true; };
  }, [activeKeyId, adminApi]);

  function updateModel(alias: string, patch: Partial<ProjectModel>) {
    setModels((current) => current.map((item) => item.model === alias ? { ...item, ...patch } : item));
  }

  async function saveProjectModels() {
    setBusy("project-models");
    setError("");
    setMessage("");
    try {
      const bindings = models.filter((item) => item.enabled).map((item) => ({ model: item.model, channelId: item.channelId, upstreamModel: item.upstreamModel, enabled: true }));
      await adminApi(`/api/internal/project/${encodeURIComponent(activeProjectName)}/models`, { method: "PUT", body: JSON.stringify({ bindings }) });
      setMessage("项目模型绑定已保存，现有业务 Key 无需更换");
      await loadProject();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "项目模型保存失败");
    } finally {
      setBusy("");
    }
  }

  async function saveKeyModels() {
    if (!activeKeyId) return;
    setBusy("key-models");
    setError("");
    setMessage("");
    try {
      await adminApi(`/api/internal/apikey/${encodeURIComponent(activeKeyId)}/models`, { method: "PUT", body: JSON.stringify({ models: keyModels.filter((item) => item.enabled).map((item) => item.model) }) });
      setMessage("API Key模型权限已立即生效");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Key模型权限保存失败");
    } finally {
      setBusy("");
    }
  }

  return <div className="content modelRelayPanel">
    <section className="panel relayIntro"><div><span><ServerCog size={20} /></span><div><h3>多供应商模型中转</h3><p>项目选择真实供应商渠道，业务 Key 只获得明确授权的模型别名。未绑定、未授权或渠道禁用时默认拒绝。</p></div></div><label>当前项目<select value={activeProjectName} onChange={(event) => { setProjectName(event.target.value); setKeyId(""); }}>{projects.map((project) => <option key={project.name} value={project.name}>{project.displayName} · {project.name}</option>)}</select></label></section>
    {error && <div className="errorBanner">{error}</div>}
    {message && <div className="successBanner"><Check size={16} />{message}</div>}

    <section className="panel"><div className="panelHead"><div><h3>项目模型绑定</h3><p>一个项目模型仅绑定一个活动渠道；真实模型 ID 从供应商控制台复制，不在系统中猜测。</p></div><button className="primary" onClick={() => void saveProjectModels()} disabled={Boolean(busy) || !activeProjectName}><Save size={15} />{busy === "project-models" ? "保存中" : "保存绑定"}</button></div>
      <div className="relayModelList">{models.map((model) => {
        const candidates = channels.filter((channel) => channel.provider === model.provider && channel.status === "active");
        return <article key={model.model} className={model.enabled ? "enabled" : ""}><div className="relayToggle"><input aria-label={`启用${model.displayName}`} type="checkbox" checked={model.enabled} onChange={(event) => updateModel(model.model, { enabled: event.target.checked })} /><span><b>{model.displayName}</b><small><code>{model.model}</code> · {model.modality} · {providerLabel[model.provider] || model.provider}</small></span></div><select aria-label={`${model.displayName}渠道`} disabled={!model.enabled} value={model.channelId || ""} onChange={(event) => updateModel(model.model, { channelId: event.target.value })}><option value="">选择渠道</option>{candidates.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}</select><input aria-label={`${model.displayName}真实模型ID`} disabled={!model.enabled} value={model.upstreamModel || ""} onChange={(event) => updateModel(model.model, { upstreamModel: event.target.value })} placeholder="真实上游模型 ID" /></article>;
      })}{!loading && catalog.length > 0 && models.length === 0 && <div className="emptyRow">目录已加载，但项目模型状态为空，请刷新重试。</div>}</div>
    </section>

    <section className="panel"><div className="panelHead"><div><h3>API Key 模型权限</h3><p>权限可随时追加或撤销，无需重新生成客户 Key。</p></div><button className="primary" onClick={() => void saveKeyModels()} disabled={Boolean(busy) || !activeKeyId}><Save size={15} />{busy === "key-models" ? "保存中" : "保存权限"}</button></div><div className="relayKeyPicker"><label>业务 Key<select value={activeKeyId} onChange={(event) => setKeyId(event.target.value)}><option value="">选择 Key</option>{projectKeys.map((key) => <option key={key.id} value={key.id}>{key.name} · {key.keyPrefix}</option>)}</select></label><div className="relayPermissionGrid">{keyModels.map((model) => <div key={model.model}><input aria-label={`授权${model.displayName}`} type="checkbox" checked={model.enabled} onChange={(event) => setKeyModels((current) => current.map((item) => item.model === model.model ? { ...item, enabled: event.target.checked } : item))} /><span><b>{model.displayName}</b><small>{model.model}</small></span></div>)}{activeKeyId && !keyModels.length && <div className="emptyRow">请先为项目启用至少一个模型。</div>}</div></div></section>

    <section className="panel"><div className="panelHead"><div><h3>中转用量与任务</h3><p>只记录供应商真实返回的 Token、图片数和视频时长；未知值保持为空。</p></div><button className="iconButton" onClick={() => void loadProject()} disabled={loading} aria-label="刷新中转用量"><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div><div className="relayFilters"><select aria-label="按模型筛选" value={modelFilter} onChange={(event) => setModelFilter(event.target.value)}><option value="">全部模型</option>{catalog.map((model) => <option key={model.id} value={model.id}>{model.displayName}</option>)}</select><select aria-label="按供应商筛选" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="">全部供应商</option>{Object.entries(providerLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input aria-label="用量开始时间" type="datetime-local" value={startTime} onChange={(event) => setStartTime(event.target.value)} /><input aria-label="用量结束时间" type="datetime-local" value={endTime} onChange={(event) => setEndTime(event.target.value)} /></div><div className="dataTable relayUsageTable"><div className="tableRow tableHead"><span>时间</span><span>模型 / 供应商</span><span>业务 Key</span><span>真实用量</span><span>状态</span></div>{usage.map((item) => <div className="tableRow" key={item.id}><span>{item.createdAt}</span><div><b>{item.model}</b><small>{providerLabel[item.provider] || item.provider}</small></div><code>{apiKeys.find((key) => key.id === item.apiKeyId)?.name || item.apiKeyId.slice(0, 8)}</code><span>{item.inputTokens != null || item.outputTokens != null ? `${item.inputTokens ?? "—"} / ${item.outputTokens ?? "—"} tokens` : item.generatedImages != null ? `${item.generatedImages} 张图片` : item.videoSeconds != null ? `${item.videoSeconds} 秒视频` : "未返回"}</span><i className={item.status}>{item.status}</i></div>)}{!loading && !usage.length && <div className="emptyRow">当前筛选条件下暂无中转用量。</div>}</div><div className="relayTaskStrip"><Activity size={15} /><span>最近任务</span>{tasks.slice(0, 8).map((task) => <code key={task.id}>{task.model} · {task.status}{task.progress != null ? ` ${task.progress}%` : ""}</code>)}{!tasks.length && <small>暂无异步任务</small>}</div></section>
  </div>;
}
