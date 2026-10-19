"use client";

import { Check, CheckCircle2, Mail, Pencil, Plus, Save, Send, ShieldCheck, Trash2, X, LoaderCircle } from "lucide-react";
import { FormEvent, useState } from "react";
import type { AdminApi } from "./admin-api";

type Provider = "qq" | "163" | "126" | "yeah" | "custom";
export type MailAccount = {
  id: string; provider: Provider; fromEmail: string; host: string; port: number;
  username: string; security: "ssl" | "starttls"; timeoutSeconds: number; passwordConfigured: boolean;
};
type MailProvider = { id: Exclude<Provider, "custom">; label: string; host: string; domains: string[]; helpUrl: string };
export type MonitorEmailSettings = {
  enabled: boolean; configured: boolean; recipients: string[]; source: string;
  accounts: MailAccount[]; activeAccountId: string | null; providers: MailProvider[];
};
type AccountDraft = MailAccount & { password: string; clearPassword: boolean };
type SettingsDraft = { enabled: boolean; accounts: AccountDraft[]; activeAccountId: string | null; recipients: string[] };
const labels: Record<Provider, string> = { qq: "QQ 邮箱", "163": "网易 163", "126": "网易 126", yeah: "网易 Yeah", custom: "其他邮箱" };
const validAddress = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
const fields = (email?: MonitorEmailSettings): SettingsDraft => ({ enabled: email?.enabled ?? false,
  accounts: (email?.accounts ?? []).map((item) => ({ ...item, password: "", clearPassword: false })),
  activeAccountId: email?.activeAccountId ?? null, recipients: email?.recipients ?? [] });
const fresh = (): AccountDraft => ({ id: `mail_${crypto.randomUUID().replaceAll("-", "")}`, provider: "qq", fromEmail: "",
  host: "", port: 465, username: "", security: "ssl", timeoutSeconds: 10, passwordConfigured: false, password: "", clearPassword: false });

export default function MonitorEmailSettingsForm({ email, adminApi, onSaved, loading = true }: {
  email?: MonitorEmailSettings; adminApi: AdminApi; onSaved: (value: MonitorEmailSettings) => void; loading?: boolean;
}) {
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const form = draft ?? fields(email);
  const [editor, setEditor] = useState<AccountDraft | null>(null);
  const [recipient, setRecipient] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  const active = form.accounts.find((item) => item.id === form.activeAccountId);
  function change(value: Partial<SettingsDraft>) {
    setDraft({ ...form, ...value }); setDirty(true); setMessage(""); setError("");
  }
  function addRecipients(value: string) {
    const values = value.split(/[\s,;，；]+/).filter(Boolean);
    if (!values.length) return;
    if (values.some((item) => !validAddress(item))) { setError("请填写有效的收件邮箱地址。"); return; }
    const next = [...new Set([...form.recipients, ...values])];
    if (next.length > 50) { setError("最多添加50个收件邮箱。"); return; }
    change({ recipients: next }); setRecipient("");
  }
  function applyAccount() {
    if (!editor) return;
    const address = editor.fromEmail.trim();
    if (!validAddress(address)) { setError("请填写有效的发件邮箱地址。"); return; }
    const preset = email?.providers.find((item) => item.id === editor.provider);
    if (preset && !preset.domains.includes(address.split("@")[1].toLowerCase())) {
      setError("邮箱地址与所选服务不匹配，请选择对应服务或其他邮箱。"); return;
    }
    if (editor.provider !== "custom" && !preset) { setError("邮箱服务尚未加载，请稍后再试。"); return; }
    const account = { ...editor, fromEmail: address, ...(preset ? { host: preset.host, port: 465,
      username: address, security: "ssl" as const, timeoutSeconds: 10 } : {}) };
    const previous = email?.accounts.find((item) => item.id === account.id);
    if (previous?.passwordConfigured && !account.password && !account.clearPassword &&
      (previous.host !== account.host || previous.username !== account.username)) {
      setError("更换发件邮箱或服务器后，请重新填写授权码。"); return;
    }
    if (!account.host || (account.username && !account.password && (!account.passwordConfigured || account.clearPassword))) {
      setError("请填写SMTP服务器和邮箱授权码。"); return;
    }
    const exists = form.accounts.some((item) => item.id === account.id);
    if (form.accounts.some((item) => item.id !== account.id && item.host === account.host && item.fromEmail === account.fromEmail)) {
      setError("该发件邮箱已添加。"); return;
    }
    change({ accounts: exists ? form.accounts.map((item) => item.id === account.id ? account : item) : [...form.accounts, account],
      activeAccountId: form.activeAccountId ?? account.id });
    setEditor(null);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (editor || busy || !email || !dirty || !currentPassword) return;
    if (recipient.trim()) { setError("请先点击添加，将输入的邮箱加入收件人列表。"); return; }
    setBusy("save"); setError(""); setMessage("");
    try {
      const data = await adminApi("/api/internal/admin/system-monitor/email/settings", { method: "PUT",
        body: JSON.stringify({ ...form, currentPassword, accounts: form.accounts.map((item) => ({
          id: item.id, provider: item.provider, fromEmail: item.fromEmail, host: item.host, port: item.port,
          username: item.username, security: item.security, timeoutSeconds: item.timeoutSeconds,
          clearPassword: item.clearPassword, password: item.password || undefined,
        })) }) });
      onSaved(data.email as MonitorEmailSettings); setDraft(null); setDirty(false);
      setMessage("邮件设置已保存，后台告警立即使用新配置。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "邮件设置保存失败");
      setDraft({ ...form, accounts: form.accounts.map((item) => ({ ...item, password: "" })) });
    } finally { setCurrentPassword(""); setBusy(""); }
  }
  async function test() {
    if (!email?.configured || dirty || editor || recipient.trim() || !currentPassword || busy) return;
    setBusy("test"); setError(""); setMessage("");
    try {
      await adminApi("/api/internal/admin/system-monitor/email/test", { method: "POST", body: JSON.stringify({ currentPassword }) });
      setMessage("测试邮件已发送，请检查收件箱。");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "测试邮件发送失败"); }
    finally { setCurrentPassword(""); setBusy(""); }
  }
  return <form className="monitorMailWorkspace" onSubmit={save} aria-label="磁盘告警邮件设置">
    <div className="monitorMailHeading"><div><span className="monitorSectionNumber">02</span><div><h4>邮件通知</h4><p>选邮箱、填授权码，其他参数自动配置。</p></div></div><label className="monitorSwitch"><input aria-label="启用磁盘邮件通知" type="checkbox" disabled={Boolean(busy) || !email} checked={form.enabled} onChange={(event) => change({ enabled: event.target.checked })} /><span>邮件通知</span></label></div>
    {!email ? <div className="monitorMailEmpty" role={loading ? "status" : "alert"}>{loading ? "正在加载邮件配置…" : "暂时无法读取邮件配置，请刷新或检查后端服务。"}</div> : <>
      {email.source === "legacy_env" && <div className="monitorMigration"><ShieldCheck size={15} />原有邮箱已保留，授权码无需重新填写。</div>}
      <fieldset disabled={Boolean(busy)} className="monitorMailContent">
        <div className="mailSectionTitle"><div><b>发件邮箱</b><small>可保存多套账号，每次只使用当前选中的账号发送。</small></div><button className="secondary" type="button" disabled={editor !== null || form.accounts.length >= 10} onClick={() => { setEditor(fresh()); setError(""); }}><Plus size={14} />添加邮箱</button></div>
        <div className="mailAccounts">{form.accounts.map((item) => <article className={`mailAccount ${item.id === form.activeAccountId ? "selected" : ""}`} key={item.id}>
          <label><input type="radio" name="mail-sender" aria-label={`使用 ${item.fromEmail} 发件`} checked={item.id === form.activeAccountId} onChange={() => change({ activeAccountId: item.id })} /><span className={`mailProviderIcon provider-${item.provider}`}><Mail size={17} /></span><span className="mailAccountIdentity"><b>{item.fromEmail}</b><small>{labels[item.provider]}{item.id === form.activeAccountId ? " · 当前发件" : " · 备用账号"}</small></span></label>
          <div><button className="mailIconAction" type="button" disabled={editor !== null} aria-label={`编辑 ${item.fromEmail}`} onClick={() => { setEditor({ ...item }); setError(""); }}><Pencil size={14} /></button><button className="mailIconAction danger" type="button" disabled={editor !== null} aria-label={`移除发件邮箱 ${item.fromEmail}`} onClick={() => { const accounts = form.accounts.filter((value) => value.id !== item.id); change({ accounts, activeAccountId: item.id === form.activeAccountId ? accounts[0]?.id ?? null : form.activeAccountId }); }}><Trash2 size={14} /></button></div>
        </article>)}{!form.accounts.length && !editor && <div className="monitorMailEmpty"><Mail size={25} /><b>添加第一个发件邮箱</b><p>支持QQ、网易，也可连接其他SMTP邮箱。</p></div>}</div>
        {editor && <section className="mailAccountEditor" aria-label="编辑发件邮箱">
          <div className="mailEditorHead"><b>{form.accounts.some((item) => item.id === editor.id) ? "编辑邮箱" : "添加邮箱"}</b><button className="mailIconAction" type="button" aria-label="取消编辑邮箱" onClick={() => { setEditor(null); setError(""); }}><X size={16} /></button></div>
          <div className="mailProviderPicker" role="group" aria-label="邮箱服务">{[...email.providers.map((item) => ({ id: item.id as Provider, label: item.label })), { id: "custom" as Provider, label: "其他邮箱" }].map((item) => <button type="button" aria-pressed={editor.provider === item.id} className={editor.provider === item.id ? "active" : ""} key={item.id} onClick={() => setEditor({ ...editor, provider: item.id, password: "", clearPassword: false })}>{item.label}{editor.provider === item.id && <Check size={13} />}</button>)}</div>
          <div className="mailEditorFields"><label>邮箱地址<input aria-label="发件邮箱地址" type="email" maxLength={320} autoComplete="off" placeholder={editor.provider === "custom" ? "alerts@example.com" : `你的账号@${email.providers.find((item) => item.id === editor.provider)?.domains[0] ?? "qq.com"}`} value={editor.fromEmail} onChange={(event) => setEditor({ ...editor, fromEmail: event.target.value })} /></label><label>邮箱授权码<input aria-label="SMTP授权码" type="password" maxLength={4096} autoComplete="new-password" placeholder={editor.passwordConfigured ? "已保存，留空不修改" : "不是邮箱登录密码"} value={editor.password} onChange={(event) => setEditor({ ...editor, password: event.target.value, clearPassword: false })} /></label></div>
          {editor.provider !== "custom" && <div className="mailSetupHint"><ShieldCheck size={14} /><span>服务器、端口和加密已自动配置。请先在邮箱设置中开启SMTP并获取授权码。</span><a href={email.providers.find((item) => item.id === editor.provider)?.helpUrl} target="_blank" rel="noreferrer">获取帮助 ↗</a></div>}
          {editor.provider === "custom" && <details className="mailAdvanced" open><summary>自定义SMTP参数</summary><div className="mailEditorFields"><label>SMTP服务器<input aria-label="SMTP服务器" value={editor.host} maxLength={253} onChange={(event) => setEditor({ ...editor, host: event.target.value })} /></label><label>SMTP登录账号<input aria-label="SMTP登录账号" value={editor.username} maxLength={320} onChange={(event) => setEditor({ ...editor, username: event.target.value })} /></label><label>端口<input aria-label="SMTP端口" type="number" min={1} max={65535} value={editor.port} onChange={(event) => setEditor({ ...editor, port: Number(event.target.value) })} /></label><label>连接加密<select aria-label="SMTP连接加密" value={editor.security} onChange={(event) => setEditor({ ...editor, security: event.target.value as "ssl" | "starttls" })}><option value="ssl">SSL / TLS</option><option value="starttls">STARTTLS</option></select></label><label>超时（秒）<input aria-label="SMTP发送超时" type="number" min={1} max={30} value={editor.timeoutSeconds} onChange={(event) => setEditor({ ...editor, timeoutSeconds: Number(event.target.value) })} /></label>{editor.passwordConfigured && <label className="mailClearCredential"><input type="checkbox" checked={editor.clearPassword} onChange={(event) => setEditor({ ...editor, clearPassword: event.target.checked, password: "" })} />清除授权码（仅免认证SMTP）</label>}</div></details>}
          <div className="mailEditorActions"><span>仅加入待保存列表，不会立即发信。</span><button type="button" className="secondary" onClick={applyAccount}><Check size={14} />完成编辑</button></div>
        </section>}
        <div className="mailSectionTitle"><div><b>谁来接收告警</b><small>可混合添加QQ、网易等邮箱，无需填写收件人的授权码。</small></div><span className="mailCount">{form.recipients.length} / 50</span></div>
        <div className="mailRecipientBox"><div className="mailRecipientChips">{form.recipients.map((address) => <span key={address}><Mail size={12} />{address}<button type="button" aria-label={`移除收件邮箱 ${address}`} onClick={() => change({ recipients: form.recipients.filter((item) => item !== address) })}><X size={12} /></button></span>)}</div><div className="mailRecipientInput"><input aria-label="添加收件邮箱" placeholder="输入邮箱，按回车添加；支持粘贴多个" value={recipient} onChange={(event) => setRecipient(event.target.value)} onKeyDown={(event) => { if (["Enter", ";", "；", ",", "，"].includes(event.key)) { event.preventDefault(); addRecipients(recipient); } }} onPaste={(event) => { const value = event.clipboardData.getData("text"); if (value.trim().split(/[\s,;，；]+/).length > 1) { event.preventDefault(); addRecipients(recipient + " " + value); } }} /><button type="button" className="secondary" disabled={!recipient.trim()} onClick={() => addRecipients(recipient)}><Plus size={14} />添加</button></div></div>
        {active && !form.recipients.includes(active.fromEmail) && <button className="mailTextAction" type="button" onClick={() => addRecipients(active.fromEmail)}>自己也接收：{active.fromEmail}</button>}
      </fieldset>
      <div className="mailSaveBar"><div><label>超级管理员密码<input aria-label="邮件配置验证密码" type="password" autoComplete="current-password" value={currentPassword} disabled={Boolean(busy)} onChange={(event) => setCurrentPassword(event.target.value)} placeholder="保存或测试前验证" /></label><small><ShieldCheck size={12} />授权码加密保存，不会回显。</small></div><div className="mailSaveActions"><span>{editor ? "请先完成或取消邮箱编辑" : dirty ? "有未保存的更改" : form.enabled ? "使用当前发件邮箱自动通知" : "邮件通知已停用"}</span><div><button className="secondary" type="button" disabled={Boolean(busy) || !email.configured || dirty || Boolean(recipient.trim()) || editor !== null || !currentPassword} onClick={() => void test()}>{busy === "test" ? <LoaderCircle size={14} className="spin" /> : <Send size={14} />}发送测试邮件</button><button className="primary" disabled={Boolean(busy) || !dirty || editor !== null || !currentPassword}>{busy === "save" ? <LoaderCircle size={14} className="spin" /> : <Save size={14} />}保存邮件设置</button></div></div></div>
    </>}
    {error && <div className="formError" role="alert">{error}</div>}
    {message && <div className="monitorSuccess" role="status"><CheckCircle2 size={14} />{message}</div>}
  </form>;
}
