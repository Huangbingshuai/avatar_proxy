"use client";

import {
  AudioLines,
  BookOpenCheck,
  Image as ImageIcon,
  LoaderCircle,
  MessageSquareText,
  Network,
  RefreshCw,
  Save,
  Video,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { AdminApi } from "./admin-api";
import { getModelIconPath } from "./model-icon-library";

type RateRule = {
  metric: string;
  dimension: string;
  unitSize: number;
  unitPriceYuan: string | null;
  sourceMonth?: string;
};

type GlobalRate = {
  model: string;
  displayName: string;
  provider: string;
  modality: "text" | "image" | "video" | "embedding" | "audio";
  configured: boolean;
  rules: RateRule[];
  editableRules: RateRule[];
  officialSource?: { version: string; url: string } | null;
};

const providers: Record<string, string> = {
  volcengine_ark: "火山方舟",
  volcengine_speech: "豆包语音",
  openai: "OpenAI",
  maxmodel: "MaxModel",
  aliyun_bailian: "阿里百炼",
  minimax: "MiniMax",
};

const metrics: Record<string, string> = {
  input_tokens: "输入 Token",
  cached_input_tokens: "缓存输入 Token",
  output_tokens: "输出 / 视频 Token",
  image: "图片",
  video_second: "视频时长",
  characters: "字符",
  audio_second: "音频时长",
};

function currentMonth() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  return `${parts.find((item) => item.type === "year")?.value}-${parts.find((item) => item.type === "month")?.value}`;
}

function unitLabel(rule: RateRule) {
  if (rule.unitSize === 1_000_000) return "/ 百万 Token";
  if (rule.metric === "characters" && rule.unitSize === 10_000) return "/ 万字符";
  if (rule.metric === "audio_second" && rule.unitSize === 3_600) return "/ 小时";
  if (rule.metric === "audio_second" && rule.unitSize === 60) return "/ 分钟";
  if (rule.metric === "video_second") return "/ 秒";
  return "/ 次";
}

function dimensionLabel(value: string) {
  if (!value) return "标准";
  return value
    .replace("tokens:0-32000", "上下文 ≤32K")
    .replace("tokens:32001-128000", "上下文 32K–128K")
    .replace("tokens:128001-256000", "上下文 128K–256K")
    .replace("input:after_first", "输入图（首张后）")
    .replace("output:le2610000", "输出图 ≤261万像素")
    .replace("output:gt2610000", "输出图 >261万像素")
    .replace(":no_video", " · 无视频输入")
    .replace(":video", " · 有视频输入")
    .replace("text", "文本输入")
    .replace("image", "图片输入");
}

function RateIcon({ rate }: { rate: GlobalRate }) {
  const path = getModelIconPath(rate.model);
  if (path) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={path} alt="" />;
  }
  if (rate.modality === "image") return <ImageIcon />;
  if (rate.modality === "video") return <Video />;
  if (rate.modality === "embedding") return <Network />;
  if (rate.modality === "audio") return <AudioLines />;
  return <MessageSquareText />;
}

export default function GlobalModelRatesPanel({ adminApi }: { adminApi: AdminApi }) {
  const [month, setMonth] = useState(currentMonth());
  const [rates, setRates] = useState<GlobalRate[]>([]);
  const [drafts, setDrafts] = useState<Record<string, RateRule[]>>({});
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await adminApi(`/api/internal/billing/rates?month=${month}`);
      const next = (data.rates ?? []) as GlobalRate[];
      setRates(next);
      setDrafts(Object.fromEntries(next.map((rate) => [rate.model, rate.editableRules.map((rule) => ({ ...rule, unitPriceYuan: rule.unitPriceYuan ?? "" }))])));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "全局价目加载失败");
    } finally {
      setLoading(false);
    }
  }, [adminApi, month]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const configuredCount = useMemo(() => rates.filter((rate) => rate.configured).length, [rates]);

  function updatePrice(model: string, index: number, value: string) {
    setDrafts((current) => ({
      ...current,
      [model]: (current[model] ?? []).map((rule, position) =>
        position === index ? { ...rule, unitPriceYuan: value } : rule,
      ),
    }));
  }

  async function save(rate: GlobalRate) {
    if (!password) {
      setError("保存全局价目前请输入超级管理员当前密码");
      return;
    }
    setBusy(rate.model);
    setError("");
    setMessage("");
    try {
      await adminApi(`/api/internal/billing/rates/${encodeURIComponent(rate.model)}`, {
        method: "PUT",
        body: JSON.stringify({
          effectiveMonth: month,
          prices: { rules: drafts[rate.model] ?? [] },
          currentPassword: password,
        }),
      });
      setMessage(`${rate.displayName} 的全局价格已应用到全部项目`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "全局价目保存失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel adminSection globalRatesPanel">
      <div className="panelHead globalRatesHead">
        <div>
          <span className="relaySectionLabel"><BookOpenCheck size={14} />GLOBAL PRICE BOOK</span>
          <h3>全局模型价目</h3>
          <p>由超级管理员统一维护，所有启用计费的项目共用；项目仅叠加自己的结算折扣。</p>
        </div>
        <div className="globalRatesControls">
          <label>生效月份<input type="month" min={currentMonth()} value={month} onChange={(event) => setMonth(event.target.value)} /></label>
          <label>超级管理员密码<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="保存前填写" /></label>
          <button className="secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""} />刷新</button>
        </div>
      </div>
      <div className="globalRatesSummary"><b>{configuredCount}/{rates.length}</b><span>个模型已配置全局价格</span><em>空价目表示待计价，不会按 ¥0 结算</em></div>
      {error && <div className="formError">{error}</div>}
      {message && <div className="successBanner">{message}</div>}
      <div className="globalRateList">
        {rates.map((rate) => (
          <article className="globalRateRow" key={rate.model}>
            <div className="globalRateIdentity">
              <span><RateIcon rate={rate} /></span>
              <div><b>{rate.displayName}</b><code>{rate.model}</code><small>{providers[rate.provider] ?? rate.provider}</small></div>
            </div>
            <div className="globalRateRules">
              {(drafts[rate.model] ?? []).map((rule, index) => (
                <label key={`${rule.metric}:${rule.dimension}`}>
                  <span>{metrics[rule.metric] ?? rule.metric}<small>{dimensionLabel(rule.dimension)} {unitLabel(rule)}</small></span>
                  <span className="globalRateInput"><i>¥</i><input aria-label={`${rate.model} ${rule.metric} ${rule.dimension}`} type="number" min="0" step="0.000001" value={rule.unitPriceYuan ?? ""} onChange={(event) => updatePrice(rate.model, index, event.target.value)} /></span>
                </label>
              ))}
              {(drafts[rate.model] ?? []).length === 0 && <div className="globalRateEmpty">尚未配置计价规则</div>}
            </div>
            <div className="globalRateAction">
              {rate.officialSource ? <a href={rate.officialSource.url} target="_blank" rel="noreferrer">火山官方价 · {rate.officialSource.version}</a> : <span>人工定价</span>}
              <button className="primary" type="button" onClick={() => void save(rate)} disabled={busy === rate.model || (drafts[rate.model] ?? []).length === 0}>{busy === rate.model ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}保存</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
