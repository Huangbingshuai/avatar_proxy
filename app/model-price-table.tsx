"use client";

import {
  AudioLines,
  BookOpenCheck,
  CalendarDays,
  CircleDollarSign,
  Image as ImageIcon,
  LoaderCircle,
  MessageSquareText,
  Network,
  RefreshCw,
  Video,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { AdminApi } from "./admin-api";
import ModelCatalogFilters from "./model-catalog-filters";
import { getModelIconPath } from "./model-icon-library";

type PriceRule = {
  metric: string;
  dimension: string;
  unitSize: number;
  unitPriceYuan: string;
  sourceMonth?: string;
};

type ModelRate = {
  model: string;
  displayName: string;
  provider: string;
  modality: "text" | "image" | "video" | "embedding" | "audio";
  configured: boolean;
  sourceMonths: string[];
  rules: PriceRule[];
};

const providerLabels: Record<string, string> = {
  volcengine_ark: "火山方舟",
  volcengine_speech: "豆包语音",
  openai: "OpenAI",
  maxmodel: "MaxModel",
  aliyun_bailian: "阿里百炼",
  minimax: "MiniMax",
};

const modalityLabels: Record<string, string> = {
  text: "文本",
  image: "图片",
  video: "视频",
  embedding: "向量",
  audio: "音频",
};

function currentMonth() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  return `${parts.find((item) => item.type === "year")?.value}-${parts.find((item) => item.type === "month")?.value}`;
}

function metricLabel(rate: ModelRate, rule: PriceRule) {
  if (rule.metric === "input_tokens") return "输入 Token";
  if (rule.metric === "cached_input_tokens") return "缓存输入 Token";
  if (rule.metric === "output_tokens") return rate.modality === "video" ? "视频 Token" : "输出 Token";
  if (rule.metric === "image") return "图片";
  if (rule.metric === "video_second") return "视频时长";
  if (rule.metric === "characters") return "字符";
  if (rule.metric === "audio_second") return "音频时长";
  return rule.metric;
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

function unitLabel(rule: PriceRule) {
  if (rule.unitSize === 1_000_000) return "每百万 Token";
  if (rule.metric === "characters" && rule.unitSize === 10_000) return "每万字符";
  if (rule.metric === "audio_second" && rule.unitSize === 3_600) return "每小时";
  if (rule.metric === "audio_second" && rule.unitSize === 60) return "每分钟";
  if (rule.metric === "video_second") return "每秒";
  if (rule.metric === "image") return "每张";
  return `每 ${rule.unitSize.toLocaleString("zh-CN")} 单位`;
}

function ModelIcon({ rate }: { rate: ModelRate }) {
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

export default function ModelPriceTable({ adminApi }: { adminApi: AdminApi }) {
  const [month, setMonth] = useState(currentMonth());
  const [rates, setRates] = useState<ModelRate[]>([]);
  const [provider, setProvider] = useState("");
  const [modality, setModality] = useState("");
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await adminApi(`/api/internal/billing/rates?month=${month}`);
      setRates((data.rates ?? []) as ModelRate[]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "模型价格加载失败");
    } finally {
      setLoading(false);
    }
  }, [adminApi, month]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const configuredCount = useMemo(() => rates.filter((rate) => rate.configured).length, [rates]);
  const ruleCount = useMemo(() => rates.reduce((total, rate) => total + rate.rules.length, 0), [rates]);
  const filteredRates = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("zh-CN");
    return rates.filter((rate) => {
      if (provider && rate.provider !== provider) return false;
      if (modality && rate.modality !== modality) return false;
      if (status === "configured" && !rate.configured) return false;
      if (status === "pending" && rate.configured) return false;
      return !needle || rate.model.toLocaleLowerCase("zh-CN").includes(needle) || rate.displayName.toLocaleLowerCase("zh-CN").includes(needle);
    });
  }, [modality, provider, rates, search, status]);

  return (
    <div className="modelPricePage">
      <section className="panel modelPriceHero">
        <div className="modelPriceHeroCopy">
          <span><BookOpenCheck size={24} /></span>
          <div><small>READ-ONLY PRICE BOOK</small><h2>模型价格表</h2><p>完整展示超级管理员配置的人民币税前价格；管理员仅可查看，不能在此修改。</p></div>
        </div>
        <div className="modelPriceControls">
          <label><CalendarDays size={15} /><span>查询账期</span><input aria-label="模型价格账期" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>
          <button className="secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />刷新价格</button>
        </div>
      </section>

      <section className="modelPriceStats" aria-label="价格表概览">
        <article><span className="coral"><CircleDollarSign size={20} /></span><div><small>已定价模型</small><b>{configuredCount} / {rates.length}</b></div></article>
        <article><span className="cyan"><BookOpenCheck size={20} /></span><div><small>完整计价规则</small><b>{ruleCount}</b></div></article>
        <article><span className="amber"><CalendarDays size={20} /></span><div><small>当前查询账期</small><b>{month}</b></div></article>
      </section>

      <section className="panel modelPriceCatalog">
        <div className="panelHead"><div><h3>全部模型价格</h3><p>每条价格均按计价指标、输入类型、上下文档位或分辨率独立展示。</p></div><span className="readOnlyBadge">只读</span></div>
        <ModelCatalogFilters
          items={rates}
          provider={provider}
          modality={modality}
          search={search}
          onProviderChange={setProvider}
          onModalityChange={setModality}
          onSearchChange={setSearch}
          providerLabels={providerLabels}
          modalityLabels={modalityLabels}
          resultCount={filteredRates.length}
          searchLabel="搜索模型价格"
          status={{
            value: status,
            onChange: setStatus,
            options: [
              { value: "all", label: "全部", count: rates.length },
              { value: "configured", label: "已定价", count: configuredCount },
              { value: "pending", label: "待定价", count: rates.length - configuredCount },
            ],
          }}
        />
        {error && <div className="formError">{error}</div>}
        <div className="modelPriceList">
          {filteredRates.map((rate) => (
            <article className={`modelPriceRow ${rate.configured ? "configured" : "pending"}`} key={rate.model}>
              <div className="modelPriceIdentity">
                <span className="modelPriceIcon"><ModelIcon rate={rate} /></span>
                <div><b>{rate.model}</b><small>{providerLabels[rate.provider] ?? rate.provider} · {modalityLabels[rate.modality] ?? rate.modality}</small><em>{rate.sourceMonths.length ? `价格版本 ${rate.sourceMonths.join("、")}` : "等待超级管理员配置"}</em></div>
              </div>
              {rate.rules.length ? (
                <div className="modelPriceRules">
                  {rate.rules.map((rule) => (
                    <div className="modelPriceRule" key={`${rule.metric}:${rule.dimension}`}>
                      <div><b>{metricLabel(rate, rule)}</b><small>{dimensionLabel(rule.dimension)}</small></div>
                      <div><strong>¥{Number(rule.unitPriceYuan).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 6 })}</strong><small>{unitLabel(rule)}</small></div>
                    </div>
                  ))}
                </div>
              ) : <div className="modelPricePending">待定价<span>未配置价格不代表免费</span></div>}
            </article>
          ))}
          {loading && <div className="modelPriceState"><LoaderCircle size={20} className="spin" />正在加载完整价格表…</div>}
          {!loading && rates.length > 0 && filteredRates.length === 0 && <div className="modelPriceState">没有符合当前筛选条件的模型。</div>}
          {!loading && rates.length === 0 && !error && <div className="modelPriceState">当前模型目录为空。</div>}
        </div>
      </section>
    </div>
  );
}
