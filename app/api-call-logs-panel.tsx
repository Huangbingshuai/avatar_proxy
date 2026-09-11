"use client";

import {
  Braces,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock3,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { AdminApi } from "./admin-api";

type Project = { name: string; displayName: string };
type ApiKey = { id: string; name: string; keyPrefix: string; projectName: string };

type CallLog = {
  id: number;
  requestId: string;
  apiKeyId: string;
  apiKeyName: string;
  apiKeyPrefix: string;
  projectName: string;
  method: string;
  path: string;
  routeTemplate: string;
  action: string;
  modelAlias?: string | null;
  requestParams: Record<string, unknown>;
  statusCode: number;
  success: boolean;
  responseSummary: Record<string, unknown>;
  errorCode?: string | null;
  errorMessage?: string | null;
  durationMs: number;
  responseBytes: number;
  sourceIp?: string | null;
  userAgent?: string | null;
  isModelCall: boolean;
  createdAt: string;
};

const PAGE_SIZE = 50;

function formatTime(value: string) {
  const normalized = value.endsWith("Z") ? value : `${value}Z`;
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(normalized));
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function pretty(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2);
}

export default function ApiCallLogsPanel({
  projects,
  apiKeys,
  adminApi,
}: {
  projects: Project[];
  apiKeys: ApiKey[];
  adminApi: AdminApi;
}) {
  const [projectName, setProjectName] = useState("");
  const [apiKeyId, setApiKeyId] = useState("");
  const [items, setItems] = useState<CallLog[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const availableKeys = useMemo(
    () => apiKeys.filter((key) => Boolean(projectName) && key.projectName === projectName),
    [apiKeys, projectName],
  );
  const selectedKey = useMemo(() => apiKeys.find((key) => key.id === apiKeyId), [apiKeys, apiKeyId]);

  const load = useCallback(async () => {
    if (!apiKeyId) {
      setItems([]);
      setTotal(0);
      setExpanded(null);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({
        apiKeyId,
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      const data = await adminApi(`/api/internal/call-logs?${query.toString()}`);
      const nextItems = (data.items ?? []) as CallLog[];
      setItems(nextItems);
      setTotal(Number(data.total ?? 0));
      setExpanded((current) => (
        current !== null && nextItems.some((item) => item.id === current) ? current : null
      ));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "调用日志加载失败");
    } finally {
      setLoading(false);
    }
  }, [adminApi, apiKeyId, offset]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    const interval = apiKeyId ? window.setInterval(() => void load(), 5000) : undefined;
    return () => {
      window.clearTimeout(timer);
      if (interval) window.clearInterval(interval);
    };
  }, [apiKeyId, load]);

  const first = total ? offset + 1 : 0;
  const last = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="content callLogsConsole">
      <div className="pageIntro">
        <div>
          <p className="eyebrow">REQUEST LEDGER</p>
          <h2>业务调用日志</h2>
          <p>先选择项目与业务 Key，系统会立即展示该 Key 的接口调用明细。</p>
        </div>
        <span className={`callLogLive${apiKeyId ? " active" : ""}`}>
          <i />{apiKeyId ? "实时更新" : "等待选择 Key"}
        </span>
      </div>

      <section className="callLogFilters callLogSelectors" aria-label="调用日志范围">
        <label>
          客户项目
          <select
            value={projectName}
            onChange={(event) => {
              setProjectName(event.target.value);
              setApiKeyId("");
              setOffset(0);
              setExpanded(null);
            }}
          >
            <option value="">请选择客户项目</option>
            {projects.map((project) => (
              <option key={project.name} value={project.name}>{project.displayName} · {project.name}</option>
            ))}
          </select>
        </label>
        <label>
          业务 Key
          <select
            value={apiKeyId}
            disabled={!projectName}
            onChange={(event) => {
              setApiKeyId(event.target.value);
              setOffset(0);
              setExpanded(null);
            }}
          >
            <option value="">{projectName ? "请选择业务 Key" : "请先选择客户项目"}</option>
            {availableKeys.map((key) => (
              <option key={key.id} value={key.id}>{key.name} · {key.keyPrefix}</option>
            ))}
          </select>
        </label>
      </section>

      {error && <div className="errorBanner"><XCircle size={16} />{error}</div>}

      <section className="panel callLogPanel">
        <div className="panelHead">
          <div>
            <h3>调用明细</h3>
            <p>{selectedKey ? `${selectedKey.name} · 共 ${total.toLocaleString()} 条，当前显示 ${first.toLocaleString()}–${last.toLocaleString()}` : "选择业务 Key 后自动展示调用记录"}</p>
          </div>
          <span className="callLogPrivacy"><Braces size={14} />敏感字段已脱敏</span>
        </div>
        <div className="dataTable callLogTable">
          <div className="tableRow tableHead">
            <span>时间</span><span>业务 Key / 项目</span><span>接口</span><span>模型</span>
            <span>结果</span><span>耗时</span><span>返回量</span><span />
          </div>
          {items.map((item) => (
            <div className="callLogEntry" key={item.id}>
              <div className="tableRow">
                <span className="callLogTime"><Clock3 size={13} />{formatTime(item.createdAt)}</span>
                <span><b>{item.apiKeyName}</b><small>{item.apiKeyPrefix || item.apiKeyId} · {item.projectName}</small></span>
                <span><b className="callLogRoute"><i>{item.method}</i>{item.routeTemplate || item.path}</b><small>{item.requestId}</small></span>
                <span>{item.modelAlias ? <code>{item.modelAlias}</code> : <small>非模型接口</small>}</span>
                <span className={`callLogResult ${item.success ? "success" : "failed"}`}>
                  {item.success ? <CheckCircle2 size={14} /> : <XCircle size={14} />}{item.statusCode}
                </span>
                <span>{item.durationMs.toLocaleString()} ms</span>
                <span>{formatBytes(item.responseBytes)}</span>
                <span>
                  <button
                    className="callLogExpand"
                    type="button"
                    onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                    aria-label={expanded === item.id ? "收起详情" : "展开详情"}
                  >
                    {expanded === item.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </span>
              </div>
              {expanded === item.id && (
                <div className="callLogDetail">
                  <div className="callLogMeta">
                    <span><b>来源 IP</b>{item.sourceIp || "未记录"}</span>
                    <span><b>操作</b>{item.action}</span>
                    <span><b>模型请求</b>{item.isModelCall ? "是" : "否"}</span>
                    <span><b>User-Agent</b>{item.userAgent || "未记录"}</span>
                  </div>
                  {!item.success && (item.errorCode || item.errorMessage) && (
                    <div className="callLogError"><b>{item.errorCode || `HTTP ${item.statusCode}`}</b><span>{item.errorMessage}</span></div>
                  )}
                  <div className="callLogPayloads">
                    <article><header>请求参数摘要</header><pre>{pretty(item.requestParams)}</pre></article>
                    <article><header>返回信息摘要</header><pre>{pretty(item.responseSummary)}</pre></article>
                  </div>
                </div>
              )}
            </div>
          ))}
          {!apiKeyId && !loading && <div className="emptyRow">请先选择客户项目，再选择要查看的业务 Key</div>}
          {apiKeyId && !items.length && !loading && <div className="emptyRow">该业务 Key 暂无调用日志</div>}
          {loading && <div className="emptyRow">正在加载调用日志…</div>}
        </div>
        {apiKeyId && total > PAGE_SIZE && (
          <div className="callLogPagination">
            <button className="secondary" type="button" disabled={offset === 0 || loading} onClick={() => { setExpanded(null); setOffset(Math.max(0, offset - PAGE_SIZE)); }}>
              <ChevronLeft size={15} />上一页
            </button>
            <span>第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
            <button className="secondary" type="button" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => { setExpanded(null); setOffset(offset + PAGE_SIZE); }}>
              下一页<ChevronRight size={15} />
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
