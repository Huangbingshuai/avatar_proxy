"use client";

import {
  Activity,
  Ban,
  BookOpen,
  Clipboard,
  FolderKanban,
  Gauge,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldCheck,
  Sparkles,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

type Project = {
  name: string;
  displayName: string;
  description: string;
  keyCount: number;
  activeKeyCount: number;
};

type ApiKey = {
  id: string;
  name: string;
  keyPrefix: string;
  projectName: string;
  status: "active" | "disabled";
  createdAt: string;
  lastUsedAt?: string;
};

type Overview = {
  stats: { projects: number; activeKeys: number; requests24h: number; errors24h: number };
  recent: Array<{ action: string; projectName: string; statusCode: number; durationMs: number; createdAt: string }>;
};

type VideoTask = {
  id: string;
  status: string;
  model?: string;
  created_at?: number;
  updated_at?: number;
  error?: { code?: string; message?: string };
  content?: { video_url?: string; last_frame_url?: string };
  output?: { video_url?: string };
  video_url?: string;
};

type Tab = "overview" | "projects" | "keys" | "playground" | "integration";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const DEFAULT_MODEL = "doubao-seedance-2-0-260128";
const DEFAULT_PROJECT_NAME = "avatar-proxy";
const RUNNING_STATUSES = new Set(["queued", "running"]);

const tabs: Array<{ id: Tab; label: string; icon: typeof Gauge }> = [
  { id: "overview", label: "概览", icon: Gauge },
  { id: "projects", label: "项目", icon: FolderKanban },
  { id: "keys", label: "API Keys", icon: KeyRound },
  { id: "playground", label: "视频调试", icon: Video },
  { id: "integration", label: "接入说明", icon: BookOpen },
];

function errorMessage(value: unknown, fallback = "请求失败") {
  if (!value || typeof value !== "object") return fallback;
  const data = value as { error?: { message?: string }; detail?: string; message?: string };
  return data.error?.message || data.detail || data.message || fallback;
}

function normalizeAssetUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed) || trimmed.startsWith("asset://")) return trimmed;
  return `asset://${trimmed}`;
}

function videoUrl(task: VideoTask | null) {
  return task?.content?.video_url || task?.output?.video_url || task?.video_url || "";
}

function formatTime(value?: string) {
  if (!value) return "从未";
  const normalized = value.endsWith("Z") ? value : `${value}Z`;
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(normalized));
}

export default function ConsolePage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [adminToken, setAdminToken] = useState("");
  const [tokenDraft, setTokenDraft] = useState("");
  const [locked, setLocked] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [secret, setSecret] = useState("");
  const [projectForm, setProjectForm] = useState({ name: "", displayName: "", description: "" });
  const [keyForm, setKeyForm] = useState({ name: "", projectName: DEFAULT_PROJECT_NAME });
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState(false);

  const adminApi = useCallback(async (path: string, init?: RequestInit, token = adminToken) => {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", "x-admin-token": token, ...init?.headers },
    });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(data));
    return data as Record<string, unknown>;
  }, [adminToken]);

  const loadAll = useCallback(async (token = adminToken) => {
    setLoading(true);
    setError("");
    try {
      const [projectData, keyData, overviewData] = await Promise.all([
        adminApi("/api/internal/project/list", undefined, token),
        adminApi("/api/internal/apikey/list", undefined, token),
        adminApi("/api/internal/overview", undefined, token),
      ]);
      setProjects(projectData.projects as Project[]);
      setApiKeys(keyData.apiKeys as ApiKey[]);
      setOverview(overviewData as unknown as Overview);
      setLocked(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "控制台加载失败");
      setLocked(true);
    } finally {
      setLoading(false);
    }
  }, [adminApi, adminToken]);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setAdminToken(tokenDraft);
    await loadAll(tokenDraft);
  }

  async function createProject(event: FormEvent) {
    event.preventDefault();
    try {
      await adminApi("/api/internal/project/create", { method: "POST", body: JSON.stringify(projectForm) });
      setProjectForm({ name: "", displayName: "", description: "" });
      setShowProjectForm(false);
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建项目失败");
    }
  }

  async function deleteProject() {
    if (!projectToDelete || deletingProject) return;
    setDeletingProject(true);
    setError("");
    try {
      await adminApi("/api/internal/project/delete", {
        method: "DELETE",
        body: JSON.stringify({ name: projectToDelete.name }),
      });
      setProjectToDelete(null);
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除项目失败");
    } finally {
      setDeletingProject(false);
    }
  }

  async function createKey(event: FormEvent) {
    event.preventDefault();
    try {
      const data = await adminApi("/api/internal/apikey/create", { method: "POST", body: JSON.stringify(keyForm) });
      setSecret(data.secret as string);
      setKeyForm({ name: "", projectName: DEFAULT_PROJECT_NAME });
      setShowKeyForm(false);
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成 API Key 失败");
    }
  }

  async function disableKey(id: string) {
    if (!window.confirm("禁用后，使用该 Key 的请求会立即失败。确认禁用？")) return;
    try {
      await adminApi("/api/internal/apikey/disable", { method: "PUT", body: JSON.stringify({ keyId: id }) });
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "禁用失败");
    }
  }

  async function enableKey(key: ApiKey) {
    if (key.status !== "disabled") return;
    if (!window.confirm(`确认重新启用 API Key“${key.name}”？\n\n用户持有的原完整 Key 将立即恢复访问权限。`)) return;
    try {
      await adminApi("/api/internal/apikey/enable", {
        method: "PUT",
        body: JSON.stringify({ keyId: key.id }),
      });
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重新启用失败");
    }
  }

  async function deleteKey(key: ApiKey) {
    if (key.status !== "disabled") return;
    setError("");
    try {
      await adminApi("/api/internal/apikey/delete", {
        method: "DELETE",
        body: JSON.stringify({ keyId: key.id }),
      });
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除 API Key 失败");
    }
  }

  async function bindProject(id: string, projectName: string) {
    try {
      await adminApi("/api/internal/apikey/bind-project", { method: "POST", body: JSON.stringify({ keyId: id, projectName }) });
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "绑定项目失败");
    }
  }

  return (
    <main className="consoleShell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark"><img src="/ruichi-logo.jpg" alt="" /></span>
          <div><strong>Avatar Proxy</strong><small>内部控制台</small></div>
        </div>
        <nav aria-label="控制台导航">
          {tabs.map((item) => {
            const Icon = item.icon;
            return <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}><Icon size={18} />{item.label}</button>;
          })}
        </nav>
        <div className="sidebarFoot">
          <span className="onlineDot" />
          <div><b>独立 API 服务</b><small>{API_BASE_URL}</small></div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">INTERNAL CONTROL PLANE</p><h1>{tabs.find((item) => item.id === tab)?.label}</h1></div>
          <div className="topbarActions"><span className="securePill"><ShieldCheck size={15} />服务端凭证已隔离</span><button className="iconButton" onClick={() => void loadAll()} disabled={loading} aria-label="刷新"><RefreshCw size={17} className={loading ? "spin" : ""} /></button></div>
        </header>

        {error && !locked && <div className="errorBanner"><Ban size={17} />{error}<button onClick={() => setError("")} aria-label="关闭"><X size={15} /></button></div>}

        {tab === "overview" && <OverviewPanel overview={overview} onOpenPlayground={() => setTab("playground")} />}
        {tab === "projects" && <ProjectsPanel projects={projects} onCreate={() => setShowProjectForm(true)} onDelete={setProjectToDelete} />}
        {tab === "keys" && <KeysPanel apiKeys={apiKeys} projects={projects} onCreate={() => setShowKeyForm(true)} onDisable={disableKey} onEnable={enableKey} onDelete={deleteKey} onBind={bindProject} />}
        {tab === "playground" && <VideoPlayground />}
        {tab === "integration" && <IntegrationPanel />}
      </section>

      {locked && <div className="modalBackdrop"><form className="unlockCard" onSubmit={unlock}>
        <span className="lockMark"><LockKeyhole size={24} /></span><p className="eyebrow">SECURE CONSOLE</p><h2>解锁内部控制台</h2>
        <p>输入 API 服务器部署时配置的管理令牌。令牌仅保存在当前页面内存中。</p>
        <label>管理令牌<input type="password" autoComplete="current-password" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} placeholder="CONSOLE_ADMIN_TOKEN" /></label>
        {error && <div className="formError">{error}</div>}
        <button className="primary wide" disabled={!tokenDraft || loading}>{loading ? <><LoaderCircle size={17} className="spin" />验证中</> : "进入控制台"}</button>
      </form></div>}

      {showProjectForm && <Modal title="新建项目" onClose={() => setShowProjectForm(false)}><form onSubmit={createProject} className="stackForm">
        <label>显示名称<input required value={projectForm.displayName} onChange={(event) => setProjectForm({ ...projectForm, displayName: event.target.value })} placeholder="短剧生产" /></label>
        <label>火山 ProjectName<input required value={projectForm.name} onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })} placeholder="drama_prod" /></label>
        <label>描述<textarea value={projectForm.description} onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })} placeholder="用于生产环境的人像素材与视频任务" /></label>
        <button className="primary wide">创建项目</button>
      </form></Modal>}

      {projectToDelete && <Modal title="删除项目" onClose={() => { if (!deletingProject) setProjectToDelete(null); }}>
        <div className="deleteProjectConfirm">
          <span className="deleteProjectMark"><Trash2 size={22} /></span>
          <div>
            <h3>确认删除“{projectToDelete.displayName}”？</h3>
            <p>项目标识：<code>{projectToDelete.name}</code></p>
          </div>
          {projectToDelete.keyCount > 0 && <div className="note">关联的 {projectToDelete.keyCount} 个 API Key 将迁移到 <code>{DEFAULT_PROJECT_NAME}</code>，不会失效。</div>}
          <p className="deleteProjectHint">此操作只删除本系统中的项目映射，不会删除火山控制台中的真实项目。</p>
          <div className="modalActions">
            <button type="button" className="secondary" onClick={() => setProjectToDelete(null)} disabled={deletingProject}>取消</button>
            <button type="button" className="dangerButton" onClick={() => void deleteProject()} disabled={deletingProject}>
              {deletingProject ? <><LoaderCircle size={16} className="spin" />删除中</> : <><Trash2 size={16} />确认删除</>}
            </button>
          </div>
        </div>
      </Modal>}

      {showKeyForm && <Modal title="生成业务 API Key" onClose={() => setShowKeyForm(false)}><form onSubmit={createKey} className="stackForm">
        <label>Key 名称<input required value={keyForm.name} onChange={(event) => setKeyForm({ ...keyForm, name: event.target.value })} placeholder="customer-production" /></label>
        <label>绑定项目<select required value={keyForm.projectName} onChange={(event) => setKeyForm({ ...keyForm, projectName: event.target.value })}><option value="">选择项目</option>{projects.map((project) => <option key={project.name} value={project.name}>{project.displayName} · {project.name}</option>)}</select></label>
        <div className="note">用户只获得这一枚业务 Key，不会接触火山 AK/SK 或方舟 API Key。</div>
        <button className="primary wide">生成 API Key</button>
      </form></Modal>}

      {secret && <Modal title="立即保存 API Key" onClose={() => setSecret("")}><div className="secretBox">
        <p>完整 Key 只显示一次。请通过安全渠道交付给用户。</p><code>{secret}</code>
        <button className="primary wide" onClick={() => void navigator.clipboard.writeText(secret)}><Clipboard size={17} />复制 API Key</button>
      </div></Modal>}
    </main>
  );
}

function OverviewPanel({ overview, onOpenPlayground }: { overview: Overview | null; onOpenPlayground: () => void }) {
  return <div className="content">
    <section className="overviewHero">
      <div><span className="heroTag">CONTROL PLANE</span><h2>控制台与公网 API<br />保持独立部署</h2><p>这里管理项目和业务 API Key。用户使用签发的 Key 直接请求独立 FastAPI 服务。</p><button className="primary" onClick={onOpenPlayground}><Play size={17} />测试视频接口</button></div>
      <div className="architectureCard"><div><span><ShieldCheck size={18} /></span><div><b>内部控制台</b><small>X-Admin-Token</small></div></div><i /><div><span><Server size={18} /></span><div><b>公网 API 服务器</b><small>Bearer vap_live_...</small></div></div><i /><div><span><Sparkles size={18} /></span><div><b>火山服务</b><small>服务端 AK/SK · Ark Key</small></div></div></div>
    </section>
    <div className="statGrid">
      <Stat label="项目" value={overview?.stats.projects ?? 0} note="映射火山 ProjectName" />
      <Stat label="有效 API Keys" value={overview?.stats.activeKeys ?? 0} note="仅保存 SHA-256 哈希" />
      <Stat label="24h 请求" value={overview?.stats.requests24h ?? 0} note="公网业务接口" />
      <Stat label="24h 异常" value={overview?.stats.errors24h ?? 0} note="上游与鉴权错误" warn={Boolean(overview?.stats.errors24h)} />
    </div>
    <section className="panel"><div className="panelHead"><div><h3>最近请求</h3><p>记录项目、操作与状态，不保存业务请求体。</p></div></div>
      <div className="dataTable recentTable"><div className="tableRow tableHead"><span>操作</span><span>项目</span><span>状态</span><span>耗时</span><span>时间</span></div>{overview?.recent.length ? overview.recent.map((row, index) => <div className="tableRow" key={`${row.createdAt}-${index}`}><span className="mono">{row.action}</span><span>{row.projectName}</span><span><i className={`httpStatus ${row.statusCode < 400 ? "ok" : "bad"}`}>{row.statusCode}</i></span><span>{row.durationMs} ms</span><span>{formatTime(row.createdAt)}</span></div>) : <div className="emptyRow">暂无调用记录</div>}</div>
    </section>
  </div>;
}

function ProjectsPanel({ projects, onCreate, onDelete }: { projects: Project[]; onCreate: () => void; onDelete: (project: Project) => void }) {
  return <div className="content"><div className="pageIntro"><div><h2>项目隔离</h2><p>项目名必须是火山方舟控制台中真实存在的 ProjectName。</p></div><button className="primary" onClick={onCreate}><Plus size={17} />新建项目</button></div>
    <div className="cardGrid">{projects.map((project) => <article className="projectCard" key={project.name}><div className="projectTop"><span className="projectIcon">{project.displayName.slice(0, 1).toUpperCase()}</span><div><h3>{project.displayName}</h3><code>{project.name}</code></div>{project.name === DEFAULT_PROJECT_NAME ? <span className="defaultProjectBadge">默认</span> : <button className="projectDelete" type="button" onClick={() => void onDelete(project)} aria-label={`删除项目 ${project.displayName}`}><Trash2 size={15} /></button>}</div><p>{project.description || "暂无描述"}</p><footer><span>{project.activeKeyCount || 0} 个有效 Key</span><span>{project.keyCount || 0} 个 Key</span></footer></article>)}{!projects.length && <Empty text="还没有项目，请先创建并填写真实的火山 ProjectName。" />}</div>
  </div>;
}

function KeysPanel({ apiKeys, projects, onCreate, onDisable, onEnable, onDelete, onBind }: { apiKeys: ApiKey[]; projects: Project[]; onCreate: () => void; onDisable: (id: string) => Promise<void>; onEnable: (key: ApiKey) => Promise<void>; onDelete: (key: ApiKey) => Promise<void>; onBind: (id: string, project: string) => Promise<void> }) {
  return <div className="content"><div className="pageIntro"><div><h2>用户 API Keys</h2><p>把生成的 `vap_live_...` 交给用户；完整 Key 只显示一次。</p></div><button className="primary" onClick={onCreate} disabled={!projects.length}><Plus size={17} />生成 API Key</button></div>
    <section className="panel"><div className="dataTable keyTable"><div className="tableRow tableHead"><span>名称</span><span>Key</span><span>绑定项目</span><span>最近使用</span><span>状态</span><span /></div>{apiKeys.map((key) => <div className="tableRow" key={key.id}><span><b>{key.name}</b><small>{formatTime(key.createdAt)} 创建</small></span><span className="mono">{key.keyPrefix}</span><span><select className="inlineSelect" value={key.projectName} disabled={key.status !== "active"} onChange={(event) => void onBind(key.id, event.target.value)}>{projects.map((project) => <option key={project.name} value={project.name}>{project.name}</option>)}</select></span><span>{formatTime(key.lastUsedAt)}</span><span><i className={`state ${key.status}`}>{key.status === "active" ? "有效" : "已禁用"}</i></span><span className="keyActions">{key.status === "active" ? <button type="button" className="dangerLink" onClick={() => void onDisable(key.id)}>禁用</button> : <><button type="button" className="enableKeyButton" onClick={() => void onEnable(key)}><RotateCcw size={14} />启用</button><button type="button" className="deleteKeyButton" onClick={() => void onDelete(key)}><Trash2 size={14} />删除</button></>}</span></div>)}{!apiKeys.length && <div className="emptyRow">暂无 API Key</div>}</div></section>
  </div>;
}

function VideoPlayground() {
  const [apiKey, setApiKey] = useState("");
  const [prompt, setPrompt] = useState("一只橘猫坐在窗边看雨，镜头缓慢推进，电影感光影，画面稳定");
  const [asset, setAsset] = useState("");
  const [ratio, setRatio] = useState("16:9");
  const [duration, setDuration] = useState("5");
  const [generateAudio, setGenerateAudio] = useState(true);
  const [taskIdDraft, setTaskIdDraft] = useState("");
  const [task, setTask] = useState<VideoTask | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const userApi = useCallback(async (path: string, init?: RequestInit) => {
    if (!apiKey.trim()) throw new Error("请先输入业务 API Key");
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", Authorization: `Bearer ${apiKey.trim()}`, ...init?.headers },
    });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(data, `请求失败（${response.status}）`));
    return data as VideoTask;
  }, [apiKey]);

  const refreshTask = useCallback(async (id = task?.id) => {
    if (!id) return;
    try {
      const data = await userApi(`/api/video/task/${encodeURIComponent(id)}`);
      setTask(data);
      setTaskIdDraft(data.id || id);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "查询任务失败");
    }
  }, [task?.id, userApi]);

  useEffect(() => {
    if (!task?.id || !RUNNING_STATUSES.has(task.status)) return;
    const timer = window.setInterval(() => void refreshTask(task.id), 8000);
    return () => window.clearInterval(timer);
  }, [refreshTask, task?.id, task?.status]);

  const content = useMemo(() => {
    const items: Array<Record<string, unknown>> = [{ type: "text", text: prompt.trim() }];
    const reference = normalizeAssetUrl(asset);
    if (reference) items.push({ type: "image_url", image_url: { url: reference } });
    return items;
  }, [asset, prompt]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const data = await userApi("/api/video/generate", { method: "POST", body: JSON.stringify({ model: DEFAULT_MODEL, content, ratio, duration: Number(duration), generateAudio, returnLastFrame: false }) });
      setTask(data);
      setTaskIdDraft(data.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建视频任务失败");
    } finally {
      setPending(false);
    }
  }

  async function cancel() {
    if (!task?.id) return;
    setPending(true);
    try {
      await userApi(`/api/video/task/${encodeURIComponent(task.id)}/cancel`, { method: "POST" });
      await refreshTask(task.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "取消任务失败");
    } finally {
      setPending(false);
    }
  }

  const output = videoUrl(task);
  return <div className="content playgroundLayout">
    <section className="toolPanel"><div className="panelHead"><div><h2>Seedance 2.0 视频调试</h2><p>此页面仅供内部验收，调用的是独立公网 API 服务。</p></div><span className="modelBadge">{DEFAULT_MODEL}</span></div>
      <form className="generatorForm" onSubmit={generate}>
        <label>业务 API Key<input type="password" autoComplete="off" required value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="vap_live_..." /></label>
        <label>提示词<textarea required minLength={2} value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={6} /></label>
        <label>参考素材 ID 或图片 URL（可选）<input value={asset} onChange={(event) => setAsset(event.target.value)} placeholder="asset-2026... 或 https://..." /><small>素材 ID 会自动转换为 asset://asset-2026...，不要重复添加 asset- 前缀。</small></label>
        <div className="formGrid"><label>画面比例<select value={ratio} onChange={(event) => setRatio(event.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option><option>4:3</option><option>3:4</option></select></label><label>时长<select value={duration} onChange={(event) => setDuration(event.target.value)}><option value="5">5 秒</option><option value="10">10 秒</option></select></label></div>
        <label className="toggleRow"><input aria-label="生成音频" type="checkbox" checked={generateAudio} onChange={(event) => setGenerateAudio(event.target.checked)} /><span><b>生成音频</b><small>由 Seedance 根据画面和提示词生成声音</small></span></label>
        {error && <div className="formError">{error}</div>}
        <button className="primary wide" disabled={pending || !prompt.trim() || !apiKey.trim()}>{pending ? <><LoaderCircle size={17} className="spin" />提交中</> : <><Sparkles size={17} />创建视频任务</>}</button>
      </form>
    </section>

    <aside className="taskPanel"><div className="panelHead"><div><h3>任务状态</h3><p>运行中每 8 秒自动刷新。</p></div>{task?.status && <i className={`taskStatus ${task.status}`}>{task.status}</i>}</div>
      <div className="resumeRow"><input value={taskIdDraft} onChange={(event) => setTaskIdDraft(event.target.value)} placeholder="输入已有 taskId" /><button className="secondary" disabled={!taskIdDraft || !apiKey} onClick={() => void refreshTask(taskIdDraft)}><RotateCcw size={16} />查询</button></div>
      {!task && <div className="taskEmpty"><Video size={34} /><h4>还没有视频任务</h4><p>左侧创建任务，或输入已有 taskId 继续查询。</p></div>}
      {task && <div className="taskResult">
        <div className="taskMeta"><span>任务 ID</span><code>{task.id}</code><span>模型</span><code>{task.model || DEFAULT_MODEL}</code></div>
        {RUNNING_STATUSES.has(task.status) && <div className="progressCard"><LoaderCircle size={22} className="spin" /><div><b>{task.status === "queued" ? "等待调度" : "正在生成视频"}</b><p>任务由火山方舟异步处理，可以离开页面后用 taskId 继续查询。</p></div></div>}
        {task.status === "failed" && <div className="errorCard"><Ban size={20} /><div><b>{task.error?.code || "生成失败"}</b><p>{task.error?.message || "请检查模型、素材权限和提示词后重试。"}</p></div></div>}
        {output && <div className="videoResult">
          {/* Generated videos do not provide a separate caption track. */}
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video aria-label="生成的视频" controls playsInline src={output} />
          <a className="secondary" href={output} target="_blank" rel="noreferrer">打开视频文件</a>
        </div>}
        <div className="taskActions"><button className="secondary" onClick={() => void refreshTask()}><RefreshCw size={16} />刷新状态</button>{RUNNING_STATUSES.has(task.status) && <button className="dangerButton" disabled={pending} onClick={() => void cancel()}><Ban size={16} />取消任务</button>}</div>
      </div>}
    </aside>
  </div>;
}

function IntegrationPanel() {
  const curl = `curl -X POST '${API_BASE_URL}/api/video/generate' \\\n+  -H 'Authorization: Bearer vap_live_xxx' \\\n+  -H 'Content-Type: application/json' \\\n+  -d '{\n    "model": "${DEFAULT_MODEL}",\n    "content": [{"type":"text","text":"一只橘猫坐在窗边看雨"}],\n    "ratio": "16:9",\n    "duration": 5,\n    "generateAudio": true\n  }'`;
  return <div className="content"><div className="pageIntro"><div><h2>交付给 API 用户</h2><p>用户只需要公网服务地址和业务 API Key，不需要控制台账号。</p></div><span className="version">API v1</span></div>
    <section className="integrationGrid"><article className="panel docCard"><span className="step">1</span><h3>创建视频任务</h3><pre>{curl}</pre></article><article className="panel docCard"><span className="step">2</span><h3>查询任务</h3><pre>{`GET ${API_BASE_URL}/api/video/task/{taskId}\nAuthorization: Bearer vap_live_xxx`}</pre><p>状态为 <code>succeeded</code> 后读取返回的视频 URL。</p></article><article className="panel docCard"><span className="step">3</span><h3>取消任务</h3><pre>{`POST ${API_BASE_URL}/api/video/task/{taskId}/cancel\nAuthorization: Bearer vap_live_xxx`}</pre><p>建议只对 <code>queued</code> 或 <code>running</code> 状态调用。</p></article></section>
    <section className="deploymentNote"><Server size={21} /><div><h3>独立部署约束</h3><p>控制台构建时设置 <code>NEXT_PUBLIC_API_BASE_URL</code>；API 服务器设置 <code>CORS_ORIGINS</code> 为控制台域名。火山凭证只能配置在 API 服务器。</p></div></section>
  </div>;
}

function Stat({ label, value, note, warn }: { label: string; value: number; note: string; warn?: boolean }) {
  return <article className="stat"><div><span>{label}</span><Activity size={17} className={warn ? "warn" : ""} /></div><strong>{value.toLocaleString()}</strong><small>{note}</small></article>;
}

function Empty({ text }: { text: string }) {
  return <div className="emptyCard"><FolderKanban size={29} /><p>{text}</p></div>;
}

function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return <div className="modalBackdrop"><section className="modal"><header><h2>{title}</h2><button type="button" onClick={onClose} aria-label="关闭"><X size={19} /></button></header>{children}</section></div>;
}
