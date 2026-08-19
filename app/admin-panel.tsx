"use client";

import { Clipboard, KeyRound, LoaderCircle, Plus, RefreshCw, ShieldCheck, UserRoundCheck, UserRoundX, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import type { AdminApi, AdminSession, AdminUser } from "./admin-api";

type AdminAudit = {
  id: number;
  actor: string;
  sourceIp?: string | null;
  userAgent?: string | null;
  action: string;
  targetType: string;
  targetId: string;
  outcome: string;
  createdAt: string;
};

function formatTime(value?: string | number | null) {
  if (!value) return "从未";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value.endsWith("Z") ? value : `${value}Z`);
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function deviceLabel(userAgent?: string | null) {
  if (!userAgent) return "未知设备";
  if (/iphone|ipad/i.test(userAgent)) return "iPhone / iPad";
  if (/android/i.test(userAgent)) return "Android";
  if (/windows/i.test(userAgent)) return "Windows";
  if (/macintosh|mac os/i.test(userAgent)) return "macOS";
  if (/linux/i.test(userAgent)) return "Linux";
  return userAgent.slice(0, 70);
}

export default function AdminPanel({ currentUser, adminApi }: { currentUser: AdminUser; adminApi: AdminApi }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [audits, setAudits] = useState<AdminAudit[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ username: "", displayName: "" });
  const [initialPassword, setInitialPassword] = useState("");
  const [passwordOwner, setPasswordOwner] = useState("");

  const loadSecurityData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userData, sessionData, auditData] = await Promise.all([
        adminApi("/api/internal/admin/users"),
        adminApi("/api/internal/auth/sessions"),
        adminApi("/api/internal/admin/audits?limit=100"),
      ]);
      setUsers((userData.users ?? []) as AdminUser[]);
      setSessions((sessionData.sessions ?? []) as AdminSession[]);
      setAudits((auditData.audits ?? []) as AdminAudit[]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "管理员安全信息加载失败");
    } finally {
      setLoading(false);
    }
  }, [adminApi]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSecurityData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadSecurityData]);

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setBusyId("create");
    setError("");
    try {
      const data = await adminApi("/api/internal/admin/users", {
        method: "POST",
        body: JSON.stringify(createForm),
      });
      const created = data.user as AdminUser;
      setInitialPassword(String(data.initialPassword ?? ""));
      setPasswordOwner(created.displayName || created.username);
      setShowCreate(false);
      setCreateForm({ username: "", displayName: "" });
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "管理员创建失败");
    } finally {
      setBusyId("");
    }
  }

  async function toggleUser(user: AdminUser) {
    if (user.id === currentUser.id) return;
    const action = user.status === "active" ? "disable" : "enable";
    const prompt = action === "disable" ? `确认禁用管理员“${user.displayName || user.username}”？其全部会话会立即失效。` : `确认启用管理员“${user.displayName || user.username}”？`;
    if (!window.confirm(prompt)) return;
    setBusyId(user.id);
    setError("");
    try {
      await adminApi(`/api/internal/admin/users/${encodeURIComponent(user.id)}/${action}`, { method: "PUT" });
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "管理员状态修改失败");
    } finally {
      setBusyId("");
    }
  }

  async function resetPassword(user: AdminUser) {
    if (!window.confirm(`确认重置“${user.displayName || user.username}”的密码？其全部会话会立即失效。`)) return;
    setBusyId(`reset-${user.id}`);
    setError("");
    try {
      const data = await adminApi(`/api/internal/admin/users/${encodeURIComponent(user.id)}/reset-password`, { method: "POST" });
      setInitialPassword(String(data.initialPassword ?? ""));
      setPasswordOwner(user.displayName || user.username);
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "密码重置失败");
    } finally {
      setBusyId("");
    }
  }

  async function revokeSession(session: AdminSession) {
    if (session.current) return;
    setBusyId(`session-${session.id}`);
    setError("");
    try {
      await adminApi(`/api/internal/auth/sessions/${encodeURIComponent(session.id)}`, { method: "DELETE" });
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "会话撤销失败");
    } finally {
      setBusyId("");
    }
  }

  return <div className="content adminConsole">
    <div className="pageIntro"><div><h2>管理员与会话</h2><p>管理员独立登录、单独停用并保留可追溯的登录来源。</p></div><button className="primary" onClick={() => setShowCreate(true)}><Plus size={16} />创建管理员</button></div>
    {error && <div className="errorBanner adminInlineError" role="alert">{error}<button onClick={() => setError("")} aria-label="关闭"><X size={15} /></button></div>}

    <section className="panel adminSection">
      <div className="panelHead"><div><h3>管理员账号</h3><p>只有超级管理员能访问本页；普通管理员可使用其他业务管理功能。</p></div><button className="iconButton" onClick={() => void loadSecurityData()} disabled={loading} aria-label="刷新管理员安全信息"><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div>
      <div className="dataTable adminTable">
        <div className="tableRow tableHead"><span>管理员</span><span>角色</span><span>状态</span><span>最后登录</span><span>来源 IP</span><span>操作</span></div>
        {users.map((user) => <div className="tableRow" key={user.id}>
          <div><b>{user.displayName || user.username}</b><small>{user.username}{user.id === currentUser.id ? " · 当前账号" : ""}</small></div>
          <span className={`roleBadge ${user.role}`}>{user.role === "super_admin" ? "超级管理员" : "管理员"}</span>
          <span className={`state ${user.status}`}>{user.status === "active" ? "启用" : "已禁用"}</span>
          <span>{formatTime(user.lastLoginAt)}</span>
          <code>{user.lastLoginIp || "—"}</code>
          <div className="adminActions">
            <button className="secondary" onClick={() => void resetPassword(user)} disabled={Boolean(busyId) || user.id === currentUser.id} title={user.id === currentUser.id ? "超级管理员请使用页面右上角修改自己的密码；遗失密码时通过服务器 CLI 恢复" : undefined}><KeyRound size={13} />重置密码</button>
            <button className={user.status === "active" ? "dangerButton" : "secondary"} onClick={() => void toggleUser(user)} disabled={Boolean(busyId) || user.id === currentUser.id} title={user.id === currentUser.id ? "不能禁用当前登录账号" : undefined}>
              {busyId === user.id ? <LoaderCircle size={13} className="spin" /> : user.status === "active" ? <UserRoundX size={13} /> : <UserRoundCheck size={13} />}{user.status === "active" ? "禁用" : "启用"}
            </button>
          </div>
        </div>)}
        {!loading && !users.length && <div className="emptyRow">暂无管理员账号</div>}
      </div>
    </section>

    <section className="panel adminSection">
      <div className="panelHead"><div><h3>管理员安全审计</h3><p>记录登录、改密、账号状态和会话撤销；来源 IP 仅用于追溯，不作为访问限制。</p></div></div>
      <div className="auditList">
        {audits.map((audit) => <div className="auditRow" key={audit.id}>
          <div><b>{audit.action}</b><small>{audit.actor} · {audit.sourceIp || "未知 IP"} · {deviceLabel(audit.userAgent)} · {formatTime(audit.createdAt)}</small></div>
          <code>{audit.targetType}:{audit.targetId}</code>
          <span className={`auditOutcome ${audit.outcome}`}>{audit.outcome === "success" ? "成功" : audit.outcome}</span>
        </div>)}
        {!loading && !audits.length && <div className="emptyRow">暂无管理员安全审计</div>}
      </div>
    </section>

    <section className="panel adminSection">
      <div className="panelHead"><div><h3>我的登录会话</h3><p>发现不熟悉的设备或来源 IP 时，可立即撤销对应会话。</p></div></div>
      <div className="sessionList">
        {sessions.map((session) => <div className="sessionRow" key={session.id}>
          <span className="sessionIcon"><ShieldCheck size={17} /></span>
          <div><b>{deviceLabel(session.userAgent)}{session.current ? " · 当前会话" : ""}</b><small>{session.sourceIp || "未知 IP"} · 最近活动 {formatTime(session.lastSeenAt)} · 到期 {formatTime(session.absoluteExpiresAt)}</small></div>
          {session.current ? <i>正在使用</i> : <button className="dangerButton" onClick={() => void revokeSession(session)} disabled={Boolean(busyId)}>{busyId === `session-${session.id}` ? <LoaderCircle size={13} className="spin" /> : "撤销"}</button>}
        </div>)}
        {!loading && !sessions.length && <div className="emptyRow">暂无有效会话</div>}
      </div>
    </section>

    {showCreate && <div className="modalBackdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="create-admin-title">
      <header><h2 id="create-admin-title">创建管理员</h2><button onClick={() => setShowCreate(false)} aria-label="关闭"><X size={18} /></button></header>
      <form className="stackForm" onSubmit={createUser}>
        <label>用户名<input required minLength={3} maxLength={64} pattern="[A-Za-z0-9._-]+" autoComplete="off" value={createForm.username} onChange={(event) => setCreateForm({ ...createForm, username: event.target.value })} placeholder="例如 operator.chen" /></label>
        <label>显示名称<input required maxLength={64} value={createForm.displayName} onChange={(event) => setCreateForm({ ...createForm, displayName: event.target.value })} placeholder="例如 陈运营" /></label>
        <div className="note">新账号固定为普通管理员。超级管理员只能通过服务器 CLI 初始化，不能在控制台中增设。系统会生成一次性初始密码，该管理员首次登录后必须修改密码。</div>
        <button className="primary wide" disabled={busyId === "create"}>{busyId === "create" ? <><LoaderCircle size={16} className="spin" />创建中</> : "创建管理员"}</button>
      </form>
    </section></div>}

    {initialPassword && <div className="modalBackdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="initial-password-title">
      <header><h2 id="initial-password-title">保存一次性初始密码</h2><button onClick={() => { setInitialPassword(""); setPasswordOwner(""); }} aria-label="关闭"><X size={18} /></button></header>
      <div className="secretBox"><p>以下密码属于“{passwordOwner}”，关闭后不再显示。请通过安全渠道交付。</p><code>{initialPassword}</code><button className="primary wide" onClick={() => void navigator.clipboard.writeText(initialPassword)}><Clipboard size={16} />复制初始密码</button></div>
    </section></div>}
  </div>;
}
