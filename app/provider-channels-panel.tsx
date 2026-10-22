"use client";

import {
  CheckCircle2,
  KeyRound,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  ServerCog,
  Trash2,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { AdminApiError, type AdminApi } from "./admin-api";

type Provider =
  | "vega"
  | "openai"
  | "maxmodel"
  | "modeltop"
  | "volcengine_ark"
  | "byteplus_modelark"
  | "volcengine_speech"
  | "aliyun_bailian"
  | "minimax";
type ProjectOption = { name: string; displayName: string };
type Channel = {
  id: string;
  projectName: string;
  name: string;
  provider: Provider;
  config: Record<string, string>;
  status: "active" | "disabled";
  secretHint?: string | null;
  lastTestStatus?: "success" | "failed" | "manual" | null;
  lastTestLatencyMs?: number | null;
  lastTestError?: string | null;
};

const providerLabels: Record<Provider, string> = {
  vega: "Vega（腾讯云点播）",
  openai: "OpenAI",
  maxmodel: "MaxModel",
  modeltop: "ModelTop",
  volcengine_ark: "火山方舟",
  byteplus_modelark: "BytePlus ModelArk（海外）",
  volcengine_speech: "豆包语音",
  aliyun_bailian: "阿里百炼",
  minimax: "MiniMax",
};

const emptyForm = {
  projectName: "",
  name: "",
  provider: "volcengine_ark" as Provider,
  secret: "",
  secretId: "",
  subAppId: "",
  site: "domestic",
  workspaceId: "",
  region: "cn-beijing",
  organization: "",
  openaiProject: "",
  currentPassword: "",
  totpCode: "",
};

function channelConfig(form: typeof emptyForm) {
  if (form.provider === "vega") return { site: form.site, subAppId: form.subAppId };
  if (form.provider === "volcengine_ark") return {};
  if (form.provider === "aliyun_bailian")
    return { workspaceId: form.workspaceId, region: form.region };
  if (form.provider === "openai")
    return {
      ...(form.organization ? { organization: form.organization } : {}),
      ...(form.openaiProject ? { project: form.openaiProject } : {}),
    };
  return {};
}

type ChannelFormError = { message: string; code?: string; status?: number; requestId?: string };

function channelFormError(caught: unknown, sensitive: string[] = []): ChannelFormError {
  if (!(caught instanceof AdminApiError)) {
    const aborted = caught !== null && typeof caught === "object" && "name" in caught && caught.name === "AbortError";
    return { message: aborted
      ? "请求等待超时，尚不能确认是否已创建。请先关闭弹窗并刷新渠道列表，确认结果后再重试，避免重复创建。"
      : "网络连接失败，尚不能确认操作结果。请检查网络并先刷新渠道列表，避免重复提交。" };
  }
  const messages: Record<string, string> = {
    invalid_csrf_token: "安全校验已失效，可能在其他标签页切换过账号。请刷新页面或重新登录后再提交。",
    admin_reauthentication_failed: "超级管理员当前密码不正确，请重新输入。",
    invalid_admin_totp: "动态验证码错误或已过期。请输入验证器当前显示的6位验证码，并确认手机时间已自动同步。",
    admin_totp_replayed: "该验证码已使用（登录也会使用验证码），请等待下一组动态验证码后重新提交。",
    super_admin_required: "当前账号无权管理供应商凭证，请重新登录超级管理员账号。",
  };
  let message = messages[caught.code] || (caught.status >= 500
    ? "服务器暂时无法完成操作，请稍后重试；仍失败时请提供下方错误码和请求编号。"
    : caught.message);
  for (const value of sensitive.filter(Boolean)) message = message.split(value).join("[已隐藏]");
  return { message, code: caught.code, status: caught.status, requestId: caught.requestId };
}

function ChannelErrorNotice({ error }: { error: ChannelFormError | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!error) return;
    ref.current?.focus({ preventScroll: true });
    ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [error]);
  return error ? (
    <div className="formError providerFormError" role="alert" tabIndex={-1} ref={ref}>
      <XCircle size={18} aria-hidden="true" />
      <div>
        <strong>提交未完成</strong>
        <p>{error.message}</p>
        {error.code && <small>错误码：{error.code}{error.status ? ` · HTTP ${error.status}` : ""}</small>}
        {error.requestId && <small>请求编号：{error.requestId}</small>}
      </div>
    </div>
  ) : null;
}

export default function ProviderChannelsPanel({
  adminApi,
}: {
  adminApi: AdminApi;
}) {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [modalError, setModalError] = useState<ChannelFormError | null>(null);
  const [notice, setNotice] = useState("");
  const createPending = useRef(false);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [renameTarget, setRenameTarget] = useState<Channel | null>(null);
  const [renameName, setRenameName] = useState("");
  const [rotateTarget, setRotateTarget] = useState<Channel | null>(null);
  const [rotateForm, setRotateForm] = useState({
    secret: "",
    secretId: "",
    currentPassword: "",
    totpCode: "",
  });
  const [confirmTarget, setConfirmTarget] = useState<{
    channel: Channel;
    kind: "status" | "delete";
  } | null>(null);
  const [confirmForm, setConfirmForm] = useState({
    currentPassword: "",
    totpCode: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [projectData, channelData] = await Promise.all([
        adminApi("/api/internal/provider/projects"),
        adminApi("/api/internal/provider/channels"),
      ]);
      const nextProjects = (projectData.projects ?? []) as ProjectOption[];
      setProjects(nextProjects);
      setChannels((channelData.channels ?? []) as Channel[]);
      setForm((current) => ({
        ...current,
        projectName: current.projectName || nextProjects[0]?.name || "",
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "供应商渠道加载失败");
    } finally {
      setLoading(false);
    }
  }, [adminApi]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createChannel(event: FormEvent) {
    event.preventDefault();
    if (createPending.current) return;
    setModalError(null);
    const validation = !form.projectName ? "请选择客户项目。"
      : !form.name.trim() ? "请填写渠道名称，不能只包含空格。"
      : form.name.length > 100 ? "渠道名称不能超过100个字符。"
      : form.secret.trim().length < 8 || form.secret.trim().length > 4096 ? "供应商 API Key 必须为8～4096个字符，请确认已完整复制。"
      : !form.currentPassword || form.currentPassword.length > 128 ? "请输入当前超级管理员密码，最多128个字符。"
      : !/^\d{6}$/.test(form.totpCode) ? "请输入6位 TOTP 动态验证码。"
      : form.provider === "aliyun_bailian" && !form.workspaceId.trim() ? "请填写 Workspace ID。" : "";
    if (validation) {
      setModalError({ message: validation });
      return;
    }
    if (form.provider === "vega" && (!/^[1-9][0-9]{0,18}$/.test(form.subAppId) || form.secretId.trim().length < 8)) {
      setModalError({ message: "请填写有效的 SubAppId 和 SecretId。" });
      return;
    }
    createPending.current = true;
    setBusy("create");
    setError("");
    setNotice("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    try {
      await adminApi("/api/internal/provider/channels", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          projectName: form.projectName,
          name: form.name,
          provider: form.provider,
          config: channelConfig(form),
          secret: form.provider === "vega" ? JSON.stringify({ secretId: form.secretId.trim(), secretKey: form.secret.trim() }) : form.secret,
          currentPassword: form.currentPassword,
          totpCode: form.totpCode,
        }),
      });
      setForm({ ...emptyForm, projectName: form.projectName });
      setShowCreate(false);
      setNotice("渠道已创建，供应商凭证已加密保存。");
      await load();
    } catch (caught) {
      setModalError(channelFormError(caught, [form.secret, form.secretId, form.currentPassword, form.totpCode]));
      if (caught instanceof AdminApiError && ["csrf_token_refreshed", "invalid_admin_totp", "admin_totp_replayed"].includes(caught.code)) {
        setForm((current) => ({ ...current, totpCode: "" }));
      }
    } finally {
      window.clearTimeout(timeout);
      createPending.current = false;
      setBusy("");
    }
  }

  function closeCreate() {
    if (createPending.current) return;
    setShowCreate(false);
    setModalError(null);
    setForm({ ...emptyForm, projectName: form.projectName });
  }

  async function testChannel(channel: Channel) {
    setBusy(`test-${channel.id}`);
    setError("");
    try {
      await adminApi(
        `/api/internal/provider/channels/${encodeURIComponent(channel.id)}/test`,
        { method: "POST" },
      );
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "渠道测试失败");
    } finally {
      setBusy("");
    }
  }

  async function renameChannel(event: FormEvent) {
    event.preventDefault();
    if (!renameTarget) return;
    setBusy(`rename-${renameTarget.id}`);
    setModalError(null);
    setError("");
    try {
      await adminApi(
        `/api/internal/provider/channels/${encodeURIComponent(renameTarget.id)}/name`,
        {
          method: "PUT",
          body: JSON.stringify({ name: renameName }),
        },
      );
      setRenameTarget(null);
      setRenameName("");
      await load();
    } catch (caught) {
      setModalError(channelFormError(caught));
    } finally {
      setBusy("");
    }
  }

  async function rotateChannel(event: FormEvent) {
    event.preventDefault();
    if (!rotateTarget) return;
    setBusy(`rotate-${rotateTarget.id}`);
    setModalError(null);
    setError("");
    try {
      await adminApi(
        `/api/internal/provider/channels/${encodeURIComponent(rotateTarget.id)}/rotate-key`,
        {
          method: "POST",
          body: JSON.stringify({ secret: rotateTarget.provider === "vega"
            ? JSON.stringify({ secretId: rotateForm.secretId.trim(), secretKey: rotateForm.secret.trim() }) : rotateForm.secret,
            currentPassword: rotateForm.currentPassword, totpCode: rotateForm.totpCode }),
        },
      );
      setRotateTarget(null);
      setRotateForm({ secret: "", secretId: "", currentPassword: "", totpCode: "" });
      await load();
    } catch (caught) {
      setModalError(channelFormError(caught, Object.values(rotateForm)));
    } finally {
      setBusy("");
    }
  }

  async function confirmSensitive(event: FormEvent) {
    event.preventDefault();
    if (!confirmTarget) return;
    const { channel, kind } = confirmTarget;
    setBusy(`${kind}-${channel.id}`);
    setModalError(null);
    setError("");
    try {
      const path = `/api/internal/provider/channels/${encodeURIComponent(channel.id)}`;
      if (kind === "status") {
        await adminApi(`${path}/status`, {
          method: "PUT",
          body: JSON.stringify({
            enabled: channel.status !== "active",
            ...confirmForm,
          }),
        });
      } else {
        await adminApi(path, {
          method: "DELETE",
          body: JSON.stringify(confirmForm),
        });
      }
      setConfirmTarget(null);
      setConfirmForm({ currentPassword: "", totpCode: "" });
      await load();
    } catch (caught) {
      setModalError(channelFormError(caught, Object.values(confirmForm)));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel adminSection providerChannelsPanel">
      <div className="panelHead">
        <div>
          <h3>供应商渠道</h3>
          <p>
            凭证按客户项目加密保存；业务管理员只能绑定渠道，不能读取或修改凭证。
          </p>
        </div>
        <div className="panelHeadActions">
          <button className="secondary" onClick={() => { setModalError(null); setNotice(""); setShowCreate(true); }} disabled={Boolean(busy)}>
            <Plus size={15} />
            创建渠道
          </button>
          <button
            className="iconButton"
            onClick={() => void load()}
            disabled={loading}
            aria-label="刷新供应商渠道"
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>
      {error && (
        <div className="formError" role="alert">
          {error}
        </div>
      )}
      {notice && <div className="note" role="status"><CheckCircle2 size={15} aria-hidden="true" /> {notice}</div>}
      <div className="providerChannelGrid">
        {channels.map((channel) => (
          <article className="providerChannelCard" key={channel.id}>
            <header>
              <span>
                <ServerCog size={18} />
              </span>
              <div>
                <div className="providerChannelTitle">
                  <b>{channel.name}</b>
                  <button
                    type="button"
                    className="channelRenameButton"
                    onClick={() => {
                      setModalError(null);
                      setRenameTarget(channel);
                      setRenameName(channel.name);
                    }}
                    disabled={Boolean(busy)}
                    aria-label={`修改“${channel.name}”名称`}
                    title="修改名称"
                  >
                    <Pencil size={13} />
                  </button>
                </div>
                <small>
                  {providerLabels[channel.provider]} · {channel.projectName}
                </small>
              </div>
              <i className={channel.status}>
                {channel.status === "active" ? "启用" : "禁用"}
              </i>
            </header>
            <dl>
              <div>
                <dt>凭证</dt>
                <dd>
                  <code>{channel.secretHint || "未配置"}</code>
                </dd>
              </div>
              <div>
                <dt>连通测试</dt>
                <dd className={channel.lastTestStatus || "untested"}>
                  {channel.lastTestStatus === "success" ? (
                    <>
                      <CheckCircle2 size={13} />
                      正常 {channel.lastTestLatencyMs ?? 0}ms
                    </>
                  ) : channel.lastTestStatus === "failed" ? (
                    <>
                      <XCircle size={13} />
                      失败
                    </>
                  ) : channel.lastTestStatus === "manual" ? (
                    "需真实调用验证"
                  ) : (
                    "尚未测试"
                  )}
                </dd>
              </div>
            </dl>
            {channel.lastTestError && (
              <p className="providerTestError">{channel.lastTestError}</p>
            )}
            <footer>
              <button
                className="secondary"
                onClick={() => void testChannel(channel)}
                disabled={Boolean(busy)}
              >
                {busy === `test-${channel.id}` ? (
                  <LoaderCircle size={13} className="spin" />
                ) : (
                  <RefreshCw size={13} />
                )}
                测试
              </button>
              <button
                className="secondary"
                onClick={() => { setModalError(null); setRotateTarget(channel); }}
                disabled={Boolean(busy)}
              >
                <RotateCcw size={13} />
                轮换
              </button>
              <button
                className="secondary"
                onClick={() => { setModalError(null); setConfirmTarget({ channel, kind: "status" }); }}
                disabled={Boolean(busy)}
              >
                {channel.status === "active" ? "禁用" : "启用"}
              </button>
              <button
                className="dangerButton"
                onClick={() => { setModalError(null); setConfirmTarget({ channel, kind: "delete" }); }}
                disabled={Boolean(busy)}
              >
                <Trash2 size={13} />
                删除
              </button>
            </footer>
          </article>
        ))}
        {!loading && channels.length === 0 && (
          <div className="emptyRow">
            尚未创建供应商渠道。新功能默认关闭时，这里保持为空且不影响旧接口。
          </div>
        )}
      </div>

      {showCreate && (
        <div className="modalBackdrop">
          <section
            className="modal providerModal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-channel-title"
          >
            <header>
              <h2 id="create-channel-title">创建供应商渠道</h2>
              <button type="button" onClick={closeCreate} disabled={busy === "create"} aria-label="关闭">
                ×
              </button>
            </header>
            <form className="stackForm" onSubmit={createChannel} noValidate aria-busy={busy === "create"}>
              <label>
                客户项目
                <select
                  required
                  value={form.projectName}
                  onChange={(event) =>
                    setForm({ ...form, projectName: event.target.value })
                  }
                >
                  <option value="">选择项目</option>
                  {projects.map((project) => (
                    <option key={project.name} value={project.name}>
                      {project.displayName} · {project.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                渠道名称
                <input
                  required
                  maxLength={100}
                  value={form.name}
                  onChange={(event) =>
                    setForm({ ...form, name: event.target.value })
                  }
                  placeholder="例如 客户A火山方舟生产渠道"
                />
              </label>
              <label>
                供应商
                <select
                  value={form.provider}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      provider: event.target.value as Provider,
                    })
                  }
                >
                  {Object.entries(providerLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {form.provider === "aliyun_bailian" && (
                <>
                  <label>
                    Workspace ID
                    <input
                      required
                      maxLength={128}
                      value={form.workspaceId}
                      onChange={(event) =>
                        setForm({ ...form, workspaceId: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    地域
                    <select
                      value={form.region}
                      onChange={(event) =>
                        setForm({ ...form, region: event.target.value })
                      }
                    >
                      <option value="cn-beijing">北京</option>
                      <option value="ap-southeast-1">新加坡</option>
                      <option value="ap-northeast-1">日本</option>
                      <option value="eu-central-1">德国</option>
                      <option value="us-east-1">美国东部</option>
                    </select>
                  </label>
                </>
              )}
              {form.provider === "openai" && (
                <>
                  <label>
                    Organization（可选）
                    <input
                      value={form.organization}
                      onChange={(event) =>
                        setForm({ ...form, organization: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    OpenAI Project（可选）
                    <input
                      value={form.openaiProject}
                      onChange={(event) =>
                        setForm({ ...form, openaiProject: event.target.value })
                      }
                    />
                  </label>
                </>
              )}
              {form.provider === "vega" && (
                <>
                  <label>腾讯云站点<select value={form.site} onChange={(event) => setForm({ ...form, site: event.target.value })}>
                    <option value="domestic">国内站（人民币刊例价）</option>
                    <option value="international">国际站（美元价折算人民币）</option>
                  </select></label>
                  <label>SubAppId<input required inputMode="numeric" pattern="[1-9][0-9]{0,18}" value={form.subAppId} onChange={(event) => setForm({ ...form, subAppId: event.target.value })} /></label>
                  <label>SecretId<input type="password" required minLength={8} autoComplete="new-password" value={form.secretId} onChange={(event) => setForm({ ...form, secretId: event.target.value })} /></label>
                  <div className="note">先开通腾讯云点播 VOD，并申请 Vega 模型权限。SecretId/SecretKey 一起加密保存；SubAppId 固定注入，不接受客户覆盖。默认并发通常为 1，扩容请联系供应商。渠道测试不提交付费生成。</div>
                </>
              )}
              <label>
                {form.provider === "vega" ? "SecretKey" : "供应商 API Key"}
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={4096}
                  value={form.secret}
                  onChange={(event) =>
                    setForm({ ...form, secret: event.target.value })
                  }
                />
                <small>只提交一次；服务端加密后仅显示掩码。</small>
              </label>
              {form.provider === "volcengine_speech" && (
                <div className="note">
                  请填写语音技术控制台中新创建的 API Key。它与火山方舟 API Key
                  不通用；模型开通后创建的新 Key 才会包含对应资源权限。
                </div>
              )}
              {form.provider === "maxmodel" && (
                <div className="note">
                  固定请求 https://aiapi.maxmaas.com；无需填写 Base URL。渠道测试不会产生图片费用，绑定 gpt-image-2 后请从用户端进行一次真实调用验证。
                </div>
              )}
              {form.provider === "byteplus_modelark" && (
                <div className="note">
                  使用 BytePlus ModelArk 亚太区域（ap-southeast-1）的 API Key。
                  <a href="https://ai.byteplus.com/ark/region:ap-southeast-1/apikey" target="_blank" rel="noreferrer">获取 API Key</a>。
                  无需重复填写海外项目名；Key 自身的权限决定可访问的海外项目。
                  渠道测试不生成视频，模型权限需通过用户端真实调用验证。
                </div>
              )}
              {form.provider === "modeltop" && (
                <div className="note">
                  使用 ModelTop 平台创建的 API Key，固定请求 https://modeltop.ai，无需填写 Base URL。
                  <a href="https://modeltop.ai/docs/" target="_blank" rel="noreferrer">接口文档</a>。
                  渠道测试不产生图片或视频费用；绑定模型后通过客户工具验证。
                </div>
              )}
              <label>
                超级管理员当前密码
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={128}
                  value={form.currentPassword}
                  onChange={(event) =>
                    setForm({ ...form, currentPassword: event.target.value })
                  }
                />
              </label>
              <label>
                TOTP 动态验证码
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  pattern="\d{6}"
                  maxLength={6}
                  value={form.totpCode}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      totpCode: event.target.value
                        .replace(/\D/g, "")
                        .slice(0, 6),
                    })
                  }
                />
              </label>
              <ChannelErrorNotice error={modalError} />
              <button type="submit" className="primary wide" disabled={busy === "create"}>
                {busy === "create" ? (
                  <>
                    <LoaderCircle size={15} className="spin" />
                    正在创建
                  </>
                ) : (
                  "加密保存渠道"
                )}
              </button>
            </form>
          </section>
        </div>
      )}

      {renameTarget && (
        <div className="modalBackdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-channel-title"
          >
            <header>
              <h2 id="rename-channel-title">修改渠道名称</h2>
              <button
                onClick={() => {
                  setRenameTarget(null);
                  setRenameName("");
                  setModalError(null);
                }}
                disabled={Boolean(busy)}
                aria-label="关闭"
              >
                ×
              </button>
            </header>
            <form className="stackForm" onSubmit={renameChannel}>
              <label>
                新渠道名称
                <input
                  required
                  maxLength={100}
                  value={renameName}
                  onChange={(event) => setRenameName(event.target.value)}
                />
              </label>
              <ChannelErrorNotice error={modalError} />
              <button
                className="primary wide"
                disabled={busy === `rename-${renameTarget.id}`}
              >
                {busy === `rename-${renameTarget.id}` ? (
                  <>
                    <LoaderCircle size={15} className="spin" />
                    正在保存
                  </>
                ) : (
                  "保存名称"
                )}
              </button>
            </form>
          </section>
        </div>
      )}

      {rotateTarget && (
        <div className="modalBackdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rotate-channel-title"
          >
            <header>
              <h2 id="rotate-channel-title">轮换“{rotateTarget.name}”凭证</h2>
              <button onClick={() => { setRotateTarget(null); setRotateForm({ secret: "", secretId: "", currentPassword: "", totpCode: "" }); setModalError(null); }} disabled={Boolean(busy)} aria-label="关闭">
                ×
              </button>
            </header>
            <form className="stackForm" onSubmit={rotateChannel}>
              <div className="note">
                新请求立即使用新凭证；已提交的视频任务继续固定使用原凭证版本。
              </div>
              {rotateTarget.provider === "vega" && <label>新 SecretId<input type="password" required minLength={8} autoComplete="new-password" value={rotateForm.secretId} onChange={(event) => setRotateForm({ ...rotateForm, secretId: event.target.value })} /></label>}
              <label>
                {rotateTarget.provider === "vega" ? "新 SecretKey" : "新 API Key"}
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={rotateForm.secret}
                  onChange={(event) =>
                    setRotateForm({ ...rotateForm, secret: event.target.value })
                  }
                />
              </label>
              <label>
                超级管理员当前密码
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={rotateForm.currentPassword}
                  onChange={(event) =>
                    setRotateForm({
                      ...rotateForm,
                      currentPassword: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                TOTP 动态验证码
                <input
                  inputMode="numeric"
                  required
                  pattern="\d{6}"
                  maxLength={6}
                  value={rotateForm.totpCode}
                  onChange={(event) =>
                    setRotateForm({
                      ...rotateForm,
                      totpCode: event.target.value
                        .replace(/\D/g, "")
                        .slice(0, 6),
                    })
                  }
                />
              </label>
              <ChannelErrorNotice error={modalError} />
              <button className="primary wide" disabled={Boolean(busy)}>
                <KeyRound size={15} />
                确认轮换
              </button>
            </form>
          </section>
        </div>
      )}

      {confirmTarget && (
        <div className="modalBackdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="channel-sensitive-title"
          >
            <header>
              <h2 id="channel-sensitive-title">
                {confirmTarget.kind === "delete"
                  ? "删除供应商渠道"
                  : `${confirmTarget.channel.status === "active" ? "禁用" : "启用"}供应商渠道`}
              </h2>
              <button onClick={() => { setConfirmTarget(null); setConfirmForm({ currentPassword: "", totpCode: "" }); setModalError(null); }} disabled={Boolean(busy)} aria-label="关闭">
                ×
              </button>
            </header>
            <form className="stackForm" onSubmit={confirmSensitive}>
              <div className="note">
                {confirmTarget.kind === "delete"
                  ? "仍有模型绑定或未完成任务时，服务端会拒绝删除。"
                  : "状态修改立即影响该项目已授权模型的可用性。"}
              </div>
              <label>
                超级管理员当前密码
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={confirmForm.currentPassword}
                  onChange={(event) =>
                    setConfirmForm({
                      ...confirmForm,
                      currentPassword: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                TOTP 动态验证码
                <input
                  inputMode="numeric"
                  required
                  pattern="\d{6}"
                  maxLength={6}
                  value={confirmForm.totpCode}
                  onChange={(event) =>
                    setConfirmForm({
                      ...confirmForm,
                      totpCode: event.target.value
                        .replace(/\D/g, "")
                        .slice(0, 6),
                    })
                  }
                />
              </label>
              <ChannelErrorNotice error={modalError} />
              <button
                disabled={Boolean(busy)}
                className={
                  confirmTarget.kind === "delete"
                    ? "dangerButton wide"
                    : "primary wide"
                }
              >
                {confirmTarget.kind === "delete" ? "确认删除" : "确认修改"}
              </button>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
