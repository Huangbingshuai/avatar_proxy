"use client";

import { Clipboard, DatabaseBackup, KeyRound, LoaderCircle, Plus, RefreshCw, ShieldCheck, Trash2, UserRoundCheck, UserRoundX, X } from "lucide-react";
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

type SecurityAlert = {
  id: number;
  eventType: string;
  severity: "info" | "warning" | "critical";
  message: string;
  actor: string;
  sourceIp?: string | null;
  targetType: string;
  targetId: string;
  acknowledgedAt?: string | null;
  createdAt: string;
};

type BackupStatus = {
  enabled: boolean;
  intervalSeconds: number;
  retention: number;
  directory: string;
  lastRun?: { status: string; completedAt?: string | null; databaseBytes?: number | null; auditBytes?: number | null; error?: string | null } | null;
};

type SensitiveAction = { kind: "toggle" | "reset" | "delete"; user: AdminUser } | { kind: "backup" };

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
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [backup, setBackup] = useState<BackupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ username: "", displayName: "", currentPassword: "" });
  const [initialPassword, setInitialPassword] = useState("");
  const [passwordOwner, setPasswordOwner] = useState("");
  const [credentialUsername, setCredentialUsername] = useState("");
  const [credentialAction, setCredentialAction] = useState<"created" | "reset">("created");
  const [credentialsCopied, setCredentialsCopied] = useState(false);
  const [sensitiveAction, setSensitiveAction] = useState<SensitiveAction | null>(null);
  const [reauthPassword, setReauthPassword] = useState("");

  const loadSecurityData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userData, sessionData, auditData, alertData, backupData] = await Promise.all([
        adminApi("/api/internal/admin/users"),
        adminApi("/api/internal/auth/sessions"),
        adminApi("/api/internal/admin/audits?limit=100"),
        adminApi("/api/internal/admin/security-alerts?limit=100"),
        adminApi("/api/internal/admin/backups/status"),
      ]);
      setUsers((userData.users ?? []) as AdminUser[]);
      setSessions((sessionData.sessions ?? []) as AdminSession[]);
      setAudits((auditData.audits ?? []) as AdminAudit[]);
      setAlerts((alertData.alerts ?? []) as SecurityAlert[]);
      setBackup(backupData as unknown as BackupStatus);
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
      setCredentialUsername(created.username);
      setCredentialAction("created");
      setCredentialsCopied(false);
      setShowCreate(false);
      setCreateForm({ username: "", displayName: "", currentPassword: "" });
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "管理员创建失败");
    } finally {
      setBusyId("");
    }
  }

  async function toggleUser(user: AdminUser, currentPassword: string) {
    if (user.id === currentUser.id) return;
    const action = user.status === "active" ? "disable" : "enable";
    setBusyId(user.id);
    setError("");
    try {
      await adminApi(`/api/internal/admin/users/${encodeURIComponent(user.id)}/${action}`, { method: "PUT", body: JSON.stringify({ currentPassword }) });
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "管理员状态修改失败");
    } finally {
      setBusyId("");
    }
  }

  async function resetPassword(user: AdminUser, currentPassword: string) {
    setBusyId(`reset-${user.id}`);
    setError("");
    try {
      const data = await adminApi(`/api/internal/admin/users/${encodeURIComponent(user.id)}/reset-password`, { method: "POST", body: JSON.stringify({ currentPassword }) });
      setInitialPassword(String(data.initialPassword ?? ""));
      setPasswordOwner(user.displayName || user.username);
      setCredentialUsername(user.username);
      setCredentialAction("reset");
      setCredentialsCopied(false);
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "密码重置失败");
    } finally {
      setBusyId("");
    }
  }

  async function deleteUser(user: AdminUser, currentPassword: string) {
    if (user.status !== "disabled" || user.role === "super_admin") return;
    setBusyId(`delete-${user.id}`);
    setError("");
    try {
      await adminApi(`/api/internal/admin/users/${encodeURIComponent(user.id)}`, { method: "DELETE", body: JSON.stringify({ currentPassword }) });
      setUsers((current) => current.filter((item) => item.id !== user.id));
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "管理员删除失败");
    } finally {
      setBusyId("");
    }
  }

  async function runBackup(currentPassword: string) {
    setBusyId("backup");
    setError("");
    try {
      const data = await adminApi("/api/internal/admin/backups/run", {
        method: "POST",
        body: JSON.stringify({ currentPassword }),
      });
      setBackup(data as unknown as BackupStatus);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "安全备份失败");
    } finally {
      setBusyId("");
    }
  }

  async function confirmSensitiveAction(event: FormEvent) {
    event.preventDefault();
    if (!sensitiveAction || !reauthPassword) return;
    const action = sensitiveAction;
    setSensitiveAction(null);
    const password = reauthPassword;
    setReauthPassword("");
    if (action.kind === "toggle") await toggleUser(action.user, password);
    else if (action.kind === "reset") await resetPassword(action.user, password);
    else if (action.kind === "delete") await deleteUser(action.user, password);
    else await runBackup(password);
  }

  async function acknowledgeAlert(alert: SecurityAlert) {
    setBusyId(`alert-${alert.id}`);
    setError("");
    try {
      await adminApi("/api/internal/admin/security-alerts/ack", {
        method: "POST",
        body: JSON.stringify({ alertId: alert.id }),
      });
      setAlerts((current) => current.map((item) => item.id === alert.id ? { ...item, acknowledgedAt: new Date().toISOString() } : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "安全告警确认失败");
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

  const consoleOrigin = initialPassword && typeof window !== "undefined" ? window.location.origin : "";
  const credentialDeliveryText = [
    `你好，${passwordOwner}：`,
    "",
    credentialAction === "created" ? "你的控制台管理员账号已创建，请使用以下信息登录：" : "你的控制台管理员密码已重置，请使用以下信息登录：",
    `登录地址：${consoleOrigin || "当前控制台地址"}`,
    `用户名：${credentialUsername}`,
    `一次性初始密码：${initialPassword}`,
    "",
    "首次登录后系统会要求修改密码。请妥善保管，不要转发给无关人员。",
  ].join("\n");

  async function copyCredentialDeliveryText() {
    try {
      await navigator.clipboard.writeText(credentialDeliveryText);
      setCredentialsCopied(true);
    } catch {
      setError("自动复制失败，请在文本框中手动复制登录信息");
    }
  }

  function closeCredentialModal() {
    setInitialPassword("");
    setPasswordOwner("");
    setCredentialUsername("");
    setCredentialsCopied(false);
  }

  const openAlerts = alerts.filter((alert) => !alert.acknowledgedAt);
  const sensitiveDescription = sensitiveAction?.kind === "backup"
    ? "立即创建SQLite一致性副本和独立审计JSONL文件。"
    : sensitiveAction?.kind === "reset"
      ? `重置“${sensitiveAction.user.displayName || sensitiveAction.user.username}”的密码，并立即撤销其全部会话。`
      : sensitiveAction?.kind === "delete"
        ? `永久删除“${sensitiveAction.user.displayName || sensitiveAction.user.username}”，此操作无法恢复。`
        : sensitiveAction?.kind === "toggle"
          ? `${sensitiveAction.user.status === "active" ? "禁用" : "启用"}“${sensitiveAction.user.displayName || sensitiveAction.user.username}”${sensitiveAction.user.status === "active" ? "，并立即撤销其全部会话" : ""}。`
          : "";

  return <div className="content adminConsole">
    <div className="pageIntro"><div><h2>超级管理员安全中心</h2><p>超级管理员只负责账号、告警、会话与备份；日常业务请使用普通管理员。</p></div><button className="primary" onClick={() => setShowCreate(true)}><Plus size={16} />创建管理员</button></div>
    {error && <div className="errorBanner adminInlineError" role="alert">{error}<button onClick={() => setError("")} aria-label="关闭"><X size={15} /></button></div>}

    {openAlerts.length > 0 && <section className="securityAlertStack" aria-label="未确认安全告警">
      {openAlerts.slice(0, 5).map((alert) => <article className={`securityAlert ${alert.severity}`} key={alert.id}>
        <span><ShieldCheck size={18} /></span><div><b>{alert.message}</b><small>{alert.actor} · {alert.sourceIp || "未知IP"} · {formatTime(alert.createdAt)}</small></div>
        <button className="secondary" onClick={() => void acknowledgeAlert(alert)} disabled={Boolean(busyId)}>{busyId === `alert-${alert.id}` ? <LoaderCircle size={13} className="spin" /> : "确认告警"}</button>
      </article>)}
    </section>}

    <section className="panel adminSection backupPanel">
      <div className="panelHead"><div><h3>SQLite与审计自动备份</h3><p>{backup?.enabled ? `每 ${Math.round((backup.intervalSeconds || 86400) / 3600)} 小时自动执行，保留最近 ${backup.retention} 份。` : "自动备份当前已关闭。"}</p></div><button className="secondary" onClick={() => setSensitiveAction({ kind: "backup" })} disabled={Boolean(busyId)}><DatabaseBackup size={15} />立即备份</button></div>
      <div className="backupSummary"><div><small>最近状态</small><b className={backup?.lastRun?.status === "failed" ? "failed" : ""}>{backup?.lastRun?.status === "success" ? "备份成功" : backup?.lastRun?.status === "failed" ? "备份失败" : "尚未执行"}</b></div><div><small>完成时间</small><b>{formatTime(backup?.lastRun?.completedAt)}</b></div><div><small>数据库 / 审计</small><b>{backup?.lastRun?.databaseBytes ? `${Math.ceil(backup.lastRun.databaseBytes / 1024)} KB` : "—"} / {backup?.lastRun?.auditBytes ? `${Math.ceil(backup.lastRun.auditBytes / 1024)} KB` : "—"}</b></div></div>
      {backup?.lastRun?.error && <div className="formError">{backup.lastRun.error}</div>}
    </section>

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
            <button className="secondary" onClick={() => setSensitiveAction({ kind: "reset", user })} disabled={Boolean(busyId) || user.id === currentUser.id} title={user.id === currentUser.id ? "超级管理员请使用页面右上角修改自己的密码；遗失密码时通过服务器 CLI 恢复" : undefined}><KeyRound size={13} />重置密码</button>
            <button className={user.status === "active" ? "dangerButton" : "secondary"} onClick={() => setSensitiveAction({ kind: "toggle", user })} disabled={Boolean(busyId) || user.id === currentUser.id} title={user.id === currentUser.id ? "不能禁用当前登录账号" : undefined}>
              {busyId === user.id ? <LoaderCircle size={13} className="spin" /> : user.status === "active" ? <UserRoundX size={13} /> : <UserRoundCheck size={13} />}{user.status === "active" ? "禁用" : "启用"}
            </button>
            {user.status === "disabled" && user.role !== "super_admin" && <button className="dangerButton" onClick={() => setSensitiveAction({ kind: "delete", user })} disabled={Boolean(busyId)}>
              {busyId === `delete-${user.id}` ? <LoaderCircle size={13} className="spin" /> : <Trash2 size={13} />}删除
            </button>}
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
        <label>确认超级管理员密码<input type="password" autoComplete="current-password" required value={createForm.currentPassword} onChange={(event) => setCreateForm({ ...createForm, currentPassword: event.target.value })} placeholder="创建前需要重新验证身份" /></label>
        <div className="note">新账号固定为普通管理员。超级管理员只能通过服务器 CLI 初始化，不能在控制台中增设。系统会生成一次性初始密码，该管理员首次登录后必须修改密码。</div>
        <button className="primary wide" disabled={busyId === "create"}>{busyId === "create" ? <><LoaderCircle size={16} className="spin" />创建中</> : "创建管理员"}</button>
      </form>
    </section></div>}

    {sensitiveAction && <div className="modalBackdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="sensitive-action-title">
      <header><h2 id="sensitive-action-title">再次确认超级管理员身份</h2><button onClick={() => { setSensitiveAction(null); setReauthPassword(""); }} aria-label="关闭"><X size={18} /></button></header>
      <form className="stackForm" onSubmit={confirmSensitiveAction}>
        <div className="note">{sensitiveDescription}</div>
        <label>超级管理员当前密码<input type="password" autoComplete="current-password" required value={reauthPassword} onChange={(event) => setReauthPassword(event.target.value)} /></label>
        <div className="passwordActions"><button type="button" className="secondary" onClick={() => { setSensitiveAction(null); setReauthPassword(""); }}>取消</button><button className="primary" disabled={!reauthPassword}>{sensitiveAction.kind === "delete" ? "确认永久删除" : "验证并继续"}</button></div>
      </form>
    </section></div>}

    {initialPassword && <div className="modalBackdrop"><section className="modal credentialModal" role="dialog" aria-modal="true" aria-labelledby="initial-password-title">
      <header><h2 id="initial-password-title">复制管理员登录信息</h2><button onClick={closeCredentialModal} aria-label="关闭"><X size={18} /></button></header>
      <div className="secretBox">
        <p>以下内容已包含登录地址、用户名、一次性密码和使用说明，可直接复制后发送给“{passwordOwner}”。关闭后密码不再显示。</p>
        <textarea className="credentialDeliveryText" readOnly aria-label="可转发的管理员登录信息" value={credentialDeliveryText} onFocus={(event) => event.currentTarget.select()} />
        <button className="primary wide" onClick={() => void copyCredentialDeliveryText()}><Clipboard size={16} />{credentialsCopied ? "已复制，可直接发送" : "复制完整登录信息"}</button>
      </div>
    </section></div>}
  </div>;
}
