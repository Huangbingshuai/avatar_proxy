export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const DEFAULT_MODEL = "doubao-seedance-2-0-260128";

export type VideoModelOption = {
  id: string;
  label: string;
};

const DEFAULT_VIDEO_MODELS: VideoModelOption[] = [
  { id: "doubao-seedance-2-0-260128", label: "Doubao-Seedance-2.0" },
  { id: "doubao-seedance-1-5-pro-251215", label: "Seedance-1.5-Pro" },
  { id: "doubao-seedance-1-0-pro-250528", label: "Seedance-1.0-Pro" },
];

function readVideoModels(): VideoModelOption[] {
  const configured = String(import.meta.env.VITE_VIDEO_MODELS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .flatMap((item) => {
      const [id, label] = item.split("|").map((part) => part.trim());
      return id ? [{ id, label: label || id }] : [];
    });
  const models = new Map(DEFAULT_VIDEO_MODELS.map((model) => [model.id, model]));
  for (const model of configured) models.set(model.id, model);
  return [...models.values()];
}

export const VIDEO_MODELS = readVideoModels();

export type VideoTask = {
  id: string;
  status: string;
  model?: string;
  created_at?: number;
  updated_at?: number;
  progress?: number;
  error?: { code?: string; message?: string };
  content?: { video_url?: string; last_frame_url?: string };
  output?: { video_url?: string; last_frame_url?: string };
  video_url?: string;
  last_frame_url?: string;
};

export type UsageDay = {
  date: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  requestCount: number;
};

export type UsageStats = {
  summary: Omit<UsageDay, "date">;
  daily: UsageDay[];
};

export type ArkUsageMetric = number;

export type ArkUsageRecord = {
  date?: string;
  modelName: string;
  modelUnitId?: string;
  endpointId?: string;
  inputTokens: ArkUsageMetric;
  outputTokens: ArkUsageMetric;
  totalTokens: ArkUsageMetric;
  requestCount: ArkUsageMetric;
  metrics?: Record<string, ArkUsageMetric>;
};

export type ArkUsageStats = {
  source: "volcengine_ark";
  scope: "ark_api_key";
  keySuffix: string;
  start: string;
  end: string;
  interval: "Day" | "Hour";
  dataDelayMinutes: { min: number; max: number };
  billingAmountIncluded: false;
  summary: {
    inputTokens: ArkUsageMetric;
    outputTokens: ArkUsageMetric;
    totalTokens: ArkUsageMetric;
    requestCount: ArkUsageMetric;
    metrics: Record<string, ArkUsageMetric>;
  };
  records: ArkUsageRecord[];
  upstreamRequestId?: string;
};

export type ApiSession = {
  authenticated: true;
  apiKeyId: string;
};

export type VideoGeneratePayload = {
  model: string;
  content: Array<Record<string, unknown>>;
  ratio?: string;
  duration?: number;
  resolution?: string;
  generateAudio: boolean;
  returnLastFrame: boolean;
  metadata?: {
    prompt: string;
    promptDocument?: string;
    assets: Array<Pick<Asset, "id" | "groupId" | "name" | "status" | "previewUrl">>;
    durationMode?: "seconds" | "smart";
    generationCount?: number;
  };
};

export type VideoHistoryRecord = {
  id: string;
  createdAt: number;
  prompt: string;
  promptDocument?: string;
  assetName?: string;
  assetNames?: string[];
  assets?: Array<Pick<Asset, "id" | "groupId" | "name" | "status" | "previewUrl">>;
  model?: string;
  ratio?: string;
  duration?: number;
  durationMode?: "seconds" | "smart";
  resolution?: string;
  generationCount?: number;
  generateAudio?: boolean;
  status?: string;
  videoUrl?: string;
  lastFrameUrl?: string;
};

export type AssetType = "Image" | "Video" | "Audio";

export type MediaMetadata = Record<string, string | number | boolean | null>;

export type UploadResult = {
  url: string;
  uploadId?: string;
  assetType?: AssetType;
  contentType?: string;
  size?: number;
  key?: string;
  mediaMetadata?: MediaMetadata;
};

export type AssetGroup = {
  id: string;
  name: string;
  description: string;
  assetCount?: number;
  createdAt?: string;
};

export type Asset = {
  id: string;
  groupId: string;
  name: string;
  status: string;
  assetType: AssetType;
  previewUrl: string;
  createdAt?: string;
};

export type PageResult<T> = {
  items: T[];
  total: number;
  pageNumber: number;
  pageSize: number;
};

type ApiErrorShape = {
  error?: { message?: string; code?: string };
  detail?: string | Array<{ msg?: string }>;
  message?: string;
  ResponseMetadata?: { Error?: { Message?: string; Code?: string } };
};

type UnknownRecord = Record<string, unknown>;
const inFlightReads = new Map<string, Promise<unknown>>();
const BROWSER_CACHE_PREFIX = "avatar-studio:data-cache:v1";
const BROWSER_CACHE_MAX_AGE_MS = 10 * 60 * 1000;

type BrowserCacheEntry<T> = {
  cachedAt: number;
  data: T;
};

function apiKeyFingerprint(apiKey: string) {
  let hash = 2166136261;
  for (let index = 0; index < apiKey.length; index += 1) {
    hash ^= apiKey.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function browserCacheKey(apiKey: string, resource: "groups" | "assets", path: string) {
  return `${BROWSER_CACHE_PREFIX}:${apiKeyFingerprint(apiKey)}:${resource}:${encodeURIComponent(path)}`;
}

function readBrowserCache<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const entry = JSON.parse(raw) as BrowserCacheEntry<T>;
    if (!entry.cachedAt || Date.now() - entry.cachedAt > BROWSER_CACHE_MAX_AGE_MS) {
      window.sessionStorage.removeItem(key);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

function writeBrowserCache<T>(key: string, data: T) {
  if (typeof window === "undefined") return;
  try {
    const entry: BrowserCacheEntry<T> = { cachedAt: Date.now(), data };
    window.sessionStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // Private browsing and storage quotas must not block normal API requests.
  }
}

function invalidateBrowserCache(apiKey: string, resource?: "groups" | "assets") {
  if (typeof window === "undefined") return;
  const scope = `${BROWSER_CACHE_PREFIX}:${apiKeyFingerprint(apiKey)}:`;
  const prefix = resource ? `${scope}${resource}:` : scope;
  try {
    const removals: string[] = [];
    for (let index = 0; index < window.sessionStorage.length; index += 1) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith(prefix)) removals.push(key);
    }
    for (const key of removals) window.sessionStorage.removeItem(key);
  } catch {
    // Cache invalidation is best-effort; network data remains authoritative.
  }
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function firstValue(record: UnknownRecord, keys: string[]) {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return undefined;
}

function firstString(record: UnknownRecord, keys: string[], fallback = "") {
  const value = firstValue(record, keys);
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

function firstNumber(record: UnknownRecord, keys: string[]) {
  const value = firstValue(record, keys);
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function normalizeAssetType(value: string): AssetType {
  const normalized = value.trim().toLowerCase();
  if (normalized === "video") return "Video";
  if (normalized === "audio") return "Audio";
  return "Image";
}

function resultRecord(value: unknown): UnknownRecord {
  if (!isRecord(value)) return {};
  const result = firstValue(value, ["Result", "result", "Data", "data"]);
  return isRecord(result) ? result : value;
}

function resultItems(value: unknown, keys: string[]) {
  const result = resultRecord(value);
  for (const key of [...keys, "Items", "items", "List", "list"]) {
    const candidate = result[key];
    if (Array.isArray(candidate)) return candidate.filter(isRecord);
  }
  return [];
}

function errorMessage(value: unknown, status: number) {
  if (!isRecord(value)) return `请求失败（HTTP ${status}）`;
  const data = value as ApiErrorShape;
  if (data.error?.message) return data.error.message;
  if (data.ResponseMetadata?.Error?.Message) return data.ResponseMetadata.Error.Message;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    const details = data.detail.map((item) => item.msg).filter(Boolean).join("；");
    if (details) return details;
  }
  return data.message || `请求失败（HTTP ${status}）`;
}

async function apiRequest<T>(
  path: string,
  apiKey: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiKey.trim()}`);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: unknown = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text };
    }
  }
  if (!response.ok) throw new Error(errorMessage(data, response.status));
  return data as T;
}

export function authenticateApiKey(apiKey: string) {
  return apiRequest<ApiSession>("/api/auth/me", apiKey);
}

async function apiRead<T>(path: string, apiKey: string): Promise<T> {
  const cacheKey = `${apiKey}\u0000${path}`;
  const existing = inFlightReads.get(cacheKey);
  if (existing) return existing as Promise<T>;
  const request = apiRequest<T>(path, apiKey);
  inFlightReads.set(cacheKey, request);
  try {
    return await request;
  } finally {
    if (inFlightReads.get(cacheKey) === request) inFlightReads.delete(cacheKey);
  }
}

function queryString(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  return search.toString();
}

function assetGroupsListPath(options: { pageNumber?: number; pageSize?: number; name?: string } = {}) {
  const pageNumber = options.pageNumber ?? 1;
  const pageSize = options.pageSize ?? 20;
  const query = queryString({ pageNumber, pageSize, name: options.name?.trim() });
  return { pageNumber, pageSize, path: `/api/asset-group/list?${query}` };
}

function assetsListPath(
  groupId: string,
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const pageNumber = options.pageNumber ?? 1;
  const pageSize = options.pageSize ?? 20;
  const query = queryString({ groupId, pageNumber, pageSize, name: options.name?.trim() });
  return { pageNumber, pageSize, path: `/api/asset/list?${query}` };
}

export function normalizeAssetGroups(
  response: unknown,
  pageNumber: number,
  pageSize: number,
): PageResult<AssetGroup> {
  const result = resultRecord(response);
  const items = resultItems(response, ["AssetGroups", "assetGroups", "Groups", "groups"])
    .map((item): AssetGroup => ({
      id: firstString(item, ["Id", "id", "GroupId", "groupId", "AssetGroupId", "assetGroupId"]),
      name: firstString(item, ["Name", "name", "GroupName", "groupName"], "未命名素材库"),
      description: firstString(item, ["Description", "description"]),
      assetCount: firstNumber(item, ["AssetCount", "assetCount", "TotalAssetCount", "totalAssetCount"]),
      createdAt: firstString(item, ["CreateTime", "createTime", "CreatedAt", "createdAt"]),
    }))
    .filter((item) => item.id);
  return {
    items,
    total: firstNumber(result, ["TotalCount", "totalCount", "Total", "total"]) ?? items.length,
    pageNumber,
    pageSize,
  };
}

export function normalizeAssets(
  response: unknown,
  groupId: string,
  pageNumber: number,
  pageSize: number,
): PageResult<Asset> {
  const result = resultRecord(response);
  const items = resultItems(response, ["Assets", "assets", "AssetList", "assetList"])
    .map((item): Asset => ({
      id: firstString(item, ["Id", "id", "AssetId", "assetId"]),
      groupId: firstString(item, ["GroupId", "groupId", "AssetGroupId", "assetGroupId"], groupId),
      name: firstString(item, ["Name", "name", "AssetName", "assetName"], "未命名素材"),
      status: firstString(item, ["Status", "status", "AssetStatus", "assetStatus"], "Unknown"),
      assetType: normalizeAssetType(firstString(item, ["AssetType", "assetType", "Type", "type"], "Image")),
      previewUrl: firstString(item, ["URL", "Url", "url", "PreviewUrl", "previewUrl", "ImageUrl", "imageUrl", "CoverUrl", "coverUrl"]),
      createdAt: firstString(item, ["CreateTime", "createTime", "CreatedAt", "createdAt"]),
    }))
    .filter((item) => item.id);
  return {
    items,
    total: firstNumber(result, ["TotalCount", "totalCount", "Total", "total"]) ?? items.length,
    pageNumber,
    pageSize,
  };
}

export async function listAssetGroups(
  apiKey: string,
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const { pageNumber, pageSize, path } = assetGroupsListPath(options);
  const response = await apiRead<unknown>(path, apiKey);
  const result = normalizeAssetGroups(response, pageNumber, pageSize);
  writeBrowserCache(browserCacheKey(apiKey, "groups", path), result);
  return result;
}

export function readCachedAssetGroups(
  apiKey: string,
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const { path } = assetGroupsListPath(options);
  return readBrowserCache<PageResult<AssetGroup>>(browserCacheKey(apiKey, "groups", path));
}

export async function createAssetGroup(apiKey: string, name: string, description = "") {
  const result = await apiRequest<unknown>("/api/asset-group/create", apiKey, {
    method: "POST",
    body: JSON.stringify({ name: name.trim(), description: description.trim() }),
  });
  invalidateBrowserCache(apiKey, "groups");
  const record = resultRecord(result);
  const nestedGroup = firstValue(record, ["AssetGroup", "assetGroup", "Group", "group"]);
  const source = isRecord(nestedGroup) ? nestedGroup : record;
  return firstString(source, ["Id", "id", "GroupId", "groupId", "AssetGroupId", "assetGroupId"]);
}

export async function updateAssetGroup(apiKey: string, groupId: string, name: string, description: string) {
  const result = await apiRequest<unknown>("/api/asset-group/update", apiKey, {
    method: "PUT",
    body: JSON.stringify({ groupId, name: name.trim(), description: description.trim() }),
  });
  invalidateBrowserCache(apiKey, "groups");
  return result;
}

export async function deleteAssetGroup(apiKey: string, groupId: string) {
  const result = await apiRequest<unknown>(`/api/asset-group/delete?${queryString({ groupId })}`, apiKey, { method: "DELETE" });
  invalidateBrowserCache(apiKey);
  return result;
}

export async function listAssets(
  apiKey: string,
  groupId: string,
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const { pageNumber, pageSize, path } = assetsListPath(groupId, options);
  const response = await apiRead<unknown>(path, apiKey);
  const result = normalizeAssets(response, groupId, pageNumber, pageSize);
  writeBrowserCache(browserCacheKey(apiKey, "assets", path), result);
  return result;
}

export function readCachedAssets(
  apiKey: string,
  groupId: string,
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const { path } = assetsListPath(groupId, options);
  return readBrowserCache<PageResult<Asset>>(browserCacheKey(apiKey, "assets", path));
}

export function uploadAssetFile(file: File, apiKey: string) {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<UploadResult>("/api/asset/upload-file", apiKey, { method: "POST", body: form });
}

export async function createAsset(apiKey: string, groupId: string, upload: UploadResult, name?: string) {
  const result = await apiRequest<unknown>("/api/asset/create", apiKey, {
    method: "POST",
    body: JSON.stringify({
      groupId,
      url: upload.url,
      uploadId: upload.uploadId || undefined,
      assetType: upload.assetType || "Image",
      name: name?.trim() || undefined,
    }),
  });
  invalidateBrowserCache(apiKey, "assets");
  return result;
}

export async function updateAsset(apiKey: string, assetId: string, name: string) {
  const result = await apiRequest<unknown>("/api/asset/update", apiKey, {
    method: "PUT",
    body: JSON.stringify({ assetId, name: name.trim() }),
  });
  invalidateBrowserCache(apiKey, "assets");
  return result;
}

export async function deleteAsset(apiKey: string, assetId: string) {
  const result = await apiRequest<unknown>(`/api/asset/delete?${queryString({ assetId })}`, apiKey, { method: "DELETE" });
  invalidateBrowserCache(apiKey, "assets");
  return result;
}

export function isAssetActive(asset: Asset) {
  return asset.status.toLowerCase() === "active";
}

export function assetUri(assetId: string) {
  return `asset://${assetId}`;
}

export function generateVideo(payload: VideoGeneratePayload, apiKey: string) {
  return apiRequest<VideoTask>("/api/video/generate", apiKey, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getVideoTask(taskId: string, apiKey: string, signal?: AbortSignal) {
  return apiRequest<VideoTask>(`/api/video/task/${encodeURIComponent(taskId)}`, apiKey, { signal });
}

export function getVideoHistory(apiKey: string, limit = 100) {
  return apiRequest<{ tasks: VideoHistoryRecord[] }>(`/api/video/history?limit=${limit}`, apiKey);
}

export function importVideoHistory(tasks: VideoHistoryRecord[], apiKey: string) {
  return apiRequest<{ imported: number }>("/api/video/history/import", apiKey, {
    method: "POST",
    body: JSON.stringify({ tasks }),
  });
}

export function removeVideoHistoryTask(taskId: string, apiKey: string) {
  return apiRequest<{ removed: boolean }>(`/api/video/history/${encodeURIComponent(taskId)}`, apiKey, { method: "DELETE" });
}

export function clearVideoHistory(apiKey: string) {
  return apiRequest<{ removed: number }>("/api/video/history", apiKey, { method: "DELETE" });
}

export function getVideoUsage(apiKey: string, days = 14) {
  return apiRequest<UsageStats>(`/api/video/usage?days=${days}`, apiKey);
}

export function getArkVideoUsage(
  apiKey: string,
  arkApiKey: string,
  start: string,
  end: string,
  interval: "Day" | "Hour" = "Day",
) {
  const parameters = new URLSearchParams({ start, end, interval });
  return apiRequest<ArkUsageStats>(`/api/video/ark-usage?${parameters.toString()}`, apiKey, {
    headers: { "X-Ark-Api-Key": arkApiKey.trim() },
  });
}

export function cancelVideoTask(taskId: string, apiKey: string) {
  return apiRequest<void>(`/api/video/task/${encodeURIComponent(taskId)}/cancel`, apiKey, { method: "POST" });
}

export function getVideoUrl(task: VideoTask | null) {
  return task?.content?.video_url || task?.output?.video_url || task?.video_url || "";
}

export function getLastFrameUrl(task: VideoTask | null) {
  return task?.content?.last_frame_url || task?.output?.last_frame_url || task?.last_frame_url || "";
}
