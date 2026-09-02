"use client";

import { Activity, ArchiveRestore, CheckCircle2, Clipboard, DatabaseBackup, FileCheck2, HardDrive, KeyRound, LoaderCircle, Plus, RefreshCw, Save, ScanLine, ShieldAlert, ShieldCheck, Smartphone, Trash2, UserRoundCheck, UserRoundX, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import type { AdminApi, AdminSession, AdminUser } from "./admin-api";
import ProviderChannelsPanel from "./provider-channels-panel";

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
  lastRestore?: { status: string; backupId: string; completedAt?: string | null; error?: string | null } | null;
};

type BackupItem = {
  id: string;
  databaseFile: string;
  auditFile?: string | null;
  databaseBytes?: number | null;
  auditBytes?: number | null;
  createdAt?: string | null;
  integrity?: string | null;
  sha256?: string | null;
  valid: boolean;
  unreadable?: boolean;
  activeSuperAdmins?: number;
  missingTables?: string[];
  counts?: { projects: number; apiKeys: number; adminUsers: number; adminAudits: number };
};

type DiskSample = {
  path: string;
  totalBytes: number;
  usedBytes: number;
  availableBytes: number;
  reservedBytes: number;
  usedPercent: number;
  level: "normal" | "warning" | "critical" | "emergency";
  sampledAt: number;
};

type DiskMonitorSettings = {
  enabled: boolean;
  configuredEnabled: boolean;
  runtimeEnabled: boolean;
  path: string;
  warningPercent: number;
  criticalPercent: number;
  emergencyPercent: number;
  recoveryPercent: number;
  sampleIntervalSeconds: number;
  persistIntervalSeconds: number;
  retentionDays: number;
  updatedBy?: string | null;
  updatedAt?: string | null;
};

type DiskMonitorStatus = {
  health: "ok" | "disabled" | "probe_failed";
  sample?: DiskSample | null;
  activeIncidentId?: string | null;
  recoveryStreak: number;
  probeFailureStreak: number;
  probeAlertActive: boolean;
  lastSampledAt?: number | null;
  lastError?: string | null;
  settings: DiskMonitorSettings;
};

type SensitiveAction = { kind: "toggle" | "reset" | "delete"; user: AdminUser } | { kind: "backup" };
type TotpRotationStage = "verify" | "scan" | "recovery" | null;
type TotpRotationSetup = { secret: string; qrCodeDataUrl: string; expiresAt: number };

function formatTime(value?: string | number | null) {
  if (!value) return "从未";
  let date: Date;
  if (typeof value === "number") {
    date = new Date(value * 1000);
  } else {
    const normalized = value.trim();
    if (!normalized) return "从未";
    const hasExplicitTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
    date = new Date(hasExplicitTimezone ? normalized : `${normalized.replace(" ", "T")}Z`);
  }
  if (!Number.isFinite(date.getTime())) return "时间未知";
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

function formatBytes(value?: number | null) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Math.max(0, value);
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount >= 100 || unit === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unit]}`;
}

function diskLevelLabel(level?: DiskSample["level"] | null) {
  if (level === "warning") return "预警";
  if (level === "critical") return "严重";
  if (level === "emergency") return "紧急";
  return "正常";
}

export default function AdminPanel({ currentUser, adminApi, onRestored }: { currentUser: AdminUser; adminApi: AdminApi; onRestored: (message: string) => void }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [audits, setAudits] = useState<AdminAudit[]>([]);
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [backup, setBackup] = useState<BackupStatus | null>(null);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [monitorStatus, setMonitorStatus] = useState<DiskMonitorStatus | null>(null);
  const [monitorForm, setMonitorForm] = useState({ enabled: true, warningPercent: "80", criticalPercent: "90", emergencyPercent: "95", recoveryPercent: "75", currentPassword: "" });
  const [monitorMessage, setMonitorMessage] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<BackupItem | null>(null);
  const [restoreForm, setRestoreForm] = useState({ currentPassword: "", totpCode: "", confirmation: "" });
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
  const [totpRotationStage, setTotpRotationStage] = useState<TotpRotationStage>(null);
  const [totpRotationForm, setTotpRotationForm] = useState({ currentPassword: "", currentTotpCode: "", newTotpCode: "" });
  const [totpRotationSetup, setTotpRotationSetup] = useState<TotpRotationSetup | null>(null);
  const [totpRecoveryCodes, setTotpRecoveryCodes] = useState<string[]>([]);
  const [totpRecoverySaved, setTotpRecoverySaved] = useState(false);
  const [totpRecoveryCopied, setTotpRecoveryCopied] = useState(false);

  const loadSecurityData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userData, sessionData, auditData, alertData, backupData, backupListData, monitorData] = await Promise.all([
        adminApi("/api/internal/admin/users"),
        adminApi("/api/internal/auth/sessions"),
        adminApi("/api/internal/admin/audits?limit=100"),
        adminApi("/api/internal/admin/security-alerts?limit=100"),
        adminApi("/api/internal/admin/backups/status"),
        adminApi("/api/internal/admin/backups"),
        adminApi("/api/internal/admin/system-monitor/status").catch(() => null),
      ]);
      setUsers((userData.users ?? []) as AdminUser[]);
      setSessions((sessionData.sessions ?? []) as AdminSession[]);
      setAudits((auditData.audits ?? []) as AdminAudit[]);
      setAlerts((alertData.alerts ?? []) as SecurityAlert[]);
      setBackup(backupData as unknown as BackupStatus);
      setBackups((backupListData.backups ?? []) as BackupItem[]);
      const nextMonitor = monitorData as unknown as DiskMonitorStatus | null;
      setMonitorStatus(nextMonitor);
      if (nextMonitor) {
        setMonitorForm({
          enabled: nextMonitor.settings.configuredEnabled,
          warningPercent: String(nextMonitor.settings.warningPercent),
          criticalPercent: String(nextMonitor.settings.criticalPercent),
          emergencyPercent: String(nextMonitor.settings.emergencyPercent),
          recoveryPercent: String(nextMonitor.settings.recoveryPercent),
          currentPassword: "",
        });
      }
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

  useEffect(() => {
    const timer = window.setInterval(() => {
      void adminApi("/api/internal/admin/system-monitor/status")
        .then((data) => setMonitorStatus(data as unknown as DiskMonitorStatus))
        .catch(() => undefined);
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [adminApi]);

  async function saveMonitorSettings(event: FormEvent) {
    event.preventDefault();
    setBusyId("monitor-settings");
    setError("");
    setMonitorMessage("");
    try {
      const data = await adminApi("/api/internal/admin/system-monitor/settings", {
        method: "PUT",
        body: JSON.stringify({
          enabled: monitorForm.enabled,
          warningPercent: Number(monitorForm.warningPercent),
          criticalPercent: Number(monitorForm.criticalPercent),
          emergencyPercent: Number(monitorForm.emergencyPercent),
          recoveryPercent: Number(monitorForm.recoveryPercent),
          currentPassword: monitorForm.currentPassword,
        }),
      });
      const settings = data.settings as unknown as DiskMonitorSettings;
      setMonitorStatus((current) => current ? { ...current, settings } : current);
      setMonitorForm((current) => ({ ...current, currentPassword: "" }));
      setMonitorMessage("磁盘监控配置已保存，下一次采样立即生效");
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "磁盘监控配置保存失败");
    } finally {
      setBusyId("");
    }
  }

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
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "安全备份失败");
    } finally {
      setBusyId("");
    }
  }

  async function validateBackup(item: BackupItem) {
    setBusyId(`validate-${item.id}`);
    setError("");
    try {
      const data = await adminApi(`/api/internal/admin/backups/${encodeURIComponent(item.id)}/validate`, {
        method: "POST",
      });
      const validated = data.backup as BackupItem;
      setBackups((current) => current.map((backupItem) => backupItem.id === item.id ? validated : backupItem));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "备份校验失败");
    } finally {
      setBusyId("");
    }
  }

  async function restoreDatabase(event: FormEvent) {
    event.preventDefault();
    if (!restoreTarget || restoreTarget.integrity !== "ok" || !restoreTarget.valid) return;
    setBusyId(`restore-${restoreTarget.id}`);
    setError("");
    try {
      await adminApi(`/api/internal/admin/backups/${encodeURIComponent(restoreTarget.id)}/restore`, {
        method: "POST",
        body: JSON.stringify(restoreForm),
      });
      setRestoreTarget(null);
      setRestoreForm({ currentPassword: "", totpCode: "", confirmation: "" });
      onRestored("数据库恢复成功，全部管理员会话已撤销，请使用备份时间点对应的账号状态重新登录");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "数据库恢复失败");
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

  function closeTotpRotation() {
    setTotpRotationStage(null);
    setTotpRotationForm({ currentPassword: "", currentTotpCode: "", newTotpCode: "" });
    setTotpRotationSetup(null);
    setTotpRecoveryCodes([]);
    setTotpRecoverySaved(false);
    setTotpRecoveryCopied(false);
  }

  async function beginTotpRotation(event: FormEvent) {
    event.preventDefault();
    setBusyId("totp-rotate-setup");
    setError("");
    try {
      const data = await adminApi("/api/internal/auth/totp/rotate/setup", {
        method: "POST",
        body: JSON.stringify({
          currentPassword: totpRotationForm.currentPassword,
          currentTotpCode: totpRotationForm.currentTotpCode,
        }),
      });
      setTotpRotationSetup(data as unknown as TotpRotationSetup);
      setTotpRotationForm({ currentPassword: "", currentTotpCode: "", newTotpCode: "" });
      setTotpRotationStage("scan");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "旧验证器身份校验失败");
    } finally {
      setBusyId("");
    }
  }

  async function confirmTotpRotation(event: FormEvent) {
    event.preventDefault();
    if (!totpRotationSetup) return;
    setBusyId("totp-rotate-confirm");
    setError("");
    try {
      const data = await adminApi("/api/internal/auth/totp/rotate/confirm", {
        method: "POST",
        body: JSON.stringify({ code: totpRotationForm.newTotpCode }),
      });
      setTotpRecoveryCodes((data.recoveryCodes ?? []) as string[]);
      setTotpRotationSetup(null);
      setTotpRotationForm({ currentPassword: "", currentTotpCode: "", newTotpCode: "" });
      setTotpRotationStage("recovery");
      await loadSecurityData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新验证器绑定失败");
    } finally {
      setBusyId("");
    }
  }

  async function copyTotpRecoveryCodes() {
    try {
      await navigator.clipboard.writeText(totpRecoveryCodes.join("\n"));
      setTotpRecoveryCopied(true);
    } catch {
      setError("自动复制失败，请手动保存新的恢复码");
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
  const diskSample = monitorStatus?.sample ?? null;
  const diskPercent = Math.min(100, Math.max(0, diskSample?.usedPercent ?? 0));
  const diskVisualState = monitorStatus?.health === "disabled"
    ? "disabled"
    : monitorStatus?.health === "probe_failed"
      ? "probe_failed"
      : diskSample?.level ?? "normal";
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
    <div className="pageIntro"><div><h2>超级管理员安全中心</h2><p>超级管理员只负责账号、告警、会话与备份；日常业务请使用普通管理员。</p></div></div>
    {error && <div className="errorBanner adminInlineError" role="alert">{error}<button onClick={() => setError("")} aria-label="关闭"><X size={15} /></button></div>}

    <ProviderChannelsPanel adminApi={adminApi} />

    {openAlerts.length > 0 && <section className="securityAlertStack" aria-label="未确认安全告警">
      {openAlerts.slice(0, 5).map((alert) => <article className={`securityAlert ${alert.severity}`} key={alert.id}>
        <span><ShieldCheck size={18} /></span><div><b>{alert.message}</b><small>{alert.actor} · {alert.sourceIp || "未知IP"} · {formatTime(alert.createdAt)}</small></div>
        <button className="secondary" onClick={() => void acknowledgeAlert(alert)} disabled={Boolean(busyId)}>{busyId === `alert-${alert.id}` ? <LoaderCircle size={13} className="spin" /> : "确认告警"}</button>
      </article>)}
    </section>}

    <section className="panel adminSection totpSecurityPanel">
      <div className="totpSecurityIdentity"><span><Smartphone size={20} /></span><div><small>SUPER ADMIN MFA</small><h3>TOTP验证器</h3><p>当前验证器已启用。更换时旧验证器会持续有效，直到新验证码确认成功。</p></div></div>
      <div className="totpSecurityAction"><span><ShieldCheck size={14} />保护中</span><button className="secondary" onClick={() => { setError(""); setTotpRotationStage("verify"); }} disabled={Boolean(busyId)}><ScanLine size={15} />更换验证器</button></div>
    </section>

    <section className={`panel adminSection diskMonitorPanel ${diskVisualState}`}>
      <div className="panelHead diskMonitorHead"><div><h3><HardDrive size={18} />磁盘空间监控</h3><p>每分钟自动采样；达到阈值后由后端自动发送邮件，不依赖管理员登录。</p></div><span className={`diskState ${diskVisualState}`}><Activity size={14} />{monitorStatus?.health === "disabled" ? "已停用" : monitorStatus?.health === "probe_failed" ? "探测异常" : diskLevelLabel(diskSample?.level)}</span></div>
      <div className="diskOverview">
        <div className="diskGauge"><div className="diskGaugeTrack"><i style={{ width: `${diskPercent}%` }} /></div><div><b>{diskSample ? `${diskSample.usedPercent.toFixed(1)}%` : "等待采样"}</b><small>{diskSample ? `${formatBytes(diskSample.usedBytes)} / ${formatBytes(diskSample.totalBytes)}` : monitorStatus?.lastError || "监控服务启动后将显示实时用量"}</small></div></div>
        <div><small>可用空间</small><b>{formatBytes(diskSample?.availableBytes)}</b></div>
        <div><small>监控路径</small><code>{monitorStatus?.settings.path || "—"}</code></div>
        <div><small>最近采样</small><b>{formatTime(diskSample?.sampledAt || monitorStatus?.lastSampledAt)}</b></div>
      </div>
      {monitorStatus?.lastError && <div className="diskProbeError"><ShieldAlert size={15} />{monitorStatus.lastError} · 连续失败 {monitorStatus.probeFailureStreak} 次</div>}
      <div className="diskMonitorBody">
        <form className="diskSettingsCard" onSubmit={saveMonitorSettings}>
          <div className="diskSubhead"><div><b>阈值配置</b><small>修改配置需要再次验证超级管理员密码。</small></div><label className="monitorSwitch"><input type="checkbox" checked={monitorForm.enabled} onChange={(event) => setMonitorForm({ ...monitorForm, enabled: event.target.checked })} /><span>{monitorForm.enabled ? "启用" : "停用"}</span></label></div>
          <div className="diskThresholdFields">
            <label>恢复线 %<input aria-label="恢复线" type="number" min="0" max="98" step="0.1" required value={monitorForm.recoveryPercent} onChange={(event) => setMonitorForm({ ...monitorForm, recoveryPercent: event.target.value })} /></label>
            <label>预警 %<input aria-label="预警阈值" type="number" min="1" max="99" step="0.1" required value={monitorForm.warningPercent} onChange={(event) => setMonitorForm({ ...monitorForm, warningPercent: event.target.value })} /></label>
            <label>严重 %<input aria-label="严重阈值" type="number" min="1" max="99" step="0.1" required value={monitorForm.criticalPercent} onChange={(event) => setMonitorForm({ ...monitorForm, criticalPercent: event.target.value })} /></label>
            <label>紧急 %<input aria-label="紧急阈值" type="number" min="1" max="100" step="0.1" required value={monitorForm.emergencyPercent} onChange={(event) => setMonitorForm({ ...monitorForm, emergencyPercent: event.target.value })} /></label>
          </div>
          <label>保存配置前验证密码<input aria-label="磁盘监控配置密码" type="password" autoComplete="current-password" required value={monitorForm.currentPassword} onChange={(event) => setMonitorForm({ ...monitorForm, currentPassword: event.target.value })} /></label>
          <button className="primary wide" disabled={busyId === "monitor-settings" || !monitorForm.currentPassword}>{busyId === "monitor-settings" ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}保存监控配置</button>
          {monitorMessage && <div className="monitorSuccess"><CheckCircle2 size={14} />{monitorMessage}</div>}
        </form>
      </div>
    </section>

    <section className="panel adminSection backupPanel">
      <div className="panelHead"><div><h3>SQLite与审计自动备份</h3><p>{backup?.enabled ? `每 ${Math.round((backup.intervalSeconds || 86400) / 3600)} 小时自动执行，保留最近 ${backup.retention} 份。` : "自动备份当前已关闭。"}</p></div><button className="secondary" onClick={() => setSensitiveAction({ kind: "backup" })} disabled={Boolean(busyId)}><DatabaseBackup size={15} />立即备份</button></div>
      <div className="backupSummary"><div><small>最近状态</small><b className={backup?.lastRun?.status === "failed" ? "failed" : ""}>{backup?.lastRun?.status === "success" ? "备份成功" : backup?.lastRun?.status === "failed" ? "备份失败" : "尚未执行"}</b></div><div><small>完成时间</small><b>{formatTime(backup?.lastRun?.completedAt)}</b></div><div><small>数据库 / 审计</small><b>{backup?.lastRun?.databaseBytes ? `${Math.ceil(backup.lastRun.databaseBytes / 1024)} KB` : "—"} / {backup?.lastRun?.auditBytes ? `${Math.ceil(backup.lastRun.auditBytes / 1024)} KB` : "—"}</b></div></div>
      {backup?.lastRun?.error && <div className="formError">{backup.lastRun.error}</div>}
      <div className="restoreSectionHead"><div><span><ArchiveRestore size={17} /></span><div><b>从服务器备份恢复</b><small>只允许恢复本系统生成并通过完整性校验的备份。</small></div></div>{backup?.lastRestore && <i className={backup.lastRestore.status}>{backup.lastRestore.status === "success" ? `最近恢复成功 · ${formatTime(backup.lastRestore.completedAt)}` : "最近恢复失败"}</i>}</div>
      <div className="backupList">
        {backups.slice(0, 10).map((item) => <article className="backupItem" key={item.id}>
          <span className={`backupFileIcon ${item.integrity === "ok" ? "verified" : ""}`}>{item.integrity === "ok" ? <CheckCircle2 size={18} /> : <DatabaseBackup size={18} />}</span>
          <div className="backupIdentity"><b>{formatTime(item.createdAt)}</b><small>{item.databaseFile} · {item.databaseBytes ? `${Math.ceil(item.databaseBytes / 1024)} KB` : "未知大小"}</small>{item.counts && <em>项目 {item.counts.projects} · Key {item.counts.apiKeys} · 管理员 {item.counts.adminUsers} · 审计 {item.counts.adminAudits}</em>}</div>
          <span className={`backupVerifyState ${item.integrity === "ok" ? "ok" : item.unreadable ? "failed" : "pending"}`}>{item.integrity === "ok" ? "校验通过" : item.unreadable ? "不可读取" : "待校验"}</span>
          <div className="backupActions"><button className="secondary" disabled={Boolean(busyId) || item.unreadable} onClick={() => void validateBackup(item)}>{busyId === `validate-${item.id}` ? <LoaderCircle size={13} className="spin" /> : <FileCheck2 size={13} />}校验</button><button className="dangerButton" disabled={Boolean(busyId) || item.integrity !== "ok" || !item.valid} onClick={() => { setRestoreTarget(item); setRestoreForm({ currentPassword: "", totpCode: "", confirmation: "" }); }}><ArchiveRestore size={13} />恢复</button></div>
        </article>)}
        {!loading && backups.length === 0 && <div className="emptyRow">暂无可恢复的服务器备份，请先执行一次备份。</div>}
      </div>
    </section>

    <section className="panel adminSection">
      <div className="panelHead"><div><h3>管理员账号</h3><p>只有超级管理员能访问本页；普通管理员可使用其他业务管理功能。</p></div><div className="panelHeadActions"><button className="iconButton" onClick={() => void loadSecurityData()} disabled={loading} aria-label="刷新管理员安全信息"><RefreshCw size={16} className={loading ? "spin" : ""} /></button><button className="primary" onClick={() => setShowCreate(true)}><Plus size={16} />创建管理员</button></div></div>
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

    {restoreTarget && <div className="modalBackdrop"><section className="modal restoreModal" role="dialog" aria-modal="true" aria-labelledby="restore-database-title">
      <header><div><p className="dangerEyebrow">不可逆高风险操作</p><h2 id="restore-database-title">恢复 SQLite 数据库</h2></div><button onClick={() => { if (!busyId) setRestoreTarget(null); }} aria-label="关闭"><X size={18} /></button></header>
      <form className="stackForm" onSubmit={restoreDatabase}>
        <div className="restoreWarning"><ShieldAlert size={21} /><div><b>备份时间之后的全部数据将被覆盖</b><p>系统会先生成当前数据库回滚点、暂停业务请求并校验恢复结果。成功后全部管理员会话失效，账号和密码恢复到备份时间点。</p></div></div>
        <div className="restoreTargetSummary"><span><small>恢复时间点</small><b>{formatTime(restoreTarget.createdAt)}</b></span><span><small>完整性</small><b>{restoreTarget.integrity === "ok" ? "已通过" : "未校验"}</b></span><span><small>数据量</small><b>{restoreTarget.counts ? `${restoreTarget.counts.projects} 项目 / ${restoreTarget.counts.apiKeys} Key` : "—"}</b></span></div>
        <label>超级管理员当前密码<input type="password" autoComplete="current-password" required value={restoreForm.currentPassword} onChange={(event) => setRestoreForm({ ...restoreForm, currentPassword: event.target.value })} /></label>
        <label>新一组 TOTP 动态验证码<input aria-label="新一组 TOTP 动态验证码" type="text" inputMode="numeric" autoComplete="one-time-code" required minLength={6} maxLength={6} pattern="\d{6}" value={restoreForm.totpCode} onChange={(event) => setRestoreForm({ ...restoreForm, totpCode: event.target.value.replace(/\D/g, "").slice(0, 6) })} /><small>登录时使用过的验证码不能重复使用；请等待验证器显示下一组验证码。</small></label>
        <label>输入“恢复数据库”确认<input required autoComplete="off" value={restoreForm.confirmation} onChange={(event) => setRestoreForm({ ...restoreForm, confirmation: event.target.value })} /></label>
        <div className="passwordActions"><button type="button" className="secondary" disabled={Boolean(busyId)} onClick={() => setRestoreTarget(null)}>取消</button><button className="dangerButton" disabled={busyId === `restore-${restoreTarget.id}` || !restoreForm.currentPassword || restoreForm.totpCode.length !== 6 || restoreForm.confirmation !== "恢复数据库"}>{busyId === `restore-${restoreTarget.id}` ? <><LoaderCircle size={15} className="spin" />正在恢复</> : <><ArchiveRestore size={15} />确认恢复</>}</button></div>
      </form>
    </section></div>}

    {totpRotationStage && <div className="modalBackdrop"><section className="modal totpRotationModal" role="dialog" aria-modal="true" aria-labelledby="totp-rotation-title">
      <header><div><p className="securityEyebrow">TOTP安全换绑</p><h2 id="totp-rotation-title">{totpRotationStage === "verify" ? "验证当前身份" : totpRotationStage === "scan" ? "扫描新的二维码" : "保存新的恢复码"}</h2></div>{totpRotationStage !== "recovery" && <button onClick={closeTotpRotation} disabled={Boolean(busyId)} aria-label="关闭"><X size={18} /></button>}</header>
      {totpRotationStage === "verify" && <form className="stackForm" onSubmit={beginTotpRotation}>
        <div className="totpRotationNotice"><ShieldAlert size={19} /><p>先验证当前密码和旧验证器。生成新二维码不会立即停用旧验证器，关闭窗口也不会影响登录。</p></div>
        <label>超级管理员当前密码<input type="password" autoComplete="current-password" required value={totpRotationForm.currentPassword} onChange={(event) => setTotpRotationForm({ ...totpRotationForm, currentPassword: event.target.value })} /></label>
        <label>当前验证器动态验证码<input aria-label="当前验证器动态验证码" type="text" inputMode="numeric" autoComplete="one-time-code" required minLength={6} maxLength={6} pattern="\d{6}" value={totpRotationForm.currentTotpCode} onChange={(event) => setTotpRotationForm({ ...totpRotationForm, currentTotpCode: event.target.value.replace(/\D/g, "").slice(0, 6) })} /><small>必须使用一组尚未提交过的6位验证码。</small></label>
        <div className="passwordActions"><button type="button" className="secondary" onClick={closeTotpRotation}>取消</button><button className="primary" disabled={busyId === "totp-rotate-setup" || !totpRotationForm.currentPassword || totpRotationForm.currentTotpCode.length !== 6}>{busyId === "totp-rotate-setup" ? <><LoaderCircle size={15} className="spin" />正在验证</> : "验证并生成新二维码"}</button></div>
      </form>}
      {totpRotationStage === "scan" && totpRotationSetup && <form className="stackForm totpRotationScan" onSubmit={confirmTotpRotation}>
        <div className="totpRotationSteps"><span className="done">1</span><i /><span>2</span><i /><span>3</span></div>
        <p className="totpRotationHint">用新的验证器App扫描二维码，然后输入新设备显示的6位验证码。二维码将在 {formatTime(totpRotationSetup.expiresAt)} 失效。</p>
        <span className="totpRotationQr" role="img" aria-label="新的TOTP绑定二维码" style={{ backgroundImage: `url(${totpRotationSetup.qrCodeDataUrl})` }} />
        <div className="totpManual"><small>无法扫码时，手动输入以下密钥</small><code>{totpRotationSetup.secret}</code><button type="button" className="secondary" onClick={() => void navigator.clipboard.writeText(totpRotationSetup.secret)}><Clipboard size={14} />复制密钥</button></div>
        <label>新验证器动态验证码<input aria-label="新验证器动态验证码" type="text" inputMode="numeric" autoComplete="one-time-code" required minLength={6} maxLength={6} pattern="\d{6}" value={totpRotationForm.newTotpCode} onChange={(event) => setTotpRotationForm({ ...totpRotationForm, newTotpCode: event.target.value.replace(/\D/g, "").slice(0, 6) })} /></label>
        <div className="passwordActions"><button type="button" className="secondary" onClick={closeTotpRotation}>暂不更换</button><button className="primary" disabled={busyId === "totp-rotate-confirm" || totpRotationForm.newTotpCode.length !== 6}>{busyId === "totp-rotate-confirm" ? <><LoaderCircle size={15} className="spin" />正在换绑</> : "确认更换"}</button></div>
      </form>}
      {totpRotationStage === "recovery" && <div className="stackForm totpRotationRecovery">
        <div className="totpRotationSuccess"><CheckCircle2 size={22} /><div><b>新验证器已生效</b><p>旧验证器、旧恢复码及其他登录会话已经失效。</p></div></div>
        <pre>{totpRecoveryCodes.join("\n")}</pre>
        <button type="button" className="secondary wide" onClick={() => void copyTotpRecoveryCodes()}><Clipboard size={15} />{totpRecoveryCopied ? "已复制新的恢复码" : "复制全部恢复码"}</button>
        <label className="recoveryConfirm"><input type="checkbox" checked={totpRecoverySaved} onChange={(event) => setTotpRecoverySaved(event.target.checked)} /><span>我已将新的恢复码保存在安全位置</span></label>
        <button type="button" className="primary wide" disabled={!totpRecoverySaved} onClick={closeTotpRotation}>完成更换</button>
      </div>}
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
