"use client";

import { LoaderCircle, LockKeyhole, ScanLine, ShieldAlert, ShieldCheck, Smartphone, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import type { AdminApi, AdminUser } from "./admin-api";

type LoginPolicy = { loginTotpBypass: boolean; totpEnabled: boolean };

export default function AdminLoginPolicy({ adminApi, onRotate, onUserChanged, blocked = false }: {
  adminApi: AdminApi; onRotate: () => void; onUserChanged?: (user: AdminUser) => void; blocked?: boolean;
}) {
  const [policy, setPolicy] = useState<LoginPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [target, setTarget] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await adminApi("/api/internal/admin/security/login-policy");
      const next = result.policy as LoginPolicy | undefined;
      if (!next || typeof next.loginTotpBypass !== "boolean" || typeof next.totpEnabled !== "boolean") {
        throw new Error("无法读取登录安全设置");
      }
      setPolicy(next); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "读取登录安全设置失败"); }
    finally { setLoading(false); }
  }, [adminApi]);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  function close() {
    if (saving) return;
    setTarget(null); setPassword(""); setCode(""); setConfirmed(false); setError("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (target === null || !password || code.length !== 6 || !confirmed || saving) return;
    setSaving(true); setError(""); setMessage("");
    try {
      const result = await adminApi("/api/internal/admin/security/login-policy", {
        method: "PUT", body: JSON.stringify({ loginTotpBypass: target, currentPassword: password, totpCode: code }),
      });
      setPolicy(result.policy as LoginPolicy);
      setMessage(target ? "已开启免TOTP登录，下次只需账号密码；其他登录会话已退出。" : "已恢复TOTP登录，其他登录会话已退出。");
      setTarget(null); setConfirmed(false);
      onUserChanged?.(result.user as AdminUser);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "修改登录安全设置失败"); }
    finally { setPassword(""); setCode(""); setSaving(false); }
  }

  return <>
    <section className={`panel adminSection totpSecurityPanel loginPolicyPanel ${policy?.loginTotpBypass ? "passwordOnly" : ""}`}>
      <div className="totpSecurityIdentity"><span><Smartphone size={20} /></span><div><small>SUPER ADMIN MFA</small><h3>TOTP验证器</h3><p>{loading ? "正在读取登录安全设置…" : policy?.loginTotpBypass ? "免TOTP登录已开启：账号密码正确即可登录。验证器仍用于敏感操作。" : "登录需要密码和TOTP验证码。更换验证器时，确认新验证码前旧验证器保持有效。"}</p></div></div>
      <div className="totpSecurityAction">
        <span className={policy?.loginTotpBypass ? "policyWarning" : ""}>{policy?.loginTotpBypass ? <ShieldAlert size={14} /> : <ShieldCheck size={14} />}{loading ? "读取中" : !policy ? "状态未知" : policy.loginTotpBypass ? "仅密码登录" : "二次验证保护中"}</span>
        <button className="secondary" type="button" onClick={onRotate} disabled={blocked || saving}><ScanLine size={15} />更换验证器</button>
        <button className={policy?.loginTotpBypass ? "secondary" : "dangerButton"} type="button" disabled={loading || blocked || saving || !policy?.totpEnabled} onClick={() => { setTarget(!policy?.loginTotpBypass); setError(""); setMessage(""); setPassword(""); setCode(""); setConfirmed(false); }}>{policy?.loginTotpBypass ? <ShieldCheck size={15} /> : <LockKeyhole size={15} />}{policy?.loginTotpBypass ? "恢复TOTP登录" : "开启免TOTP登录"}</button>
      </div>
      {target === null && error && <div className="loginPolicyFeedback formError" role="alert">{error}<button className="secondary" type="button" onClick={() => void load()} disabled={loading}>重新读取</button></div>}
      {message && <div className="loginPolicyFeedback monitorSuccess" role="status"><ShieldCheck size={14} />{message}</div>}
    </section>
    {target !== null && <div className="modalBackdrop"><section className="modal loginPolicyModal" role="dialog" aria-modal="true" aria-labelledby="login-policy-title">
      <header><div><p className="securityEyebrow">登录安全设置</p><h2 id="login-policy-title">{target ? "开启免TOTP登录" : "恢复TOTP登录"}</h2></div><button type="button" aria-label="关闭登录安全设置" onClick={close} disabled={saving}><X size={18} /></button></header>
      <form className="stackForm" onSubmit={save}>
        <div className="loginPolicyNotice"><ShieldAlert size={20} /><div><b>{target ? "开启后，知道密码即可登录超级管理员。" : "恢复后，下次登录需要当前验证器的验证码。"}</b><p>仅影响当前超级管理员账号的登录步骤；不删除验证器、不取消敏感操作的验证。保存后其他登录会话将退出，当前会话保留。</p></div></div>
        <label>超级管理员当前密码<input aria-label="登录安全设置验证密码" type="password" autoComplete="current-password" required maxLength={128} value={password} disabled={saving} onChange={(event) => setPassword(event.target.value)} /></label>
        <label>当前验证器动态验证码<input aria-label="登录安全设置动态验证码" inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" minLength={6} maxLength={6} value={code} disabled={saving} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /><small>请使用尚未提交过的新验证码；登录刚使用的验证码不能再次使用。</small></label>
        <label className="loginPolicyConfirm"><input type="checkbox" aria-label="确认修改登录验证方式" checked={confirmed} disabled={saving} onChange={(event) => setConfirmed(event.target.checked)} /><span>{target ? "我了解仅密码登录会降低安全性，确认开启。" : "我能使用当前验证器，确认恢复二次验证登录。"}</span></label>
        {error && <div className="formError" role="alert">{error}</div>}
        <div className="passwordActions"><button className="secondary" type="button" onClick={close} disabled={saving}>取消</button><button className={target ? "dangerButton" : "primary"} disabled={saving || !password || code.length !== 6 || !confirmed}>{saving && <LoaderCircle size={15} className="spin" />}{saving ? "正在保存" : target ? "确认开启免TOTP登录" : "确认恢复TOTP登录"}</button></div>
      </form>
    </section></div>}
  </>;
}
