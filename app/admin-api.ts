export type AdminUser = {
  id: string;
  username: string;
  displayName: string;
  role: "super_admin" | "admin";
  status: "active" | "disabled";
  mustChangePassword: boolean;
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

  constructor(message: string, status: number, code = "request_failed", retryAfter?: number) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function responseError(data: unknown, fallback: string) {
  if (!data || typeof data !== "object") return { message: fallback, code: "request_failed" };
  const value = data as { error?: { message?: string; code?: string }; detail?: string; message?: string; code?: string };
  return {
    message: value.error?.message || value.detail || value.message || fallback,
    code: value.error?.code || value.code || "request_failed",
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
  const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = responseError(data, `请求失败（${response.status}）`);
    const retryHeader = response.headers.get("retry-after");
    const retryAfter = retryHeader && /^\d+$/.test(retryHeader) ? Number(retryHeader) : undefined;
    throw new AdminApiError(error.message, response.status, error.code, retryAfter);
  }
  return data as Record<string, unknown>;
}

export function isSessionError(error: unknown) {
  return error instanceof AdminApiError && error.status === 401;
}

export function isPasswordChangeRequired(error: unknown) {
  return error instanceof AdminApiError && error.status === 403 && error.code === "password_change_required";
}
