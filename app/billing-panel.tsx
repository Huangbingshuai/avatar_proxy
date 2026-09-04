"use client";

import {
  AudioLines,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  Download,
  FileClock,
  Image as ImageIcon,
  LoaderCircle,
  MessageSquareText,
  Network,
  Printer,
  ReceiptText,
  RefreshCw,
  Save,
  Settings2,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { AdminApi } from "./admin-api";
import { getModelIconPath } from "./model-icon-library";

type Project = { name: string; displayName: string };
type Prices = {
  inputPerMillionYuan?: string | null;
  outputPerMillionYuan?: string | null;
  perImageYuan?: string | null;
  perTenThousandCharactersYuan?: string | null;
  perHourYuan?: string | null;
  perMinuteYuan?: string | null;
  perSecondByResolution?: Record<string, string | null>;
};
type Rate = {
  model: string;
  displayName: string;
  provider: string;
  modality: "text" | "image" | "video" | "embedding" | "audio";
  billingMetric?: string;
  billingUnit?: number;
  sourceMonths: string[];
  prices: Prices;
};
type Terms = {
  projectName: string;
  month: string;
  enabled: boolean;
  discountBps: number;
  sourceMonth?: string | null;
};
type StatementSummary = {
  id: string;
  number: string;
  projectName: string;
  month: string;
  status: "draft" | "confirmed" | "paid";
  subtotalYuan: string;
  discountYuan: string;
  adjustmentYuan: string;
  totalYuan: string;
  pendingCount: number;
  generatedAt: string;
  updatedAt: string;
  confirmedAt?: string | null;
  paidAt?: string | null;
};
type StatementLine = {
  id: string;
  model: string;
  metric: string;
  resolution?: string | null;
  quantity: string;
  unitSize: number;
  unitPriceYuan: string;
  listAmountYuan: string;
  netAmountYuan: string;
};
type Adjustment = {
  id: string;
  amountYuan: string;
  reason: string;
  type?: "manual" | "late_usage";
  createdAt: string;
};
type Statement = StatementSummary & {
  lines: StatementLine[];
  adjustments: Adjustment[];
  pending: Array<{
    model_alias: string;
    pending_reason: string;
    count: number;
  }>;
};

const resolutions = ["480p", "720p", "768p", "1080p"];
const providerNames: Record<string, string> = {
  volcengine_ark: "火山方舟",
  volcengine_speech: "豆包语音",
  openai: "OpenAI",
  aliyun_bailian: "阿里百炼",
  minimax: "MiniMax",
};
const metricNames: Record<string, string> = {
  input_tokens: "输入 Token",
  output_tokens: "输出 Token",
  image: "生成图片",
  video_second: "视频时长",
  characters: "输入字符",
  audio_second: "音频时长",
};

function monthNow() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  return `${parts.find((item) => item.type === "year")?.value}-${parts.find((item) => item.type === "month")?.value}`;
}

function nextMonth(value: string) {
  const [year, month] = value.split("-").map(Number);
  return `${year + (month === 12 ? 1 : 0)}-${String(month === 12 ? 1 : month + 1).padStart(2, "0")}`;
}

function money(value?: string | null) {
  const amount = Number(value || 0);
  const formatted = Math.abs(amount).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${amount < 0 ? "-" : ""}¥${formatted}`;
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(
    value.endsWith("Z") || value.includes("+") ? value : `${value}Z`,
  );
  return Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date)
    : "—";
}

function ModelIcon({ rate }: { rate: Rate }) {
  const path = getModelIconPath(rate.model);
  if (path) {
    // Icons are small local SVG assets; preserving their native viewBox avoids
    // provider-logo distortion in this dense price table.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={path} alt="" />;
  }
  if (rate.modality === "image") return <ImageIcon size={22} />;
  if (rate.modality === "video") return <Video size={22} />;
  if (rate.modality === "embedding") return <Network size={22} />;
  if (rate.modality === "audio") return <AudioLines size={22} />;
  return <MessageSquareText size={22} />;
}

export default function BillingPanel({
  projects,
  adminApi,
}: {
  projects: Project[];
  adminApi: AdminApi;
}) {
  const [projectName, setProjectName] = useState(projects[0]?.name || "");
  const [month, setMonth] = useState(monthNow());
  const [view, setView] = useState<"overview" | "rates" | "statements">(
    "overview",
  );
  const [rates, setRates] = useState<Rate[]>([]);
  const [rateDrafts, setRateDrafts] = useState<Record<string, Prices>>({});
  const [terms, setTerms] = useState<Terms | null>(null);
  const [statement, setStatement] = useState<StatementSummary | null>(null);
  const [statements, setStatements] = useState<StatementSummary[]>([]);
  const [statementMonthFilter, setStatementMonthFilter] = useState("");
  const [statementStatusFilter, setStatementStatusFilter] = useState("");
  const [detail, setDetail] = useState<Statement | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [projectDraft, setProjectDraft] = useState({
    enabled: false,
    discountPercent: "100",
    effectiveMonth: nextMonth(monthNow()),
    currentPassword: "",
  });
  const [ratePassword, setRatePassword] = useState("");
  const [statementPassword, setStatementPassword] = useState("");
  const [adjustment, setAdjustment] = useState({ amountYuan: "", reason: "" });
  const [payment, setPayment] = useState({ reference: "", note: "" });

  const activeProject =
    projects.find((item) => item.name === projectName) ?? projects[0];
  const activeProjectName = activeProject?.name || "";

  const load = useCallback(async () => {
    if (!activeProjectName) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [rateData, termData, previewData, statementData] =
        await Promise.all([
          adminApi(`/api/internal/billing/rates?month=${month}`),
          adminApi(
            `/api/internal/billing/projects/${encodeURIComponent(activeProjectName)}?month=${month}`,
          ),
          adminApi(
            `/api/internal/billing/preview?projectName=${encodeURIComponent(activeProjectName)}&month=${month}`,
          ),
          adminApi(
            `/api/internal/billing/statements?projectName=${encodeURIComponent(activeProjectName)}${statementMonthFilter ? `&month=${statementMonthFilter}` : ""}${statementStatusFilter ? `&status=${statementStatusFilter}` : ""}`,
          ),
        ]);
      const nextRates = (rateData.rates ?? []) as Rate[];
      const nextTerms = termData.billing as Terms;
      setRates(nextRates);
      setRateDrafts(
        Object.fromEntries(
          nextRates.map((rate) => [
            rate.model,
            JSON.parse(JSON.stringify(rate.prices)) as Prices,
          ]),
        ),
      );
      setTerms(nextTerms);
      setProjectDraft((current) => ({
        ...current,
        enabled: nextTerms.enabled,
        discountPercent: String(nextTerms.discountBps / 100),
        effectiveMonth:
          nextTerms.sourceMonth && nextTerms.sourceMonth >= monthNow()
            ? nextTerms.sourceMonth
            : nextMonth(monthNow()),
        currentPassword: "",
      }));
      setStatement((previewData.statement as StatementSummary | null) ?? null);
      setStatements((statementData.statements ?? []) as StatementSummary[]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "计费数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [
    activeProjectName,
    adminApi,
    month,
    statementMonthFilter,
    statementStatusFilter,
  ]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const ratedModels = useMemo(
    () =>
      rates.filter((rate) => {
        if (rate.modality === "text")
          return (
            rate.prices.inputPerMillionYuan !== null &&
            rate.prices.outputPerMillionYuan !== null
          );
        if (rate.modality === "image") return rate.prices.perImageYuan !== null;
        if (rate.modality === "embedding")
          return rate.prices.inputPerMillionYuan !== null;
        if (rate.modality === "audio")
          return Object.entries(rate.prices).some(
            ([, value]) => value !== null,
          );
        return Object.values(rate.prices.perSecondByResolution ?? {}).some(
          (value) => value !== null,
        );
      }).length,
    [rates],
  );

  function updateRate(model: string, update: (value: Prices) => Prices) {
    setRateDrafts((current) => ({
      ...current,
      [model]: update(current[model] ?? {}),
    }));
  }

  async function saveRate(rate: Rate) {
    if (!ratePassword) {
      setError("保存价目前请输入当前管理员密码");
      return;
    }
    setBusy(`rate:${rate.model}`);
    setError("");
    setMessage("");
    try {
      await adminApi(
        `/api/internal/billing/rates/${encodeURIComponent(rate.model)}`,
        {
          method: "PUT",
          body: JSON.stringify({
            effectiveMonth: month,
            prices: normalizePrices(rate, rateDrafts[rate.model] ?? {}),
            currentPassword: ratePassword,
          }),
        },
      );
      setRatePassword("");
      setMessage(`${rate.displayName} 价目已保存`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "价目保存失败");
    } finally {
      setBusy("");
    }
  }

  function normalizePrices(rate: Rate, value: Prices): Prices {
    const nullable = (input?: string | null) =>
      input === "" || input == null ? null : input;
    if (rate.modality === "text")
      return {
        inputPerMillionYuan: nullable(value.inputPerMillionYuan),
        outputPerMillionYuan: nullable(value.outputPerMillionYuan),
      };
    if (rate.modality === "image")
      return { perImageYuan: nullable(value.perImageYuan) };
    if (rate.modality === "embedding")
      return { inputPerMillionYuan: nullable(value.inputPerMillionYuan) };
    if (rate.modality === "audio") {
      if (rate.billingMetric === "characters")
        return {
          perTenThousandCharactersYuan: nullable(
            value.perTenThousandCharactersYuan,
          ),
        };
      if (rate.billingUnit === 3600)
        return { perHourYuan: nullable(value.perHourYuan) };
      return { perMinuteYuan: nullable(value.perMinuteYuan) };
    }
    return {
      perSecondByResolution: Object.fromEntries(
        resolutions.map((resolution) => [
          resolution,
          nullable(value.perSecondByResolution?.[resolution]),
        ]),
      ),
    };
  }

  async function saveProject(event: FormEvent) {
    event.preventDefault();
    const discount = Number(projectDraft.discountPercent);
    if (!Number.isFinite(discount) || discount < 0 || discount > 100) {
      setError("项目折扣必须在0%到100%之间");
      return;
    }
    setBusy("project");
    setError("");
    setMessage("");
    try {
      await adminApi(
        `/api/internal/billing/projects/${encodeURIComponent(activeProjectName)}`,
        {
          method: "PUT",
          body: JSON.stringify({
            effectiveMonth: projectDraft.effectiveMonth,
            enabled: projectDraft.enabled,
            discountBps: Math.round(discount * 100),
            currentPassword: projectDraft.currentPassword,
          }),
        },
      );
      setMessage("项目计费规则已保存");
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "项目计费规则保存失败",
      );
    } finally {
      setBusy("");
    }
  }

  async function openStatement(id: string) {
    setBusy(`detail:${id}`);
    setError("");
    try {
      const data = await adminApi(`/api/internal/billing/statements/${id}`);
      setDetail(data.statement as Statement);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "账单详情加载失败");
    } finally {
      setBusy("");
    }
  }

  async function statementAction(
    action: "recalculate" | "confirm" | "mark-paid",
  ) {
    if (!detail) return;
    if (action !== "recalculate" && !statementPassword) {
      setError("请先输入当前管理员密码");
      return;
    }
    setBusy(action);
    setError("");
    try {
      const body =
        action === "mark-paid"
          ? {
              currentPassword: statementPassword,
              reference: payment.reference || null,
              note: payment.note || null,
            }
          : action === "confirm"
            ? { currentPassword: statementPassword }
            : undefined;
      const data = await adminApi(
        `/api/internal/billing/statements/${detail.id}/${action}`,
        { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) },
      );
      setDetail(data.statement as Statement);
      setStatementPassword("");
      setMessage("账单状态已更新");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "账单操作失败");
    } finally {
      setBusy("");
    }
  }

  async function addAdjustment(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;
    setBusy("adjustment");
    setError("");
    try {
      const data = await adminApi(
        `/api/internal/billing/statements/${detail.id}/adjustments`,
        {
          method: "POST",
          body: JSON.stringify({
            ...adjustment,
            currentPassword: statementPassword,
          }),
        },
      );
      setDetail(data.statement as Statement);
      setAdjustment({ amountYuan: "", reason: "" });
      setStatementPassword("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "调整项保存失败");
    } finally {
      setBusy("");
    }
  }

  async function removeAdjustment(id: string) {
    if (!detail || !statementPassword) {
      setError("删除调整项前请输入当前管理员密码");
      return;
    }
    setBusy(`adjustment:${id}`);
    try {
      const data = await adminApi(
        `/api/internal/billing/statements/${detail.id}/adjustments/${id}`,
        {
          method: "DELETE",
          body: JSON.stringify({ currentPassword: statementPassword }),
        },
      );
      setDetail(data.statement as Statement);
      setStatementPassword("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "调整项删除失败");
    } finally {
      setBusy("");
    }
  }

  if (!projects.length)
    return (
      <div className="content">
        <section className="panel emptyState">
          <ReceiptText size={34} />
          <h3>暂无可计费项目</h3>
          <p>创建客户项目后即可设置价目和生成月度账单。</p>
        </section>
      </div>
    );

  return (
    <div className="content billingPage">
      <section className="panel billingHero">
        <div className="billingHeroCopy">
          <span>
            <CircleDollarSign size={24} />
          </span>
          <div>
            <small>BILLING CENTER</small>
            <h2>项目计费账单</h2>
            <p>按真实模型用量生成税前月度账单，草稿确认后永久锁定。</p>
          </div>
        </div>
        <div className="billingSelectors">
          <label>
            客户项目
            <select
              value={activeProjectName}
              onChange={(event) => setProjectName(event.target.value)}
            >
              {projects.map((project) => (
                <option key={project.name} value={project.name}>
                  {project.displayName} · {project.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            账期
            <input
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            />
          </label>
          <button
            className="secondary"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} />
            刷新
          </button>
        </div>
      </section>
      {error && (
        <div className="formError billingNotice" role="alert">
          {error}
          <button onClick={() => setError("")} aria-label="关闭">
            <X size={14} />
          </button>
        </div>
      )}
      {message && (
        <div className="successBanner billingNotice">
          <CheckCircle2 size={16} />
          {message}
        </div>
      )}
      <div className="billingTabs" role="tablist">
        <button
          className={view === "overview" ? "active" : ""}
          onClick={() => setView("overview")}
        >
          <CircleDollarSign size={16} />
          计费概览
        </button>
        <button
          className={view === "rates" ? "active" : ""}
          onClick={() => setView("rates")}
        >
          <Settings2 size={16} />
          模型价目
        </button>
        <button
          className={view === "statements" ? "active" : ""}
          onClick={() => setView("statements")}
        >
          <ReceiptText size={16} />
          月度账单
        </button>
      </div>
      {loading ? (
        <section className="panel billingLoading">
          <LoaderCircle className="spin" />
          <span>正在归集真实用量…</span>
        </section>
      ) : null}

      {!loading && view === "statements" && (
        <div className="billingListFilters">
          <label>
            账期筛选
            <input
              type="month"
              value={statementMonthFilter}
              onChange={(event) => setStatementMonthFilter(event.target.value)}
            />
          </label>
          <label>
            状态筛选
            <select
              value={statementStatusFilter}
              onChange={(event) => setStatementStatusFilter(event.target.value)}
            >
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="confirmed">已确认</option>
              <option value="paid">已支付</option>
            </select>
          </label>
          {(statementMonthFilter || statementStatusFilter) && (
            <button
              className="secondary"
              onClick={() => {
                setStatementMonthFilter("");
                setStatementStatusFilter("");
              }}
            >
              清除筛选
            </button>
          )}
        </div>
      )}

      {!loading && view === "overview" && (
        <>
          <section className="billingStats">
            <article>
              <span className="coral">
                <CircleDollarSign />
              </span>
              <div>
                <small>
                  {month === monthNow() ? "本月预计应付" : "账单应付"}
                </small>
                <b>{money(statement?.totalYuan)}</b>
                <em>税前人民币</em>
              </div>
            </article>
            <article>
              <span className="cyan">
                <ReceiptText />
              </span>
              <div>
                <small>原价用量</small>
                <b>{money(statement?.subtotalYuan)}</b>
                <em>优惠 {money(statement?.discountYuan)}</em>
              </div>
            </article>
            <article>
              <span className="amber">
                <FileClock />
              </span>
              <div>
                <small>待计价调用</small>
                <b>{statement?.pendingCount ?? 0}</b>
                <em>
                  {statement?.pendingCount
                    ? "补齐价目或用量后可结算"
                    : "计费数据完整"}
                </em>
              </div>
            </article>
            <article>
              <span className="purple">
                <Settings2 />
              </span>
              <div>
                <small>已配置模型</small>
                <b>
                  {ratedModels}/{rates.length}
                </b>
                <em>
                  {terms?.enabled
                    ? `项目折扣 ${terms.discountBps / 100}%`
                    : "项目尚未启用计费"}
                </em>
              </div>
            </article>
          </section>
          <section className="panel billingProjectCard">
            <div className="panelHead">
              <div>
                <span className="relaySectionLabel">
                  <CalendarClock size={14} />
                  项目规则
                </span>
                <h3>{activeProject?.displayName}</h3>
                <p>默认从下月生效；本月草稿未确认时也可以选择本月重新计算。</p>
              </div>
              <span
                className={`billingStatus ${terms?.enabled ? "enabled" : "disabled"}`}
              >
                {terms?.enabled ? "计费中" : "未启用"}
              </span>
            </div>
            <form className="billingProjectForm" onSubmit={saveProject}>
              <label className="billingToggle">
                <input
                  type="checkbox"
                  checked={projectDraft.enabled}
                  onChange={(event) =>
                    setProjectDraft({
                      ...projectDraft,
                      enabled: event.target.checked,
                    })
                  }
                />
                <span>
                  <i />
                </span>
                <b>启用项目计费</b>
              </label>
              <label>
                生效月份
                <input
                  type="month"
                  min={monthNow()}
                  value={projectDraft.effectiveMonth}
                  onChange={(event) =>
                    setProjectDraft({
                      ...projectDraft,
                      effectiveMonth: event.target.value,
                    })
                  }
                  required
                />
              </label>
              <label>
                结算比例（%）
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={projectDraft.discountPercent}
                  onChange={(event) =>
                    setProjectDraft({
                      ...projectDraft,
                      discountPercent: event.target.value,
                    })
                  }
                  required
                />
              </label>
              <label>
                当前管理员密码
                <input
                  type="password"
                  autoComplete="current-password"
                  value={projectDraft.currentPassword}
                  onChange={(event) =>
                    setProjectDraft({
                      ...projectDraft,
                      currentPassword: event.target.value,
                    })
                  }
                  required
                />
              </label>
              <button className="primary" disabled={busy === "project"}>
                {busy === "project" ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Save size={16} />
                )}
                保存项目规则
              </button>
            </form>
          </section>
        </>
      )}

      {!loading && view === "rates" && (
        <section className="panel billingRatesPanel">
          <div className="panelHead">
            <div>
              <span className="relaySectionLabel">
                <Settings2 size={14} />
                PRICE BOOK
              </span>
              <h3>{month} 模型价目表</h3>
              <p>
                空值表示待计价，明确填写 0 才表示免费。金额统一为税前人民币。
              </p>
            </div>
            <label className="ratePassword">
              当前管理员密码
              <input
                type="password"
                autoComplete="current-password"
                value={ratePassword}
                onChange={(event) => setRatePassword(event.target.value)}
                placeholder="保存任一模型前填写"
              />
            </label>
          </div>
          <div className="billingRateList">
            {rates.map((rate) => {
              const draft = rateDrafts[rate.model] ?? {};
              return (
                <article key={rate.model} className="billingRateRow">
                  <div className="billingModel">
                    <span>
                      <ModelIcon rate={rate} />
                    </span>
                    <div>
                      <b>{rate.displayName}</b>
                      <code>{rate.model}</code>
                      <small>
                        {providerNames[rate.provider] ?? rate.provider}
                      </small>
                    </div>
                  </div>
                  <div className={`relayTypePill ${rate.modality}`}>
                    {rate.modality === "text" ? (
                      <MessageSquareText size={14} />
                    ) : rate.modality === "image" ? (
                      <ImageIcon size={14} />
                    ) : rate.modality === "embedding" ? (
                      <Network size={14} />
                    ) : rate.modality === "audio" ? (
                      <AudioLines size={14} />
                    ) : (
                      <Video size={14} />
                    )}
                    {rate.modality === "text"
                      ? "文本"
                      : rate.modality === "image"
                        ? "图片"
                        : rate.modality === "embedding"
                          ? "向量"
                          : rate.modality === "audio"
                            ? "音频"
                            : "视频"}
                  </div>
                  <div className="billingRateFields">
                    {rate.modality === "text" && (
                      <>
                        <label>
                          输入 / 百万 Token
                          <input
                            type="number"
                            min="0"
                            step="0.000001"
                            value={draft.inputPerMillionYuan ?? ""}
                            onChange={(event) =>
                              updateRate(rate.model, (value) => ({
                                ...value,
                                inputPerMillionYuan: event.target.value,
                              }))
                            }
                            placeholder="待计价"
                          />
                        </label>
                        <label>
                          输出 / 百万 Token
                          <input
                            type="number"
                            min="0"
                            step="0.000001"
                            value={draft.outputPerMillionYuan ?? ""}
                            onChange={(event) =>
                              updateRate(rate.model, (value) => ({
                                ...value,
                                outputPerMillionYuan: event.target.value,
                              }))
                            }
                            placeholder="待计价"
                          />
                        </label>
                      </>
                    )}
                    {rate.modality === "image" && (
                      <label>
                        每张图片
                        <input
                          type="number"
                          min="0"
                          step="0.000001"
                          value={draft.perImageYuan ?? ""}
                          onChange={(event) =>
                            updateRate(rate.model, (value) => ({
                              ...value,
                              perImageYuan: event.target.value,
                            }))
                          }
                          placeholder="待计价"
                        />
                      </label>
                    )}
                    {rate.modality === "embedding" && (
                      <label>
                        输入 / 百万 Token
                        <input
                          type="number"
                          min="0"
                          step="0.000001"
                          value={draft.inputPerMillionYuan ?? ""}
                          onChange={(event) =>
                            updateRate(rate.model, (value) => ({
                              ...value,
                              inputPerMillionYuan: event.target.value,
                            }))
                          }
                          placeholder="待计价"
                        />
                      </label>
                    )}
                    {rate.modality === "audio" && rate.billingMetric === "characters" && (
                      <label>
                        每万字符
                        <input type="number" min="0" step="0.000001" value={draft.perTenThousandCharactersYuan ?? ""} onChange={(event) => updateRate(rate.model, (value) => ({ ...value, perTenThousandCharactersYuan: event.target.value }))} placeholder="待计价" />
                      </label>
                    )}
                    {rate.modality === "audio" && rate.billingMetric === "audio_second" && (
                      <label>
                        {rate.billingUnit === 3600 ? "每小时" : "每分钟"}
                        <input type="number" min="0" step="0.000001" value={rate.billingUnit === 3600 ? draft.perHourYuan ?? "" : draft.perMinuteYuan ?? ""} onChange={(event) => updateRate(rate.model, (value) => rate.billingUnit === 3600 ? ({ ...value, perHourYuan: event.target.value }) : ({ ...value, perMinuteYuan: event.target.value }))} placeholder="待计价" />
                      </label>
                    )}
                    {rate.modality === "video" &&
                      resolutions.map((resolution) => (
                        <label key={resolution}>
                          {resolution} / 秒
                          <input
                            type="number"
                            min="0"
                            step="0.000001"
                            value={
                              draft.perSecondByResolution?.[resolution] ?? ""
                            }
                            onChange={(event) =>
                              updateRate(rate.model, (value) => ({
                                ...value,
                                perSecondByResolution: {
                                  ...value.perSecondByResolution,
                                  [resolution]: event.target.value,
                                },
                              }))
                            }
                            placeholder="待计价"
                          />
                        </label>
                      ))}
                  </div>
                  <button
                    className="secondary"
                    onClick={() => void saveRate(rate)}
                    disabled={busy === `rate:${rate.model}`}
                  >
                    {busy === `rate:${rate.model}` ? (
                      <LoaderCircle size={15} className="spin" />
                    ) : (
                      <Save size={15} />
                    )}
                    保存
                  </button>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {!loading && view === "statements" && (
        <section className="panel billingStatementsPanel">
          <div className="panelHead">
            <div>
              <span className="relaySectionLabel">
                <ReceiptText size={14} />
                STATEMENTS
              </span>
              <h3>月度账单</h3>
              <p>当前月为滚动预估，月结后的草稿可确认并登记支付。</p>
            </div>
          </div>
          <div className="billingStatementTable">
            <div className="billingStatementHead">
              <span>账期 / 账单号</span>
              <span>原价</span>
              <span>优惠与调整</span>
              <span>应付金额</span>
              <span>状态</span>
              <span />
            </div>
            {statements.map((item) => (
              <div className="billingStatementRow" key={item.id}>
                <div>
                  <b>{item.month}</b>
                  <code>{item.number}</code>
                  <small>更新于 {formatTime(item.updatedAt)}</small>
                </div>
                <span>{money(item.subtotalYuan)}</span>
                <span>
                  -{money(item.discountYuan)} / {money(item.adjustmentYuan)}
                </span>
                <strong>{money(item.totalYuan)}</strong>
                <i className={`billingStatus ${item.status}`}>
                  {item.status === "draft"
                    ? "草稿"
                    : item.status === "confirmed"
                      ? "已确认"
                      : "已支付"}
                </i>
                <button
                  className="secondary"
                  onClick={() => void openStatement(item.id)}
                >
                  {busy === `detail:${item.id}` ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    "查看详情"
                  )}
                </button>
              </div>
            ))}
            {!statements.length && (
              <div className="emptyRow">
                该项目尚未生成账单。启用计费后系统会自动创建自然月草稿。
              </div>
            )}
          </div>
        </section>
      )}

      {detail && (
        <div className="modalBackdrop billingDetailBackdrop">
          <section className="billingDetail" id="billingPrintArea">
            <header>
              <div>
                <small>税前项目对账单</small>
                <h2>{detail.number}</h2>
                <p>
                  {detail.projectName} · {detail.month}
                </p>
              </div>
              <div className="billingDetailActions">
                <a
                  className="secondary"
                  href={`/api/internal/billing/statements/${detail.id}/export.csv`}
                >
                  <Download size={15} />
                  CSV
                </a>
                <button className="secondary" onClick={() => window.print()}>
                  <Printer size={15} />
                  打印
                </button>
                <button
                  className="iconButton"
                  onClick={() => setDetail(null)}
                  aria-label="关闭"
                >
                  <X size={17} />
                </button>
              </div>
            </header>
            <div className="billingPrintSummary">
              <div>
                <small>账单状态</small>
                <b>
                  {detail.status === "draft"
                    ? "草稿"
                    : detail.status === "confirmed"
                      ? "已确认"
                      : "已支付"}
                </b>
              </div>
              <div>
                <small>原价合计</small>
                <b>{money(detail.subtotalYuan)}</b>
              </div>
              <div>
                <small>优惠金额</small>
                <b>-{money(detail.discountYuan)}</b>
              </div>
              <div>
                <small>应付金额</small>
                <strong>{money(detail.totalYuan)}</strong>
              </div>
            </div>
            {detail.pendingCount > 0 && (
              <div className="billingPending">
                <FileClock size={16} />
                <b>{detail.pendingCount} 条调用待计价</b>
                <span>补齐缺失价目或真实用量后才能确认账单。</span>
              </div>
            )}
            <div className="billingLineTable">
              <div className="billingLineHead">
                <span>模型</span>
                <span>计费项</span>
                <span>数量</span>
                <span>单价</span>
                <span>折后金额</span>
              </div>
              {detail.lines.map((line) => (
                <div className="billingLineRow" key={line.id}>
                  <code>{line.model}</code>
                  <span>
                    {metricNames[line.metric] ?? line.metric}
                    {line.resolution ? ` · ${line.resolution}` : ""}
                  </span>
                  <span>{Number(line.quantity).toLocaleString("zh-CN")}</span>
                  <span>{money(line.unitPriceYuan)}</span>
                  <b>{money(line.netAmountYuan)}</b>
                </div>
              ))}
              {!detail.lines.length && (
                <div className="emptyRow">暂无已计价用量</div>
              )}
            </div>
            {detail.adjustments.length > 0 && (
              <div className="billingAdjustments">
                <h3>调整项</h3>
                {detail.adjustments.map((item) => (
                  <div key={item.id}>
                    <span>{item.reason}</span>
                    <b>{money(item.amountYuan)}</b>
                    {detail.status === "draft" && (
                      <button
                        className="iconButton"
                        onClick={() => void removeAdjustment(item.id)}
                        aria-label="删除调整项"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            <footer className="billingDetailFooter">
              <div>
                <small>生成时间 {formatTime(detail.generatedAt)}</small>
                <small>本账单为内部税前对账凭证，不属于法定发票。</small>
              </div>
              <strong>应付合计 {money(detail.totalYuan)}</strong>
            </footer>
            {detail.status !== "paid" && (
              <div className="billingFinanceActions">
                <label>
                  当前管理员密码
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={statementPassword}
                    onChange={(event) =>
                      setStatementPassword(event.target.value)
                    }
                    placeholder="敏感财务操作前填写"
                  />
                </label>
                {detail.status === "draft" && (
                  <form onSubmit={addAdjustment}>
                    <input
                      value={adjustment.amountYuan}
                      onChange={(event) =>
                        setAdjustment({
                          ...adjustment,
                          amountYuan: event.target.value,
                        })
                      }
                      placeholder="调整金额，可为负数"
                      required
                    />
                    <input
                      value={adjustment.reason}
                      onChange={(event) =>
                        setAdjustment({
                          ...adjustment,
                          reason: event.target.value,
                        })
                      }
                      placeholder="调整原因"
                      required
                    />
                    <button className="secondary">添加调整</button>
                  </form>
                )}
                {detail.status === "confirmed" && (
                  <div className="billingPaymentFields">
                    <input
                      value={payment.reference}
                      onChange={(event) =>
                        setPayment({
                          ...payment,
                          reference: event.target.value,
                        })
                      }
                      placeholder="支付凭证号（可选）"
                    />
                    <input
                      value={payment.note}
                      onChange={(event) =>
                        setPayment({ ...payment, note: event.target.value })
                      }
                      placeholder="支付备注（可选）"
                    />
                  </div>
                )}
                <div className="billingActionButtons">
                  {detail.status === "draft" && (
                    <button
                      className="secondary"
                      onClick={() => void statementAction("recalculate")}
                      disabled={busy === "recalculate"}
                    >
                      <RefreshCw size={15} />
                      重新计算
                    </button>
                  )}
                  {detail.status === "draft" && (
                    <button
                      className="primary"
                      onClick={() => void statementAction("confirm")}
                      disabled={
                        busy === "confirm" || detail.month >= monthNow()
                      }
                    >
                      确认并锁定
                    </button>
                  )}
                  {detail.status === "confirmed" && (
                    <button
                      className="primary"
                      onClick={() => void statementAction("mark-paid")}
                      disabled={busy === "mark-paid"}
                    >
                      标记全额已支付
                    </button>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
