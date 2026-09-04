"use client";

import {
  CheckCircle2,
  KeyRound,
  LoaderCircle,
  Plus,
  RefreshCw,
  RotateCcw,
  ServerCog,
  Trash2,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import type { AdminApi } from "./admin-api";

type Provider =
  | "openai"
  | "volcengine_ark"
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
  openai: "OpenAI",
  volcengine_ark: "火山方舟",
  volcengine_speech: "豆包语音",
  aliyun_bailian: "阿里百炼",
  minimax: "MiniMax",
};

const emptyForm = {
  projectName: "",
  name: "",
  provider: "volcengine_ark" as Provider,
  secret: "",
  workspaceId: "",
  region: "cn-beijing",
  organization: "",
  openaiProject: "",
  currentPassword: "",
  totpCode: "",
};

function channelConfig(form: typeof emptyForm) {
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
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [rotateTarget, setRotateTarget] = useState<Channel | null>(null);
  const [rotateForm, setRotateForm] = useState({
    secret: "",
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
    setBusy("create");
    setError("");
    try {
      await adminApi("/api/internal/provider/channels", {
        method: "POST",
        body: JSON.stringify({
          projectName: form.projectName,
          name: form.name,
          provider: form.provider,
          config: channelConfig(form),
          secret: form.secret,
          currentPassword: form.currentPassword,
          totpCode: form.totpCode,
        }),
      });
      setForm({ ...emptyForm, projectName: form.projectName });
      setShowCreate(false);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "渠道创建失败");
    } finally {
      setBusy("");
    }
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

  async function rotateChannel(event: FormEvent) {
    event.preventDefault();
    if (!rotateTarget) return;
    setBusy(`rotate-${rotateTarget.id}`);
    setError("");
    try {
      await adminApi(
        `/api/internal/provider/channels/${encodeURIComponent(rotateTarget.id)}/rotate-key`,
        {
          method: "POST",
          body: JSON.stringify(rotateForm),
        },
      );
      setRotateTarget(null);
      setRotateForm({ secret: "", currentPassword: "", totpCode: "" });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "凭证轮换失败");
    } finally {
      setBusy("");
    }
  }

  async function confirmSensitive(event: FormEvent) {
    event.preventDefault();
    if (!confirmTarget) return;
    const { channel, kind } = confirmTarget;
    setBusy(`${kind}-${channel.id}`);
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
      setError(caught instanceof Error ? caught.message : "渠道操作失败");
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
          <button className="secondary" onClick={() => setShowCreate(true)}>
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
      <div className="providerChannelGrid">
        {channels.map((channel) => (
          <article className="providerChannelCard" key={channel.id}>
            <header>
              <span>
                <ServerCog size={18} />
              </span>
              <div>
                <b>{channel.name}</b>
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
                onClick={() => setRotateTarget(channel)}
                disabled={Boolean(busy)}
              >
                <RotateCcw size={13} />
                轮换
              </button>
              <button
                className="secondary"
                onClick={() => setConfirmTarget({ channel, kind: "status" })}
                disabled={Boolean(busy)}
              >
                {channel.status === "active" ? "禁用" : "启用"}
              </button>
              <button
                className="dangerButton"
                onClick={() => setConfirmTarget({ channel, kind: "delete" })}
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
              <button onClick={() => setShowCreate(false)} aria-label="关闭">
                ×
              </button>
            </header>
            <form className="stackForm" onSubmit={createChannel}>
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
              <label>
                供应商 API Key
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
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
              <label>
                超级管理员当前密码
                <input
                  type="password"
                  autoComplete="current-password"
                  required
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
              <button className="primary wide" disabled={busy === "create"}>
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
              <button onClick={() => setRotateTarget(null)} aria-label="关闭">
                ×
              </button>
            </header>
            <form className="stackForm" onSubmit={rotateChannel}>
              <div className="note">
                新请求立即使用新凭证；已提交的视频任务继续固定使用原凭证版本。
              </div>
              <label>
                新 API Key
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
              <button className="primary wide">
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
              <button onClick={() => setConfirmTarget(null)} aria-label="关闭">
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
              <button
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
