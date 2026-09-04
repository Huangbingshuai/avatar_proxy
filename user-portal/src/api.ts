export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const DEFAULT_MODEL = "doubao-seedance-2.0";

export type VideoModelOption = {
  id: string;
  label: string;
};

const DEFAULT_VIDEO_MODELS: VideoModelOption[] = [
  { id: "doubao-seedance-2.5", label: "Doubao-Seedance-2.5" },
  { id: "doubao-seedance-2.0", label: "Doubao-Seedance-2.0" },
  { id: "doubao-seedance-2.0-fast", label: "Doubao-Seedance-2.0-Fast" },
  { id: "doubao-seedance-2.0-mini", label: "Doubao-Seedance-2.0-Mini" },
  { id: "doubao-seedance-1.0-pro", label: "Doubao-Seedance-1.0-Pro" },
  { id: "doubao-seedance-1.0-pro-fast", label: "Doubao-Seedance-1.0-Pro-Fast" },
];

const RETIRED_VIDEO_MODELS = new Set([
  "doubao-seedance-1.5-pro",
  "doubao-seedance-1-5-pro-251215",
]);

function readVideoModels(): VideoModelOption[] {
  const configured = String(import.meta.env.VITE_VIDEO_MODELS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .flatMap((item) => {
      const [id, label] = item.split("|").map((part) => part.trim());
      return id && !RETIRED_VIDEO_MODELS.has(id)
        ? [{ id, label: label || id }]
        : [];
    });
  const models = new Map(
    DEFAULT_VIDEO_MODELS.map((model) => [model.id, model]),
  );
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

export type ApiSession = {
  authenticated: true;
  apiKeyId: string;
};

export type RelayModel = {
  id: string;
  object: "model";
  displayName: string;
  modality: "text" | "image" | "video" | "embedding" | "audio";
  capabilities: Record<string, unknown>;
};

export type RelayApiResult = {
  body: Record<string, unknown>;
  status: number;
  requestId?: string;
};

export type RelayTextStreamOptions = {
  signal?: AbortSignal;
  image?: string;
  onDelta?: (delta: string, accumulated: string) => void;
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
    assets: Array<
      Pick<
        Asset,
        "id" | "groupId" | "name" | "status" | "assetType" | "previewUrl"
      >
    >;
    durationMode?: "seconds" | "smart";
    generationCount?: number;
  };
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

function browserCacheKey(
  apiKey: string,
  resource: "groups" | "assets",
  path: string,
) {
  return `${BROWSER_CACHE_PREFIX}:${apiKeyFingerprint(apiKey)}:${resource}:${encodeURIComponent(path)}`;
}

function readBrowserCache<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const entry = JSON.parse(raw) as BrowserCacheEntry<T>;
    if (
      !entry.cachedAt ||
      Date.now() - entry.cachedAt > BROWSER_CACHE_MAX_AGE_MS
    ) {
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

function invalidateBrowserCache(
  apiKey: string,
  resource?: "groups" | "assets",
) {
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
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : fallback;
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
  if (data.ResponseMetadata?.Error?.Message)
    return data.ResponseMetadata.Error.Message;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    const details = data.detail
      .map((item) => item.msg)
      .filter(Boolean)
      .join("；");
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
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");

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

async function relayRequest(
  path: string,
  apiKey: string,
  init: RequestInit = {},
): Promise<RelayApiResult> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiKey.trim()}`);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "omit",
  });
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
  return {
    body: isRecord(data) ? data : {},
    status: response.status,
    requestId: response.headers.get("x-request-id") || undefined,
  };
}

export function authenticateApiKey(apiKey: string) {
  return apiRequest<ApiSession>("/api/auth/me", apiKey);
}

export async function listRelayModels(apiKey: string): Promise<RelayModel[]> {
  const result = await relayRequest("/v1/models", apiKey);
  const models = Array.isArray(result.body.data) ? result.body.data : [];
  return models.filter(isRecord).flatMap((item) => {
    const id = firstString(item, ["id"]);
    const modality = firstString(item, ["modality"]);
    if (
      !id ||
      !new Set(["text", "image", "video", "embedding", "audio"]).has(modality)
    )
      return [];
    return [
      {
        id,
        object: "model" as const,
        displayName: firstString(item, ["display_name", "displayName"], id),
        modality: modality as RelayModel["modality"],
        capabilities: isRecord(item.capabilities) ? item.capabilities : {},
      },
    ];
  });
}

export function testRelayText(apiKey: string, model: string, prompt: string) {
  return relayRequest("/v1/chat/completions", apiKey, {
    method: "POST",
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: prompt }],
      stream: false,
      max_tokens: 512,
    }),
  });
}

export function testRelayTranslation(
  apiKey: string,
  model: string,
  text: string,
  targetLanguage: string,
  sourceLanguage?: string,
) {
  return relayRequest("/v1/responses", apiKey, {
    method: "POST",
    body: JSON.stringify({
      model,
      input: [
        {
          role: "user",
          content: [
            {
              type: "input_text",
              text,
              translation_options: {
                ...(sourceLanguage ? { source_language: sourceLanguage } : {}),
                target_language: targetLanguage,
              },
            },
          ],
        },
      ],
      stream: false,
    }),
  });
}

function streamTextValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return "";
  return value
    .flatMap((item) => {
      if (typeof item === "string") return [item];
      if (!isRecord(item)) return [];
      const text = firstString(item, ["text", "content"]);
      return text ? [text] : [];
    })
    .join("");
}

function chatStreamDelta(event: UnknownRecord): string {
  const choice =
    Array.isArray(event.choices) && isRecord(event.choices[0])
      ? event.choices[0]
      : {};
  const delta = isRecord(choice.delta) ? choice.delta : {};
  return (
    streamTextValue(delta.content) || streamTextValue(delta.reasoning_content)
  );
}

export async function testRelayTextStream(
  apiKey: string,
  model: string,
  prompt: string,
  options: RelayTextStreamOptions = {},
): Promise<RelayApiResult> {
  const content = options.image
    ? [
        { type: "image_url", image_url: { url: options.image } },
        { type: "text", text: prompt },
      ]
    : prompt;
  const response = await fetch(`${API_BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey.trim()}`,
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    credentials: "omit",
    signal: options.signal,
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content }],
      stream: true,
      stream_options: { include_usage: true },
      max_tokens: 512,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    let data: unknown = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { message: text };
      }
    }
    throw new Error(errorMessage(data, response.status));
  }
  if (!response.body) throw new Error("浏览器未收到可读取的流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let accumulated = "";
  let usage: Record<string, unknown> = {};
  let requestId = response.headers.get("x-request-id") || undefined;

  function consumeLine(rawLine: string) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (!line.startsWith("data:")) return;
    const payload = line.slice(5).trimStart();
    if (!payload || payload === "[DONE]") return;
    let event: unknown;
    try {
      event = JSON.parse(payload);
    } catch {
      return;
    }
    if (!isRecord(event)) return;
    if (!requestId) requestId = firstString(event, ["id"]) || undefined;
    if (isRecord(event.usage)) usage = event.usage;
    const delta = chatStreamDelta(event);
    if (!delta) return;
    accumulated += delta;
    options.onDelta?.(delta, accumulated);
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) consumeLine(line);
    if (done) break;
  }
  if (buffer) consumeLine(buffer);

  return {
    status: response.status,
    requestId,
    body: {
      id: requestId,
      object: "chat.completion",
      model,
      choices: [
        {
          index: 0,
          message: { role: "assistant", content: accumulated },
          finish_reason: "stop",
        },
      ],
      ...(Object.keys(usage).length ? { usage } : {}),
    },
  };
}

export function testRelayImage(
  apiKey: string,
  model: string,
  prompt: string,
  idempotencyKey: string,
  image?: string,
) {
  return relayRequest("/v1/images/generations", apiKey, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      model,
      prompt,
      n: 1,
      response_format: "url",
      ...(image ? { image } : {}),
    }),
  });
}

export function testRelayEmbedding(
  apiKey: string,
  model: string,
  input: string,
) {
  return relayRequest("/v1/embeddings", apiKey, {
    method: "POST",
    body: JSON.stringify({ model, input, encoding_format: "float" }),
  });
}

export async function testRelaySpeech(
  apiKey: string,
  model: string,
  input: string,
  voice: string,
): Promise<RelayApiResult> {
  const response = await fetch(`${API_BASE_URL}/v1/audio/speech`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey.trim()}`,
      "Content-Type": "application/json",
    },
    credentials: "omit",
    body: JSON.stringify({ model, input, voice, response_format: "mp3" }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(errorMessage(body, response.status));
  }
  const audioUrl = URL.createObjectURL(await response.blob());
  return {
    status: response.status,
    requestId: response.headers.get("x-request-id") || undefined,
    body: { model, audio_url: audioUrl },
  };
}

export function testRelayTranscription(
  apiKey: string,
  model: string,
  url: string,
  idempotencyKey: string,
) {
  return relayRequest("/v1/audio/transcriptions", apiKey, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ model, url }),
  });
}

export function getRelayTranscription(apiKey: string, taskId: string) {
  return relayRequest(
    `/v1/audio/transcriptions/${encodeURIComponent(taskId)}`,
    apiKey,
  );
}

export function testRelayAudioGeneration(
  apiKey: string,
  model: string,
  prompt: string,
) {
  return relayRequest("/v1/audio/generations", apiKey, {
    method: "POST",
    body: JSON.stringify({ model, prompt, format: "mp3" }),
  });
}

export function testRelayVideo(
  apiKey: string,
  payload: { model: string; prompt: string; image?: string; duration?: number },
  idempotencyKey: string,
) {
  const content: Array<Record<string, unknown>> = [
    { type: "text", text: payload.prompt },
  ];
  if (payload.image) {
    content.push({
      type: "image_url",
      image_url: { url: payload.image },
      role: "first_frame",
    });
  }
  return relayRequest("/api/v3/contents/generations/tasks", apiKey, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      model: payload.model,
      content,
      ...(payload.duration != null ? { duration: payload.duration } : {}),
    }),
  });
}

export function getRelayVideoTask(apiKey: string, taskId: string) {
  return relayRequest(
    `/api/v3/contents/generations/tasks/${encodeURIComponent(taskId)}`,
    apiKey,
  );
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

function assetGroupsListPath(
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const pageNumber = options.pageNumber ?? 1;
  const pageSize = options.pageSize ?? 20;
  const query = queryString({
    pageNumber,
    pageSize,
    name: options.name?.trim(),
  });
  return { pageNumber, pageSize, path: `/api/asset-group/list?${query}` };
}

function assetsListPath(
  groupId: string,
  options: { pageNumber?: number; pageSize?: number; name?: string } = {},
) {
  const pageNumber = options.pageNumber ?? 1;
  const pageSize = options.pageSize ?? 20;
  const query = queryString({
    groupId,
    pageNumber,
    pageSize,
    name: options.name?.trim(),
  });
  return { pageNumber, pageSize, path: `/api/asset/list?${query}` };
}

export function normalizeAssetGroups(
  response: unknown,
  pageNumber: number,
  pageSize: number,
): PageResult<AssetGroup> {
  const result = resultRecord(response);
  const items = resultItems(response, [
    "AssetGroups",
    "assetGroups",
    "Groups",
    "groups",
  ])
    .map((item): AssetGroup => ({
      id: firstString(item, [
        "Id",
        "id",
        "GroupId",
        "groupId",
        "AssetGroupId",
        "assetGroupId",
      ]),
      name: firstString(
        item,
        ["Name", "name", "GroupName", "groupName"],
        "未命名素材库",
      ),
      description: firstString(item, ["Description", "description"]),
      assetCount: firstNumber(item, [
        "AssetCount",
        "assetCount",
        "TotalAssetCount",
        "totalAssetCount",
      ]),
      createdAt: firstString(item, [
        "CreateTime",
        "createTime",
        "CreatedAt",
        "createdAt",
      ]),
    }))
    .filter((item) => item.id);
  return {
    items,
    total:
      firstNumber(result, ["TotalCount", "totalCount", "Total", "total"]) ??
      items.length,
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
  const items = resultItems(response, [
    "Assets",
    "assets",
    "AssetList",
    "assetList",
  ])
    .map((item): Asset => ({
      id: firstString(item, ["Id", "id", "AssetId", "assetId"]),
      groupId: firstString(
        item,
        ["GroupId", "groupId", "AssetGroupId", "assetGroupId"],
        groupId,
      ),
      name: firstString(
        item,
        ["Name", "name", "AssetName", "assetName"],
        "未命名素材",
      ),
      status: firstString(
        item,
        ["Status", "status", "AssetStatus", "assetStatus"],
        "Unknown",
      ),
      assetType: normalizeAssetType(
        firstString(item, ["AssetType", "assetType", "Type", "type"], "Image"),
      ),
      previewUrl: firstString(item, [
        "URL",
        "Url",
        "url",
        "PreviewUrl",
        "previewUrl",
        "ImageUrl",
        "imageUrl",
        "CoverUrl",
        "coverUrl",
      ]),
      createdAt: firstString(item, [
        "CreateTime",
        "createTime",
        "CreatedAt",
        "createdAt",
      ]),
    }))
    .filter((item) => item.id);
  return {
    items,
    total:
      firstNumber(result, ["TotalCount", "totalCount", "Total", "total"]) ??
      items.length,
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
  return readBrowserCache<PageResult<AssetGroup>>(
    browserCacheKey(apiKey, "groups", path),
  );
}

export async function createAssetGroup(
  apiKey: string,
  name: string,
  description = "",
) {
  const result = await apiRequest<unknown>("/api/asset-group/create", apiKey, {
    method: "POST",
    body: JSON.stringify({
      name: name.trim(),
      description: description.trim(),
    }),
  });
  invalidateBrowserCache(apiKey, "groups");
  const record = resultRecord(result);
  const nestedGroup = firstValue(record, [
    "AssetGroup",
    "assetGroup",
    "Group",
    "group",
  ]);
  const source = isRecord(nestedGroup) ? nestedGroup : record;
  return firstString(source, [
    "Id",
    "id",
    "GroupId",
    "groupId",
    "AssetGroupId",
    "assetGroupId",
  ]);
}

export async function updateAssetGroup(
  apiKey: string,
  groupId: string,
  name: string,
  description: string,
) {
  const result = await apiRequest<unknown>("/api/asset-group/update", apiKey, {
    method: "PUT",
    body: JSON.stringify({
      groupId,
      name: name.trim(),
      description: description.trim(),
    }),
  });
  invalidateBrowserCache(apiKey, "groups");
  return result;
}

export async function deleteAssetGroup(apiKey: string, groupId: string) {
  const result = await apiRequest<unknown>(
    `/api/asset-group/delete?${queryString({ groupId })}`,
    apiKey,
    { method: "DELETE" },
  );
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
  return readBrowserCache<PageResult<Asset>>(
    browserCacheKey(apiKey, "assets", path),
  );
}

export function uploadAssetFile(file: File, apiKey: string) {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<UploadResult>("/api/asset/upload-file", apiKey, {
    method: "POST",
    body: form,
  });
}

export async function createAsset(
  apiKey: string,
  groupId: string,
  upload: UploadResult,
  name?: string,
) {
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

export async function updateAsset(
  apiKey: string,
  assetId: string,
  name: string,
) {
  const result = await apiRequest<unknown>("/api/asset/update", apiKey, {
    method: "PUT",
    body: JSON.stringify({ assetId, name: name.trim() }),
  });
  invalidateBrowserCache(apiKey, "assets");
  return result;
}

export async function deleteAsset(apiKey: string, assetId: string) {
  const result = await apiRequest<unknown>(
    `/api/asset/delete?${queryString({ assetId })}`,
    apiKey,
    { method: "DELETE" },
  );
  invalidateBrowserCache(apiKey, "assets");
  return result;
}

export function isAssetActive(asset: Asset) {
  return asset.status.toLowerCase() === "active";
}

export function assetUri(assetId: string) {
  return `asset://${assetId}`;
}

export type ReferenceAsset = Pick<Asset, "id" | "assetType">;

export function assetTypeOf(
  asset: Partial<Pick<Asset, "assetType">> | AssetType,
): AssetType {
  const value = typeof asset === "string" ? asset : asset.assetType;
  return value === "Video" || value === "Audio" ? value : "Image";
}

export function assetTypeLabel(
  asset: Partial<Pick<Asset, "assetType">> | AssetType,
) {
  const assetType = assetTypeOf(asset);
  if (assetType === "Video") return "视频";
  if (assetType === "Audio") return "音频";
  return "图片";
}

export function assetReferenceLabel(
  asset: ReferenceAsset,
  selectedAssets: ReferenceAsset[],
) {
  const assetType = assetTypeOf(asset);
  const sameTypeIndex = selectedAssets
    .filter((candidate) => assetTypeOf(candidate) === assetType)
    .findIndex((candidate) => candidate.id === asset.id);
  return `${assetTypeLabel(asset)}${Math.max(0, sameTypeIndex) + 1}`;
}

export function assetContentItem(
  asset: ReferenceAsset,
): Record<string, unknown> {
  const url = assetUri(asset.id);
  const assetType = assetTypeOf(asset);
  if (assetType === "Video") {
    return { type: "video_url", video_url: { url }, role: "reference_video" };
  }
  if (assetType === "Audio") {
    return { type: "audio_url", audio_url: { url }, role: "reference_audio" };
  }
  return { type: "image_url", image_url: { url }, role: "reference_image" };
}

export function generateVideo(payload: VideoGeneratePayload, apiKey: string) {
  const {
    metadata: _localMetadata,
    generateAudio,
    returnLastFrame,
    ...nativePayload
  } = payload;
  void _localMetadata;
  return apiRequest<VideoTask>("/api/v3/contents/generations/tasks", apiKey, {
    method: "POST",
    body: JSON.stringify({
      ...nativePayload,
      generate_audio: generateAudio,
      return_last_frame: returnLastFrame,
    }),
  });
}

export function getVideoTask(
  taskId: string,
  apiKey: string,
  signal?: AbortSignal,
) {
  return apiRequest<VideoTask>(
    `/api/v3/contents/generations/tasks/${encodeURIComponent(taskId)}`,
    apiKey,
    { signal },
  );
}

export function cancelVideoTask(taskId: string, apiKey: string) {
  return apiRequest<void>(
    `/api/v3/contents/generations/tasks/${encodeURIComponent(taskId)}`,
    apiKey,
    { method: "DELETE" },
  );
}

export function getVideoUrl(task: VideoTask | null) {
  return (
    task?.content?.video_url || task?.output?.video_url || task?.video_url || ""
  );
}

export function getLastFrameUrl(task: VideoTask | null) {
  return (
    task?.content?.last_frame_url ||
    task?.output?.last_frame_url ||
    task?.last_frame_url ||
    ""
  );
}
