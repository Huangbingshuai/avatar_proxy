"use client";

import {
  Activity,
  AlertTriangle,
  Ban,
  BookOpen,
  Clipboard,
  FolderKanban,
  Gauge,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  UserRoundCog,
  Video,
  X,
} from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import AdminPanel from "./admin-panel";
import { AdminApiError, isPasswordChangeRequired, isSessionError, requestAdminApi, type AdminApi, type AdminUser } from "./admin-api";

type Project = {
  name: string;
  displayName: string;
  description: string;
  keyCount: number;
  activeKeyCount: number;
  activeAssetCount: number;
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
  stats: { projects: number; activeKeys: number; requests24h: number; errors24h: number; assetsToday: number; uploadsToday: number; uploadBytesToday: number; limitedProjects: number; openQuotaEvents: number; cleanupPending: number };
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

type QuotaValues = {
  enabled?: boolean;
  readQpm?: number | null;
  writeQpm?: number | null;
  maxConcurrency?: number | null;
  dailyAssetCreates?: number | null;
  dailyUploadFiles?: number | null;
  dailyUploadBytes?: number | null;
  totalAssets?: number | null;
  totalStorageBytes?: number | null;
};

type QuotaEvent = {
  id: number;
  projectName: string;
  apiKeyId?: string;
  scopeType: string;
  metric: string;
  threshold: number;
  limitValue: number;
  usedValue: number;
  acknowledged: boolean;
  createdAt: string;
};

type QuotaAudit = {
  id: number;
  sourceIp?: string;
  action: string;
  targetType: string;
  targetId: string;
  createdAt: string;
};

type CleanupObject = {
  recordId: string;
  objectKey: string;
  sizeBytes: number;
  status: string;
  cleanupAttempts: number;
  lastError?: string;
  createdAt: string;
};

type QuotaUsage = {
  projectName: string;
  quota: QuotaValues;
  usage: Record<string, number>;
  cleanupObjects: CleanupObject[];
};

type Tab = "overview" | "projects" | "keys" | "quotas" | "playground" | "integration" | "admins";
type AuthStatus = "checking" | "anonymous" | "password_change_required" | "authenticated";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const DEFAULT_MODEL = "doubao-seedance-2-0-260128";
const RUNNING_STATUSES = new Set(["queued", "running"]);

const baseTabs: Array<{ id: Tab; label: string; icon: typeof Gauge }> = [
  { id: "overview", label: "概览", icon: Gauge },
  { id: "projects", label: "项目", icon: FolderKanban },
  { id: "keys", label: "API Keys", icon: KeyRound },
  { id: "quotas", label: "额度与用量", icon: SlidersHorizontal },
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
  const [authStatus, setAuthStatus] = useState<AuthStatus>("checking");
  const [currentUser, setCurrentUser] = useState<AdminUser | null>(null);
  const [csrfToken, setCsrfToken] = useState("");
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [passwordForm, setPasswordForm] = useState({ currentPassword: "", newPassword: "", confirmPassword: "" });
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [quotaEvents, setQuotaEvents] = useState<QuotaEvent[]>([]);
  const [quotaAudits, setQuotaAudits] = useState<QuotaAudit[]>([]);
  const [secret, setSecret] = useState("");
  const [projectForm, setProjectForm] = useState({ name: "", displayName: "", description: "" });
  const [keyForm, setKeyForm] = useState({ name: "", projectName: "" });
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [projectCreateError, setProjectCreateError] = useState("");
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState(false);

  const tabs = useMemo(() => currentUser?.role === "super_admin"
    ? [...baseTabs, { id: "admins" as Tab, label: "管理员", icon: UserRoundCog }]
    : baseTabs, [currentUser?.role]);

  const clearSession = useCallback((message = "") => {
    setCurrentUser(null);
    setCsrfToken("");
    setProjects([]);
    setApiKeys([]);
    setOverview(null);
    setQuotaEvents([]);
    setQuotaAudits([]);
    setSecret("");
    setShowPasswordForm(false);
    setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
    setTab("overview");
    setAuthMessage(message);
    setAuthStatus("anonymous");
  }, []);

  const adminApi = useCallback<AdminApi>(async (path, init) => {
    try {
      return await requestAdminApi(path, init, csrfToken);
    } catch (caught) {
      if (isSessionError(caught)) clearSession("登录会话已过期，请重新登录");
      else if (isPasswordChangeRequired(caught)) setAuthStatus("password_change_required");
      throw caught;
    }
  }, [clearSession, csrfToken]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [projectData, keyData, overviewData, eventData, auditData] = await Promise.all([
        adminApi("/api/internal/project/list"),
        adminApi("/api/internal/apikey/list"),
        adminApi("/api/internal/overview"),
        adminApi("/api/internal/quota/events?limit=100"),
        adminApi("/api/internal/quota/audits?limit=100"),
      ]);
      setProjects(projectData.projects as Project[]);
      setApiKeys(keyData.apiKeys as ApiKey[]);
      setOverview(overviewData as unknown as Overview);
      setQuotaEvents(eventData.events as QuotaEvent[]);
      setQuotaAudits(auditData.audits as QuotaAudit[]);
    } catch (caught) {
      if (!isSessionError(caught) && !isPasswordChangeRequired(caught)) setError(caught instanceof Error ? caught.message : "控制台加载失败");
    } finally {
      setLoading(false);
    }
  }, [adminApi]);

  useEffect(() => {
    let cancelled = false;
    void requestAdminApi("/api/internal/auth/me").then((data) => {
      if (cancelled) return;
      const user = data.user as AdminUser;
      setCurrentUser(user);
      setCsrfToken(String(data.csrfToken ?? ""));
      setAuthStatus(user.mustChangePassword ? "password_change_required" : "authenticated");
    }).catch((caught) => {
      if (!cancelled) clearSession(caught instanceof AdminApiError && caught.status !== 401 ? caught.message : "");
    });
    return () => { cancelled = true; };
  }, [clearSession]);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    const timer = window.setTimeout(() => void loadAll(), 0);
    return () => window.clearTimeout(timer);
  }, [authStatus, loadAll]);

  async function login(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setAuthMessage("");
    try {
      const data = await requestAdminApi("/api/internal/auth/login", { method: "POST", body: JSON.stringify(loginForm) });
      const user = data.user as AdminUser;
      setCurrentUser(user);
      setCsrfToken(String(data.csrfToken ?? ""));
      setLoginForm((current) => ({ username: current.username, password: "" }));
      setAuthStatus(user.mustChangePassword ? "password_change_required" : "authenticated");
    } catch (caught) {
      if (caught instanceof AdminApiError && caught.retryAfter) setAuthMessage(`${caught.message}，请在 ${caught.retryAfter} 秒后重试`);
      else setAuthMessage(caught instanceof Error ? caught.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setAuthMessage("");
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setAuthMessage("两次输入的新密码不一致");
      return;
    }
    setLoading(true);
    try {
      await requestAdminApi("/api/internal/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ currentPassword: passwordForm.currentPassword, newPassword: passwordForm.newPassword }),
      }, csrfToken);
      setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
      setShowPasswordForm(false);
      clearSession("密码已修改，请使用新密码重新登录");
    } catch (caught) {
      if (isSessionError(caught)) clearSession("登录会话已过期，请重新登录");
      else setAuthMessage(caught instanceof Error ? caught.message : "密码修改失败");
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    try {
      await requestAdminApi("/api/internal/auth/logout", { method: "POST" }, csrfToken);
    } catch {
      // 本地状态必须立即失效；服务端会话仍受自身过期和撤销规则约束。
    } finally {
      clearSession("");
    }
  }

  async function createProject(event: FormEvent) {
    event.preventDefault();
    if (creatingProject) return;
    setCreatingProject(true);
    setProjectCreateError("");
    setError("");
    try {
      await adminApi("/api/internal/project/create", { method: "POST", body: JSON.stringify(projectForm) });
      setProjectForm({ name: "", displayName: "", description: "" });
      setShowProjectForm(false);
      await loadAll();
    } catch (caught) {
      setProjectCreateError(caught instanceof Error ? caught.message : "创建项目失败");
    } finally {
      setCreatingProject(false);
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
      setKeyForm({ name: "", projectName: "" });
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
          <div><b>业务 API 服务</b><small>{API_BASE_URL}</small></div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">INTERNAL CONTROL PLANE</p><h1>{tabs.find((item) => item.id === tab)?.label}</h1></div>
          <div className="topbarActions">
            {currentUser && <div className="adminIdentity"><span><b>{currentUser.displayName || currentUser.username}</b><small>{currentUser.role === "super_admin" ? "超级管理员" : "管理员"} · {currentUser.username}</small></span><button className="secondary" onClick={() => { setAuthMessage(""); setShowPasswordForm(true); }}>修改密码</button><button className="iconButton" onClick={() => void logout()} aria-label="退出登录" title="退出登录"><LogOut size={16} /></button></div>}
            <span className="securePill"><ShieldCheck size={15} />管理员会话已隔离</span><button className="iconButton" onClick={() => void loadAll()} disabled={loading || authStatus !== "authenticated"} aria-label="刷新"><RefreshCw size={17} className={loading ? "spin" : ""} /></button>
          </div>
        </header>

        {error && authStatus === "authenticated" && <div className="errorBanner"><Ban size={17} />{error}<button onClick={() => setError("")} aria-label="关闭"><X size={15} /></button></div>}

        {tab === "overview" && <OverviewPanel overview={overview} onOpenPlayground={() => setTab("playground")} />}
        {tab === "projects" && <ProjectsPanel projects={projects} onCreate={() => { setProjectCreateError(""); setError(""); setShowProjectForm(true); }} onDelete={setProjectToDelete} />}
        {tab === "keys" && <KeysPanel apiKeys={apiKeys} projects={projects} onCreate={() => { setKeyForm((current) => ({ ...current, projectName: current.projectName || projects[0]?.name || "" })); setShowKeyForm(true); }} onDisable={disableKey} onEnable={enableKey} onDelete={deleteKey} onBind={bindProject} />}
        {tab === "quotas" && <QuotaPanel projects={projects} apiKeys={apiKeys} events={quotaEvents} audits={quotaAudits} adminApi={adminApi} onChanged={() => loadAll()} />}
        {tab === "playground" && <VideoPlayground />}
        {tab === "integration" && <IntegrationPanel />}
        {tab === "admins" && currentUser?.role === "super_admin" && <AdminPanel currentUser={currentUser} adminApi={adminApi} />}
      </section>

      {authStatus === "checking" && <div className="modalBackdrop"><div className="unlockCard authChecking"><LoaderCircle size={27} className="spin" /><h2>正在验证会话</h2><p>请稍候，系统正在确认当前管理员身份。</p></div></div>}

      {authStatus === "anonymous" && <div className="modalBackdrop"><form className="unlockCard" onSubmit={login}>
        <span className="lockMark"><LockKeyhole size={24} /></span><p className="eyebrow">SECURE CONSOLE</p><h2>登录内部控制台</h2>
        <p>使用分配给你的管理员账号登录。账号停用或密码重置后，已有会话会立即失效。</p>
        <label>用户名<input type="text" autoComplete="username" required value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} placeholder="请输入管理员用户名" /></label>
        <label>密码<input type="password" autoComplete="current-password" required value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} placeholder="请输入密码" /></label>
        {authMessage && <div className="formError" role="alert">{authMessage}</div>}
        <button className="primary wide" disabled={!loginForm.username.trim() || !loginForm.password || loading}>{loading ? <><LoaderCircle size={17} className="spin" />登录中</> : "登录控制台"}</button>
      </form></div>}

      {(authStatus === "password_change_required" || showPasswordForm) && currentUser && <div className="modalBackdrop"><form className="unlockCard" onSubmit={changePassword}>
        <span className="lockMark"><KeyRound size={24} /></span><p className="eyebrow">ACCOUNT SECURITY</p><h2>{authStatus === "password_change_required" ? "首次登录，请修改密码" : "修改管理员密码"}</h2>
        <p>{authStatus === "password_change_required" ? "初始密码只能用于首次登录。修改成功后请使用新密码重新登录。" : "修改密码后，全部登录会话都会失效，请使用新密码重新登录。"}</p>
        <label>当前密码<input type="password" autoComplete="current-password" required value={passwordForm.currentPassword} onChange={(event) => setPasswordForm({ ...passwordForm, currentPassword: event.target.value })} /></label>
        <label>新密码<input type="password" autoComplete="new-password" required minLength={14} value={passwordForm.newPassword} onChange={(event) => setPasswordForm({ ...passwordForm, newPassword: event.target.value })} /><small>14～128 个字符，且不能与用户名相同。</small></label>
        <label>确认新密码<input type="password" autoComplete="new-password" required minLength={14} value={passwordForm.confirmPassword} onChange={(event) => setPasswordForm({ ...passwordForm, confirmPassword: event.target.value })} /></label>
        {authMessage && <div className="formError" role="alert">{authMessage}</div>}
        <div className="passwordActions">{authStatus !== "password_change_required" && <button type="button" className="secondary" onClick={() => { setShowPasswordForm(false); setAuthMessage(""); setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" }); }}>取消</button>}<button className="primary" disabled={loading}>{loading ? <><LoaderCircle size={17} className="spin" />保存中</> : "保存新密码"}</button></div>
      </form></div>}

      {showProjectForm && <Modal title="新建项目" onClose={() => { if (!creatingProject) setShowProjectForm(false); }}><form onSubmit={createProject} className="stackForm">
        <label>显示名称<input maxLength={64} value={projectForm.displayName} onChange={(event) => setProjectForm({ ...projectForm, displayName: event.target.value })} placeholder="短剧生产（选填，最多 64 个字符）" /></label>
        <label>火山 ProjectName<input required minLength={1} maxLength={64} pattern="[A-Za-z0-9._-]+" title="1～64 个字符，仅允许英文字母、数字、英文句点、下划线和连字符" value={projectForm.name} onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })} placeholder="例如 xinchuang8.0" /></label>
        <label>描述<textarea maxLength={128} value={projectForm.description} onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })} placeholder="选填，最多 128 个字符" /></label>
        <div className="note">创建前会由后端使用火山 AK/SK 校验资源项目；ProjectName 必须真实存在且大小写完全一致。</div>
        {projectCreateError && <div className="formError" role="alert">{projectCreateError}</div>}
        <button className="primary wide" disabled={creatingProject || !projectForm.name.trim()}>{creatingProject ? <><LoaderCircle size={17} className="spin" />正在校验火山项目</> : "创建项目"}</button>
      </form></Modal>}

      {projectToDelete && <Modal title="删除项目" onClose={() => { if (!deletingProject) setProjectToDelete(null); }}>
        <div className="deleteProjectConfirm">
          <span className="deleteProjectMark"><Trash2 size={22} /></span>
          <div>
            <h3>确认删除“{projectToDelete.displayName}”？</h3>
            <p>项目标识：<code>{projectToDelete.name}</code></p>
          </div>
          {projectToDelete.keyCount > 0 && <div className="note">该项目仍关联 {projectToDelete.keyCount} 个 API Key，因此不能删除。请先迁移这些 Key，或将其禁用后逐一删除。</div>}
          {projectToDelete.activeAssetCount > 0 && <div className="note">该项目仍有 {projectToDelete.activeAssetCount} 个未删除素材，请先完成删除和 TOS 清理。</div>}
          <p className="deleteProjectHint">此操作只删除本系统中的项目映射，不会删除火山控制台中的真实项目。</p>
          <div className="modalActions">
            <button type="button" className="secondary" onClick={() => setProjectToDelete(null)} disabled={deletingProject}>取消</button>
            <button type="button" className="dangerButton" onClick={() => void deleteProject()} disabled={deletingProject || projectToDelete.keyCount > 0 || projectToDelete.activeAssetCount > 0}>
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
      <div className="architectureCard"><div><span><ShieldCheck size={18} /></span><div><b>内部控制台</b><small>独立管理员会话 · 操作可审计</small></div></div><i /><div><span><Server size={18} /></span><div><b>公网 API 服务器</b><small>Bearer vap_live_...</small></div></div><i /><div><span><Sparkles size={18} /></span><div><b>火山服务</b><small>服务端 AK/SK · Ark Key</small></div></div></div>
    </section>
    <div className="statGrid">
      <Stat label="项目" value={overview?.stats.projects ?? 0} note="映射火山 ProjectName" />
      <Stat label="有效 API Keys" value={overview?.stats.activeKeys ?? 0} note="仅保存 SHA-256 哈希" />
      <Stat label="24h 请求" value={overview?.stats.requests24h ?? 0} note="公网业务接口" />
      <Stat label="24h 异常" value={overview?.stats.errors24h ?? 0} note="上游与鉴权错误" warn={Boolean(overview?.stats.errors24h)} />
    </div>
    <div className="statGrid riskStats">
      <Stat label="今日创建素材" value={overview?.stats.assetsToday ?? 0} note="北京时间自然日" />
      <Stat label="今日上传" value={overview?.stats.uploadsToday ?? 0} note={bytesLabel(overview?.stats.uploadBytesToday ?? 0)} />
      <Stat label="启用额度项目" value={overview?.stats.limitedProjects ?? 0} note="其余项目默认不限额" />
      <Stat label="未确认额度事件" value={overview?.stats.openQuotaEvents ?? 0} note={`${overview?.stats.cleanupPending ?? 0} 个对象待清理`} warn={Boolean(overview?.stats.openQuotaEvents || overview?.stats.cleanupPending)} />
    </div>
    <section className="panel"><div className="panelHead"><div><h3>最近请求</h3><p>记录项目、操作与状态，不保存业务请求体。</p></div></div>
      <div className="dataTable recentTable"><div className="tableRow tableHead"><span>操作</span><span>项目</span><span>状态</span><span>耗时</span><span>时间</span></div>{overview?.recent.length ? overview.recent.map((row, index) => <div className="tableRow" key={`${row.createdAt}-${index}`}><span className="mono">{row.action}</span><span>{row.projectName}</span><span><i className={`httpStatus ${row.statusCode < 400 ? "ok" : "bad"}`}>{row.statusCode}</i></span><span>{row.durationMs} ms</span><span>{formatTime(row.createdAt)}</span></div>) : <div className="emptyRow">暂无调用记录</div>}</div>
    </section>
  </div>;
}

function ProjectsPanel({ projects, onCreate, onDelete }: { projects: Project[]; onCreate: () => void; onDelete: (project: Project) => void }) {
  return <div className="content"><div className="pageIntro"><div><h2>项目隔离</h2><p>项目名必须是火山方舟控制台中真实存在的 ProjectName。</p></div><button className="primary" onClick={onCreate}><Plus size={17} />新建项目</button></div>
    <div className="cardGrid">{projects.map((project) => <article className="projectCard" key={project.name}><div className="projectTop"><span className="projectIcon">{project.displayName.slice(0, 1).toUpperCase()}</span><div><h3>{project.displayName}</h3><code>{project.name}</code></div><button className="projectDelete" type="button" onClick={() => void onDelete(project)} aria-label={`删除项目 ${project.displayName}`}><Trash2 size={15} /></button></div><p>{project.description || "暂无描述"}</p><footer><span>{project.activeKeyCount || 0} 个有效 Key</span><span>{project.keyCount || 0} 个 Key</span></footer></article>)}{!projects.length && <Empty text="还没有项目，请先创建并填写真实的火山 ProjectName。" />}</div>
  </div>;
}

function KeysPanel({ apiKeys, projects, onCreate, onDisable, onEnable, onDelete, onBind }: { apiKeys: ApiKey[]; projects: Project[]; onCreate: () => void; onDisable: (id: string) => Promise<void>; onEnable: (key: ApiKey) => Promise<void>; onDelete: (key: ApiKey) => Promise<void>; onBind: (id: string, project: string) => Promise<void> }) {
  return <div className="content"><div className="pageIntro"><div><h2>用户 API Keys</h2><p>把生成的 `vap_live_...` 交给用户；完整 Key 只显示一次。</p></div><button className="primary" onClick={onCreate} disabled={!projects.length}><Plus size={17} />生成 API Key</button></div>
    <section className="panel"><div className="dataTable keyTable"><div className="tableRow tableHead"><span>名称</span><span>Key</span><span>绑定项目</span><span>最近使用</span><span>状态</span><span /></div>{apiKeys.map((key) => <div className="tableRow" key={key.id}><span><b>{key.name}</b><small>{formatTime(key.createdAt)} 创建</small></span><span className="mono">{key.keyPrefix}</span><span><select className="inlineSelect" value={key.projectName} disabled={key.status !== "active"} onChange={(event) => void onBind(key.id, event.target.value)}>{projects.map((project) => <option key={project.name} value={project.name}>{project.name}</option>)}</select></span><span>{formatTime(key.lastUsedAt)}</span><span><i className={`state ${key.status}`}>{key.status === "active" ? "有效" : "已禁用"}</i></span><span className="keyActions">{key.status === "active" ? <button type="button" className="dangerLink" onClick={() => void onDisable(key.id)}>禁用</button> : <><button type="button" className="enableKeyButton" onClick={() => void onEnable(key)}><RotateCcw size={14} />启用</button><button type="button" className="deleteKeyButton" onClick={() => void onDelete(key)}><Trash2 size={14} />删除</button></>}</span></div>)}{!apiKeys.length && <div className="emptyRow">暂无 API Key</div>}</div></section>
  </div>;
}

type QuotaMetricKey = Exclude<keyof QuotaValues, "enabled">;

const quotaFields: Array<{ key: QuotaMetricKey; label: string; note: string; bytes?: boolean; projectOnly?: boolean }> = [
  { key: "readQpm", label: "查询 QPM", note: "查询超量只告警" },
  { key: "writeQpm", label: "写入 QPM", note: "超限返回 429" },
  { key: "maxConcurrency", label: "最大写并发", note: "单实例并发闸门" },
  { key: "dailyAssetCreates", label: "每日素材数", note: "创建成功后计数" },
  { key: "dailyUploadFiles", label: "每日上传文件", note: "TOS 上传成功后计数" },
  { key: "dailyUploadBytes", label: "每日上传量（GiB）", note: "公网 URL 不计入", bytes: true },
  { key: "totalAssets", label: "素材总数", note: "仅平台管理素材", projectOnly: true },
  { key: "totalStorageBytes", label: "TOS 总存储（GiB）", note: "仅本系统上传对象", bytes: true, projectOnly: true },
];

function bytesLabel(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${value} B`;
}

function quotaInputValue(value: number | null | undefined, bytes?: boolean) {
  if (value == null) return "";
  return String(bytes ? value / 1024 ** 3 : value);
}

function quotaPayload(form: Record<string, string>, projectOnly: boolean) {
  const result: Record<string, number | null> = {};
  for (const field of quotaFields) {
    if (!projectOnly && field.projectOnly) continue;
    const value = form[field.key]?.trim();
    result[field.key] = value ? Math.round(Number(value) * (field.bytes ? 1024 ** 3 : 1)) : null;
  }
  return result;
}

function QuotaPanel({ projects, apiKeys, events, audits, adminApi, onChanged }: { projects: Project[]; apiKeys: ApiKey[]; events: QuotaEvent[]; audits: QuotaAudit[]; adminApi: AdminApi; onChanged: () => Promise<void> }) {
  const [projectName, setProjectName] = useState("");
  const [keyId, setKeyId] = useState("");
  const [usage, setUsage] = useState<QuotaUsage | null>(null);
  const [projectForm, setProjectForm] = useState<Record<string, string>>({});
  const [projectEnabled, setProjectEnabled] = useState(false);
  const [keyForm, setKeyForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const selectedProjectName = projects.some((project) => project.name === projectName) ? projectName : (projects[0]?.name ?? "");
  const projectKeys = useMemo(() => apiKeys.filter((key) => key.projectName === selectedProjectName), [apiKeys, selectedProjectName]);
  const selectedKeyId = projectKeys.some((key) => key.id === keyId) ? keyId : (projectKeys[0]?.id ?? "");

  useEffect(() => {
    if (!selectedProjectName) return;
    let cancelled = false;
    void adminApi(`/api/internal/quota/usage?projectName=${encodeURIComponent(selectedProjectName)}`).then((data) => {
      if (cancelled) return;
      const next = data as unknown as QuotaUsage;
      setUsage(next);
      setProjectEnabled(Boolean(next.quota.enabled));
      setProjectForm(Object.fromEntries(quotaFields.map((field) => [field.key, quotaInputValue(next.quota[field.key], field.bytes)])));
    }).catch((caught) => setMessage(caught instanceof Error ? caught.message : "额度加载失败"));
    return () => { cancelled = true; };
  }, [adminApi, selectedProjectName]);

  useEffect(() => {
    if (!selectedKeyId) return;
    let cancelled = false;
    void adminApi(`/api/internal/apikey/quota?keyId=${encodeURIComponent(selectedKeyId)}`).then((data) => {
      if (cancelled) return;
      const next = data.quota as QuotaValues;
      setKeyForm(Object.fromEntries(quotaFields.filter((field) => !field.projectOnly).map((field) => [field.key, quotaInputValue(next[field.key], field.bytes)])));
    }).catch((caught) => setMessage(caught instanceof Error ? caught.message : "Key 子额度加载失败"));
    return () => { cancelled = true; };
  }, [adminApi, selectedKeyId]);

  async function saveProject(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await adminApi("/api/internal/project/quota", { method: "PUT", body: JSON.stringify({ projectName: selectedProjectName, enabled: projectEnabled, ...quotaPayload(projectForm, true) }) });
      setMessage("项目额度已保存并立即生效");
      await onChanged();
      const data = await adminApi(`/api/internal/quota/usage?projectName=${encodeURIComponent(selectedProjectName)}`);
      setUsage(data as unknown as QuotaUsage);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "项目额度保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveKey(event: FormEvent) {
    event.preventDefault();
    if (!selectedKeyId) return;
    setBusy(true);
    setMessage("");
    try {
      await adminApi("/api/internal/apikey/quota", { method: "PUT", body: JSON.stringify({ keyId: selectedKeyId, ...quotaPayload(keyForm, false) }) });
      setMessage("API Key 子额度已保存；留空字段继续继承项目");
      await onChanged();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Key 子额度保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function acknowledge(eventId: number) {
    await adminApi("/api/internal/quota/event/ack", { method: "POST", body: JSON.stringify({ eventId }) });
    await onChanged();
  }

  return <div className="content quotaConsole">
    <div className="pageIntro"><div><h2>额度与用量</h2><p>按企业项目设置总闸门，再为测试或批处理 Key 收紧子额度。</p></div><span className={`quotaMode ${projectEnabled ? "guarded" : "open"}`}>{projectEnabled ? "额度已启用" : "当前不限额"}</span></div>
    <div className="quotaSelector"><label>企业项目<select value={selectedProjectName} onChange={(event) => { setProjectName(event.target.value); setKeyId(""); }}>{projects.map((project) => <option key={project.name} value={project.name}>{project.displayName} · {project.name}</option>)}</select></label><div><b>{usage?.usage.cleanupPending ?? 0}</b><span>待清理 TOS 对象</span></div></div>

    <section className="quotaMeters" aria-label="项目额度使用情况">
      {quotaFields.map((field) => {
        const used = usage?.usage[field.key] ?? 0;
        const limit = projectEnabled ? usage?.quota[field.key] : null;
        const ratio = limit ? Math.min(100, used / limit * 100) : 0;
        return <article className="quotaMeter" key={field.key}><div><span>{field.label}</span><b>{field.bytes ? bytesLabel(used) : used.toLocaleString()}</b></div><div className="meterTrack"><i style={{ width: `${ratio}%` }} /></div><small>{limit ? `上限 ${field.bytes ? bytesLabel(limit) : limit.toLocaleString()}` : "不限额"}</small></article>;
      })}
    </section>

    <div className="quotaEditGrid">
      <form className="panel quotaForm" onSubmit={saveProject}><div className="panelHead"><div><h3>项目总额度</h3><p>留空表示该指标不限额，关闭后整套项目额度不生效。</p></div><label className="compactToggle"><input type="checkbox" checked={projectEnabled} onChange={(event) => setProjectEnabled(event.target.checked)} /><span>{projectEnabled ? "启用" : "关闭"}</span></label></div><div className="quotaFieldGrid">{quotaFields.map((field) => <label key={field.key}>{field.label}<input aria-label={field.label} type="number" min={field.bytes ? String(1 / 1024 ** 3) : "1"} step={field.bytes ? "any" : "1"} value={projectForm[field.key] ?? ""} onChange={(event) => setProjectForm({ ...projectForm, [field.key]: event.target.value })} placeholder="不限额" /><small>{field.note}</small></label>)}</div><button className="primary" disabled={busy || !selectedProjectName}>保存项目额度</button></form>

      <form className="panel quotaForm" onSubmit={saveKey}><div className="panelHead"><div><h3>API Key 子额度</h3><p>留空继承项目；填写值只能比项目额度更严格。</p></div></div><div className="keyQuotaSelect"><label>选择 Key<select value={selectedKeyId} onChange={(event) => setKeyId(event.target.value)}><option value="">该项目暂无 Key</option>{projectKeys.map((key) => <option key={key.id} value={key.id}>{key.name} · {key.keyPrefix}</option>)}</select></label></div><div className="quotaFieldGrid">{quotaFields.filter((field) => !field.projectOnly).map((field) => <label key={field.key}>{field.label}<input aria-label={field.label} type="number" min={field.bytes ? String(1 / 1024 ** 3) : "1"} step={field.bytes ? "any" : "1"} value={keyForm[field.key] ?? ""} onChange={(event) => setKeyForm({ ...keyForm, [field.key]: event.target.value })} placeholder="继承项目" /><small>{field.note}</small></label>)}</div><button className="secondary" disabled={busy || !selectedKeyId}>保存 Key 子额度</button></form>
    </div>
    {message && <div className="quotaMessage">{message}</div>}

    <section className="panel quotaEvents"><div className="panelHead"><div><h3>额度事件</h3><p>70%、90%、100% 阈值及硬限制会在这里留痕，同一窗口自动去重。</p></div></div>{events.length ? events.map((event) => <div className={`quotaEvent ${event.acknowledged ? "acknowledged" : ""}`} key={event.id}><span className="eventMark"><AlertTriangle size={16} /></span><div><b>{event.projectName} · {quotaFields.find((field) => field.key === event.metric.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()))?.label ?? event.metric}</b><small>{event.scopeType === "project" ? "项目" : "API Key"}达到 {event.threshold}% · {event.usedValue}/{event.limitValue} · {formatTime(event.createdAt)}</small></div>{event.acknowledged ? <i>已确认</i> : <button className="secondary" onClick={() => void acknowledge(event.id)}>确认</button>}</div>) : <div className="emptyRow">暂无额度事件</div>}</section>
    <div className="quotaBottomGrid">
      <section className="panel quotaLedger"><div className="panelHead"><div><h3>待处理 TOS 对象</h3><p>未注册文件保留 48 小时；删除失败对象由后台重试。</p></div></div>{usage?.cleanupObjects?.length ? usage.cleanupObjects.map((item) => <div className="ledgerRow" key={item.recordId}><div><b>{item.objectKey}</b><small>{bytesLabel(item.sizeBytes)} · {formatTime(item.createdAt)}</small></div><span>{item.status}{item.cleanupAttempts ? ` · 重试 ${item.cleanupAttempts}` : ""}</span></div>) : <div className="emptyRow">当前没有待处理对象</div>}</section>
      <section className="panel quotaLedger"><div className="panelHead"><div><h3>额度修改审计</h3><p>记录修改目标、来源 IP 与操作时间。</p></div></div>{audits.length ? audits.map((audit) => <div className="ledgerRow" key={audit.id}><div><b>{audit.targetType === "project" ? "项目" : "API Key"} · {audit.targetId}</b><small>{audit.sourceIp || "未知来源"} · {formatTime(audit.createdAt)}</small></div><span>{audit.action.endsWith("project.update") ? "项目额度" : "Key 子额度"}</span></div>) : <div className="emptyRow">暂无额度修改记录</div>}</section>
    </div>
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
