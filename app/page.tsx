"use client";

import { FormEvent, useCallback, useState } from "react";

type Project = { name: string; displayName: string; description: string; keyCount: number; activeKeyCount: number };
type ApiKey = { id: string; name: string; keyPrefix: string; projectName: string; status: string; createdAt: string; lastUsedAt?: string };
type Overview = { stats: { projects: number; activeKeys: number; requests24h: number; errors24h: number }; recent: Array<{ action: string; projectName: string; statusCode: number; durationMs: number; createdAt: string }> };
type Tab = "overview" | "projects" | "keys" | "docs";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "projects", label: "项目" },
  { id: "keys", label: "API Keys" },
  { id: "docs", label: "接口文档" },
];

const endpoints = [
  ["POST", "/api/v1/asset-groups", "创建素材组"],
  ["GET", "/api/v1/asset-groups", "查询素材组"],
  ["GET", "/api/v1/asset-groups/{id}", "获取素材组"],
  ["PATCH", "/api/v1/asset-groups/{id}", "更新素材组"],
  ["DELETE", "/api/v1/asset-groups/{id}", "删除素材组"],
  ["POST", "/api/v1/assets", "上传素材"],
  ["GET", "/api/v1/assets", "查询素材"],
  ["GET", "/api/v1/assets/{id}", "获取素材"],
  ["PATCH", "/api/v1/assets/{id}", "更新素材"],
  ["DELETE", "/api/v1/assets/{id}", "删除素材"],
];

export default function Home() {
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
  const [keyForm, setKeyForm] = useState({ name: "", projectName: "" });
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [showKeyForm, setShowKeyForm] = useState(false);

  const api = useCallback(async (path: string, init?: RequestInit, token = adminToken) => {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", "x-admin-token": token, ...init?.headers },
    });
    const data = await response.json() as Record<string, unknown>;
    if (!response.ok) {
      const nested = data.error as { message?: string } | undefined;
      throw new Error(nested?.message || "请求失败");
    }
    return data;
  }, [adminToken]);

  const loadAll = useCallback(async (token = adminToken) => {
    setLoading(true);
    setError("");
    try {
      const [projectData, keyData, overviewData] = await Promise.all([
        api("/api/admin/projects", undefined, token),
        api("/api/admin/api-keys", undefined, token),
        api("/api/admin/overview", undefined, token),
      ]);
      setProjects(projectData.projects as Project[]);
      setApiKeys(keyData.apiKeys as ApiKey[]);
      setOverview(overviewData as unknown as Overview);
      setLocked(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载失败");
      setLocked(true);
    } finally { setLoading(false); }
  }, [adminToken, api]);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setAdminToken(tokenDraft);
    await loadAll(tokenDraft);
  }

  async function createProject(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      await api("/api/admin/projects", { method: "POST", body: JSON.stringify(projectForm) });
      setProjectForm({ name: "", displayName: "", description: "" }); setShowProjectForm(false); await loadAll();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "创建失败"); }
  }

  async function createKey(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      const data = await api("/api/admin/api-keys", { method: "POST", body: JSON.stringify(keyForm) });
      setSecret(data.secret as string); setKeyForm({ name: "", projectName: "" }); setShowKeyForm(false); await loadAll();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "创建失败"); }
  }

  async function revokeKey(id: string) {
    if (!window.confirm("撤销后，使用此 Key 的请求会立即失败。确认撤销？")) return;
    await api(`/api/admin/api-keys/${id}`, { method: "DELETE" }); await loadAll();
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brandMark">V</span><div><strong>Avatar Proxy</strong><small>虚拟人像资产网关</small></div></div>
        <nav>{tabs.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}><span>{item.id === "overview" ? "◫" : item.id === "projects" ? "◇" : item.id === "keys" ? "⌁" : "≡"}</span>{item.label}</button>)}</nav>
        <div className="sidebarFoot"><i className="statusDot" /><div><b>Volcengine Ark</b><small>服务端凭证代理</small></div></div>
      </aside>

      <section className="workspace">
        <header><div><p className="eyebrow">CONTROL PLANE</p><h1>{tabs.find((item) => item.id === tab)?.label}</h1></div><div className="headerActions"><span className="securePill">AK/SK 已隔离</span><button className="ghost" onClick={() => void loadAll()} disabled={loading}>刷新</button></div></header>
        {error && !locked && <div className="errorBanner">{error}</div>}

        {tab === "overview" && <div className="content">
          <section className="hero"><div><span className="heroTag">PRIVATE ASSET GATEWAY</span><h2>一把 Key，安全调用<br />虚拟人像资产库</h2><p>前后端分离、项目级隔离与 Python FastAPI 网关。</p></div><div className="terminal"><div className="terminalTop"><span /><span /><span /><em>创建素材组</em></div><code><b>curl</b> -X POST {API_BASE_URL}/api/v1/asset-groups \<br />&nbsp; -H <i>&quot;Authorization: Bearer vap_live_••••&quot;</i> \<br />&nbsp; -d <i>&apos;{`{"name":"campaign-hero"}`}&apos;</i></code></div></section>
          <div className="statGrid">
            <Stat label="项目" value={overview?.stats.projects ?? 0} note="独立 ProjectName" />
            <Stat label="有效 API Keys" value={overview?.stats.activeKeys ?? 0} note="仅保存哈希" />
            <Stat label="24h 请求" value={overview?.stats.requests24h ?? 0} note="全部接口" />
            <Stat label="24h 异常" value={overview?.stats.errors24h ?? 0} note="上游与鉴权" warn={Boolean(overview?.stats.errors24h)} />
          </div>
          <section className="panel"><div className="panelHead"><div><h3>最近请求</h3><p>仅记录操作与状态，不记录业务请求体</p></div><button className="textButton" onClick={() => setTab("docs")}>查看接口文档 →</button></div>
            <div className="table"><div className="tr th"><span>操作</span><span>项目</span><span>状态</span><span>耗时</span><span>时间</span></div>{overview?.recent.length ? overview.recent.map((row, index) => <div className="tr" key={index}><span className="mono">{row.action}</span><span>{row.projectName}</span><span><i className={`httpStatus ${row.statusCode < 400 ? "ok" : "bad"}`}>{row.statusCode}</i></span><span>{row.durationMs} ms</span><span>{new Date(row.createdAt + "Z").toLocaleString("zh-CN")}</span></div>) : <div className="emptyRow">还没有调用记录</div>}</div>
          </section>
        </div>}

        {tab === "projects" && <div className="content"><div className="pageIntro"><div><h2>项目隔离</h2><p>每个项目映射到火山方舟的 ProjectName，资源与推理接入点保持一致。</p></div><button className="primary" onClick={() => setShowProjectForm(true)}>＋ 新建项目</button></div>
          <div className="cardGrid">{projects.map((project) => <article className="projectCard" key={project.name}><div className="projectIcon">{project.displayName.slice(0, 1).toUpperCase()}</div><div><h3>{project.displayName}</h3><code>{project.name}</code></div><p>{project.description || "暂无描述"}</p><footer><span>{project.activeKeyCount || 0} 个有效 Key</span><span>ProjectName 固定</span></footer></article>)}{!projects.length && <Empty text="还没有项目，先创建一个项目。" />}</div>
        </div>}

        {tab === "keys" && <div className="content"><div className="pageIntro"><div><h2>API Keys</h2><p>Key 只在创建时显示一次；服务端仅保存 SHA-256 哈希。</p></div><button className="primary" onClick={() => setShowKeyForm(true)} disabled={!projects.length}>＋ 生成 API Key</button></div>
          <section className="panel keyPanel"><div className="table"><div className="tr keyTr th"><span>名称</span><span>Key</span><span>项目</span><span>最近使用</span><span>状态</span><span /></div>{apiKeys.map((key) => <div className="tr keyTr" key={key.id}><span><b>{key.name}</b><small>{new Date(key.createdAt + "Z").toLocaleDateString("zh-CN")} 创建</small></span><span className="mono">{key.keyPrefix}</span><span>{key.projectName}</span><span>{key.lastUsedAt ? new Date(key.lastUsedAt + "Z").toLocaleString("zh-CN") : "从未"}</span><span><i className={`state ${key.status}`}>{key.status === "active" ? "有效" : "已撤销"}</i></span><span>{key.status === "active" && <button className="dangerLink" onClick={() => void revokeKey(key.id)}>撤销</button>}</span></div>)}{!apiKeys.length && <div className="emptyRow">还没有 API Key</div>}</div></section>
        </div>}

        {tab === "docs" && <div className="content"><div className="pageIntro"><div><h2>接口文档</h2><p>统一 Bearer 鉴权；项目由 API Key 自动注入，客户端不能覆盖。</p></div><a className="version" href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">Swagger ↗</a></div>
          <section className="docsLayout"><div className="endpointList">{endpoints.map(([method, path, title]) => <div className="endpoint" key={`${method}${path}`}><i className={method.toLowerCase()}>{method}</i><code>{path}</code><span>{title}</span></div>)}</div><aside className="quickDoc"><h3>快速开始</h3><p>请求头</p><pre>Authorization: Bearer vap_live_xxx<br />Content-Type: application/json</pre><p>上传图片素材</p><pre>{`POST /api/v1/assets\n\n{\n  "group_id": "group-xxx",\n  "url": "https://.../avatar.png",\n  "asset_type": "Image",\n  "name": "角色正面照"\n}`}</pre><div className="note">素材状态为 <b>Active</b> 后，用 <code>asset://&lt;asset_id&gt;</code> 参与 Seedance 视频生成。</div></aside></section>
        </div>}
      </section>

      {locked && <div className="modalBackdrop"><form className="unlockCard" onSubmit={unlock}><span className="lockMark">⌁</span><p className="eyebrow">SECURE CONSOLE</p><h2>解锁管理控制台</h2><p>输入部署时配置的管理令牌。令牌只保存在当前页面内存中。</p><label>管理令牌<input type="password" value={tokenDraft} onChange={(e) => setTokenDraft(e.target.value)} placeholder="CONSOLE_ADMIN_TOKEN" /></label>{error && <div className="formError">{error}</div>}<button className="primary wide" disabled={!tokenDraft || loading}>{loading ? "验证中…" : "进入控制台"}</button></form></div>}
      {showProjectForm && <Modal title="新建项目" onClose={() => setShowProjectForm(false)}><form onSubmit={createProject} className="stackForm"><label>显示名称<input required value={projectForm.displayName} onChange={(e) => setProjectForm({ ...projectForm, displayName: e.target.value })} placeholder="短剧业务" /></label><label>项目标识 / ProjectName<input required value={projectForm.name} onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })} placeholder="drama_prod" /></label><label>描述<textarea value={projectForm.description} onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })} placeholder="用于生产环境的虚拟人像资产" /></label><button className="primary wide">创建项目</button></form></Modal>}
      {showKeyForm && <Modal title="生成 API Key" onClose={() => setShowKeyForm(false)}><form onSubmit={createKey} className="stackForm"><label>Key 名称<input required value={keyForm.name} onChange={(e) => setKeyForm({ ...keyForm, name: e.target.value })} placeholder="production-server" /></label><label>所属项目<select required value={keyForm.projectName} onChange={(e) => setKeyForm({ ...keyForm, projectName: e.target.value })}><option value="">选择项目</option>{projects.map((project) => <option key={project.name} value={project.name}>{project.displayName} · {project.name}</option>)}</select></label><div className="note">此 Key 只能访问所选项目下的素材与素材组。</div><button className="primary wide">生成 Key</button></form></Modal>}
      {secret && <Modal title="保存你的 API Key" onClose={() => setSecret("")}><div className="secretBox"><p>这是唯一一次显示完整 Key。请立即复制并保存到安全位置。</p><code>{secret}</code><button className="primary wide" onClick={() => void navigator.clipboard.writeText(secret)}>复制 API Key</button></div></Modal>}
    </main>
  );
}

function Stat({ label, value, note, warn }: { label: string; value: number; note: string; warn?: boolean }) { return <article className="stat"><div><span>{label}</span><i className={warn ? "warn" : ""}>{warn ? "!" : "↗"}</i></div><strong>{value.toLocaleString()}</strong><small>{note}</small></article>; }
function Empty({ text }: { text: string }) { return <div className="emptyCard"><span>◇</span><p>{text}</p></div>; }
function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) { return <div className="modalBackdrop"><section className="modal"><header><h2>{title}</h2><button onClick={onClose} aria-label="关闭">×</button></header>{children}</section></div>; }
