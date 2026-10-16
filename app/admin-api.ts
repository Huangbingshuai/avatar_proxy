export type AdminUser = {
  id: string;
  username: string;
  displayName: string;
  role: "super_admin" | "admin";
  status: "active" | "disabled";
  mustChangePassword: boolean;
  totpEnabled?: boolean;
  mfaSetupRequired?: boolean;
  mfaVerified?: boolean;
  createdAt: string;
  createdBy?: string | null;
  lastLoginAt?: string | null;
  lastLoginIp?: string | null;
};

export type AdminSession = {
  id: string;
  current: boolean;
  createdAt: number;
  lastSeenAt: number;
  absoluteExpiresAt: number;
  sourceIp?: string | null;
  userAgent?: string | null;
};

export type AdminApi = (path: string, init?: RequestInit) => Promise<Record<string, unknown>>;

export class AdminApiError extends Error {
  status: number;
  code: string;
  retryAfter?: number;
  requestId?: string;

  constructor(message: string, status: number, code = "request_failed", retryAfter?: number, requestId?: string) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
    this.requestId = requestId;
  }
}

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function responseError(data: unknown, fallback: string) {
  if (!data || typeof data !== "object") return { message: fallback, code: "request_failed" };
  const value = data as { error?: { message?: unknown; code?: unknown }; detail?: unknown; message?: unknown; code?: unknown };
  const text = (value: unknown) => typeof value === "string" && value ? value : undefined;
  const fields: Record<string, string> = { projectName: "客户项目", name: "渠道名称", secret: "供应商 API Key", currentPassword: "当前管理员密码", totpCode: "TOTP 动态验证码", provider: "供应商", config: "供应商配置" };
  // FastAPI's validation detail can contain the submitted password/Key in input.
  // Only use known field names, never stringify detail or its input/context.
  const invalidFields = Array.isArray(value.detail) ? [...new Set(value.detail.flatMap((item) => {
    const location = item && typeof item === "object" ? item.loc : undefined;
    return Array.isArray(location) && typeof location[1] === "string" && Object.hasOwn(fields, location[1]) ? [fields[location[1]]] : [];
  }))] : [];
  return {
    message: text(value.error?.message) || text(value.detail) || text(value.message) || (Array.isArray(value.detail) ? `请求参数校验失败${invalidFields.length ? `：请检查${invalidFields.join("、")}` : "，请检查填写内容"}` : fallback),
    code: text(value.error?.code) || text(value.code) || (Array.isArray(value.detail) ? "invalid_request_parameter" : "request_failed"),
  };
}

export async function requestAdminApi(path: string, init: RequestInit = {}, csrfToken = "") {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  if (unsafeMethods.has(method) && csrfToken) headers.set("x-csrf-token", csrfToken);

  const response = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const requestId = response.headers.get("x-request-id") || undefined;
  const data = response.status === 204 ? {} : await response.json().catch(() => null);
  if (response.ok && data === null) {
    throw new AdminApiError("服务器返回了无法识别的响应，请刷新列表确认操作结果后再重试", response.status, "invalid_response", undefined, requestId);
  }
  if (!response.ok) {
    const error = responseError(data, `请求失败（${response.status}）`);
    const retryHeader = response.headers.get("retry-after");
    const retryAfter = retryHeader && /^\d+$/.test(retryHeader) ? Number(retryHeader) : undefined;
    throw new AdminApiError(error.message, response.status, error.code, retryAfter, requestId);
  }
  return data as Record<string, unknown>;
}

export async function refreshAdminCsrf(expectedUser: AdminUser | null) {
  if (!expectedUser) throw new AdminApiError("请重新登录", 401, "invalid_admin_session");
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 5_000);
  let data: Record<string, unknown>;
  try {
    data = await requestAdminApi("/api/internal/auth/me", { signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
  const user = data.user as AdminUser | undefined;
  if (!user || user.id !== expectedUser.id || user.role !== expectedUser.role || user.mustChangePassword ||
      (user.role === "super_admin" && !user.mfaVerified) || typeof data.csrfToken !== "string" || !data.csrfToken) {
    throw new AdminApiError("登录身份或安全状态已变化，请重新登录", 401, "invalid_admin_session");
  }
  return data.csrfToken;
}

export function isSessionError(error: unknown) {
  return error instanceof AdminApiError && error.status === 401 && new Set([
    "admin_session_required",
    "invalid_admin_session",
    "admin_session_expired",
    "admin_user_disabled",
  ]).has(error.code);
}

export function isPasswordChangeRequired(error: unknown) {
  return error instanceof AdminApiError && error.status === 403 && error.code === "password_change_required";
}
