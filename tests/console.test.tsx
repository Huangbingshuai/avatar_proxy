import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConsolePage from "../app/page";

type MockData = {
  projects?: Array<Record<string, unknown>>;
  apiKeys?: Array<Record<string, unknown>>;
  events?: Array<Record<string, unknown>>;
  audits?: Array<Record<string, unknown>>;
  projectCreateError?: string;
  loginError?: { message: string; code: string; status: number; retryAfter?: number };
  mustChangePassword?: boolean;
  role?: "super_admin" | "admin";
  totpRequired?: boolean;
  mfaSetupRequired?: boolean;
  expireOnPath?: string;
  backupCreatedAt?: string | null;
  monitorPercent?: number;
};

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

function installFetch(data: MockData = {}) {
  const projects = data.projects ?? [
    { name: "customer_a", displayName: "客户 A", description: "", keyCount: 1, activeKeyCount: 1, activeAssetCount: 0 },
    { name: "customer_b", displayName: "客户 B", description: "", keyCount: 1, activeKeyCount: 1, activeAssetCount: 0 },
  ];
  const apiKeys = data.apiKeys ?? [
    { id: "key-a", name: "生产 Key", keyPrefix: "vap_live_a…", projectName: "customer_a", status: "active", createdAt: "2026-08-13 00:00:00" },
    { id: "key-b", name: "批处理 Key", keyPrefix: "vap_live_b…", projectName: "customer_b", status: "active", createdAt: "2026-08-13 00:00:00" },
  ];
  const events = data.events ?? [{ id: 7, projectName: "customer_a", scopeType: "project", metric: "read_qpm", threshold: 90, limitValue: 100, usedValue: 90, acknowledged: false, createdAt: "2026-08-13 00:00:00" }];
  const audits = data.audits ?? [{ id: 8, sourceIp: "10.0.0.8", action: "quota.project.update", targetType: "project", targetId: "customer_a", createdAt: "2026-08-13 00:00:00" }];
  const currentUser = { id: "admin-1", username: "owner", displayName: "系统管理员", role: data.role ?? "admin", status: "active", mustChangePassword: Boolean(data.mustChangePassword), totpEnabled: data.role === "super_admin" && !data.mfaSetupRequired, mfaSetupRequired: Boolean(data.mfaSetupRequired), mfaVerified: data.role !== "super_admin" || !data.mfaSetupRequired, createdAt: "2026-08-10 00:00:00", lastLoginAt: "2026-08-19 08:00:00", lastLoginIp: "127.0.0.1" };
  let users = [currentUser, { id: "admin-2", username: "operator", displayName: "运营管理员", role: "admin", status: "active", mustChangePassword: false, createdAt: "2026-08-11 00:00:00", lastLoginAt: "2026-08-18 08:00:00", lastLoginIp: "10.0.0.8" }];
  const sessions = [
    { id: "session-current", current: true, createdAt: 1787107200, lastSeenAt: 1787107800, absoluteExpiresAt: 1787150400, sourceIp: "127.0.0.1", userAgent: "Windows Chrome" },
    { id: "session-old", current: false, createdAt: 1787020800, lastSeenAt: 1787024400, absoluteExpiresAt: 1787110800, sourceIp: "10.0.0.8", userAgent: "Macintosh Safari" },
  ];
  const backupItem = { id: "20260819-080000-000001", databaseFile: "avatar_proxy-20260819-080000-000001.db", auditFile: "admin_audit-20260819-080000-000001.jsonl", databaseBytes: 2048, auditBytes: 1024, createdAt: data.backupCreatedAt ?? "2026-08-19T08:00:00Z", valid: true, counts: { projects: 2, apiKeys: 2, adminUsers: 2, adminAudits: 19 } };
  const monitorSettings = { enabled: true, configuredEnabled: true, runtimeEnabled: true, path: "C:\\data", warningPercent: 80, criticalPercent: 90, emergencyPercent: 95, recoveryPercent: 75, sampleIntervalSeconds: 60, persistIntervalSeconds: 300, retentionDays: 30, emailConfigured: true, emailRecipientCount: 2 };
  const monitorSample = { path: "C:\\data", totalBytes: 160 * 1024 ** 3, usedBytes: 109.4 * 1024 ** 3, availableBytes: 50.6 * 1024 ** 3, reservedBytes: 0, usedPercent: data.monitorPercent ?? 68.4, level: "normal", sampledAt: 1_787_107_800 };
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  let authenticated = false;
  let passwordChanged = !data.mustChangePassword;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const path = `${url.pathname}${url.search}`;
    calls.push({ path, init });
    if (url.pathname === "/api/internal/auth/login") {
      if (data.loginError) return jsonResponse({ error: { message: data.loginError.message, code: data.loginError.code } }, data.loginError.status, data.loginError.retryAfter ? { "retry-after": String(data.loginError.retryAfter) } : {});
      const body = JSON.parse(String(init?.body));
      if (body.username !== "owner" || body.password !== "correct-password") return jsonResponse({ error: { message: "用户名或密码错误", code: "invalid_admin_credentials" } }, 401);
      if (data.totpRequired && !body.totpCode && !body.recoveryCode) return jsonResponse({ error: { message: "请输入动态验证码", code: "admin_totp_required" } }, 401);
      authenticated = true;
      return jsonResponse({ user: currentUser, csrfToken: "csrf-test", session: sessions[0] });
    }
    if (url.pathname === "/api/internal/auth/me") {
      if (!authenticated) return jsonResponse({ error: { message: "需要管理员会话", code: "admin_session_required" } }, 401);
      return jsonResponse({ user: { ...currentUser, mustChangePassword: !passwordChanged }, csrfToken: "csrf-test", session: sessions[0] });
    }
    if (!authenticated || data.expireOnPath === url.pathname) return jsonResponse({ error: { message: "管理员会话已过期", code: "admin_session_expired" } }, 401);
    if (url.pathname === "/api/internal/auth/change-password") {
      if (new Headers(init?.headers).get("x-csrf-token") !== "csrf-test") return jsonResponse({ error: { message: "CSRF 校验失败", code: "invalid_csrf_token" } }, 403);
      passwordChanged = true;
      return jsonResponse({ user: { ...currentUser, mustChangePassword: false }, csrfToken: "csrf-test" });
    }
    if (url.pathname === "/api/internal/auth/totp/setup") return jsonResponse({ secret: "JBSWY3DPEHPK3PXP", qrCodeDataUrl: "data:image/png;base64,AAAA" });
    if (url.pathname === "/api/internal/auth/totp/confirm") return jsonResponse({ enabled: true, mfaVerified: true, recoveryCodes: ["AAAA-BBBB-CCCC-DDDD", "EEEE-FFFF-GGGG-HHHH"] });
    if (url.pathname === "/api/internal/auth/totp/rotate/setup") return jsonResponse({ secret: "NEWSECRETFORROTATION", qrCodeDataUrl: "data:image/png;base64,BBBB", expiresAt: 1_800_000_600 });
    if (url.pathname === "/api/internal/auth/totp/rotate/confirm") return jsonResponse({ enabled: true, mfaVerified: true, recoveryCodes: ["NEW1-AAAA-BBBB-CCCC", "NEW2-DDDD-EEEE-FFFF"], otherSessionsRevoked: 1 });
    if (!passwordChanged) return jsonResponse({ error: { message: "请先修改初始密码", code: "password_change_required" } }, 403);
    if (url.pathname === "/api/internal/auth/logout") { authenticated = false; return jsonResponse({ loggedOut: true }); }
    if (url.pathname === "/api/internal/admin/users") {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return jsonResponse({ user: { ...users[1], id: "admin-3", username: body.username, displayName: body.displayName }, initialPassword: "Temp-Password-123!" }, 201);
      }
      return jsonResponse({ users });
    }
    if (url.pathname === "/api/internal/admin/audits") return jsonResponse({ audits: [{ id: 19, actor: "owner", sourceIp: "10.0.0.8", userAgent: "Windows Chrome", action: "admin.auth.login", targetType: "admin_user", targetId: "admin-1", outcome: "success", createdAt: "2026-08-19 08:00:00" }] });
    if (url.pathname === "/api/internal/admin/security-alerts") return jsonResponse({ alerts: [{ id: 21, eventType: "super_admin_login", severity: "critical", message: "超级管理员账号已登录", actor: "owner", sourceIp: "127.0.0.1", targetType: "admin_session", targetId: "session-current", acknowledgedAt: null, createdAt: "2026-08-19 08:00:00" }] });
    if (url.pathname === "/api/internal/admin/security-alerts/ack") return jsonResponse({ alert: { id: 21, acknowledged_at: "2026-08-19 08:05:00" } });
    if (url.pathname === "/api/internal/admin/backups/status") return jsonResponse({ enabled: true, intervalSeconds: 86400, retention: 30, directory: "data/backups", lastRun: { status: "success", completedAt: "2026-08-19 08:00:00", databaseBytes: 2048, auditBytes: 1024 } });
    if (url.pathname === "/api/internal/admin/backups") return jsonResponse({ backups: [backupItem], lastRestore: null });
    if (url.pathname === "/api/internal/admin/backups/run") return jsonResponse({ enabled: true, intervalSeconds: 86400, retention: 30, directory: "data/backups", lastRun: { status: "success", completedAt: "2026-08-19 08:10:00", databaseBytes: 2048, auditBytes: 1024 } });
    if (url.pathname === "/api/internal/admin/system-monitor/status") return jsonResponse({ health: "ok", sample: monitorSample, activeIncidentId: null, recoveryStreak: 0, probeFailureStreak: 0, probeAlertActive: false, lastSampledAt: monitorSample.sampledAt, lastError: null, pendingEmailDeliveries: 0, settings: monitorSettings });
    if (url.pathname === "/api/internal/admin/system-monitor/settings" && init?.method === "PUT") { const body = JSON.parse(String(init.body)); return jsonResponse({ settings: { ...monitorSettings, ...body, currentPassword: undefined } }); }
    if (/\/api\/internal\/admin\/backups\/[^/]+\/validate$/.test(url.pathname)) return jsonResponse({ backup: { ...backupItem, integrity: "ok", sha256: "abc123" } });
    if (/\/api\/internal\/admin\/backups\/[^/]+\/restore$/.test(url.pathname)) { authenticated = false; return jsonResponse({ restored: true, requiresLogin: true }); }
    if (/\/api\/internal\/admin\/users\/[^/]+\/(enable|disable)$/.test(url.pathname)) {
      const id = url.pathname.split("/").at(-2);
      const status = url.pathname.endsWith("/disable") ? "disabled" : "active";
      users = users.map((item) => item.id === id ? { ...item, status } : item);
      return jsonResponse({ user: users.find((item) => item.id === id) });
    }
    if (/\/api\/internal\/admin\/users\/[^/]+\/reset-password$/.test(url.pathname)) return jsonResponse({ user: users[1], initialPassword: "Reset-Password-456!" });
    if (/\/api\/internal\/admin\/users\/[^/]+$/.test(url.pathname) && init?.method === "DELETE") {
      const id = url.pathname.split("/").at(-1);
      users = users.filter((item) => item.id !== id);
      return jsonResponse({ deleted: true, userId: id, username: "operator" });
    }
    if (url.pathname === "/api/internal/auth/sessions") return jsonResponse({ sessions });
    if (/\/api\/internal\/auth\/sessions\/[^/]+$/.test(url.pathname) && init?.method === "DELETE") return jsonResponse({ revoked: true, sessionId: "session-old" });
    if (url.pathname === "/api/internal/project/list") return jsonResponse({ projects });
    if (url.pathname === "/api/internal/apikey/list") return jsonResponse({ apiKeys });
    if (url.pathname === "/api/internal/overview") return jsonResponse({ stats: { projects: projects.length, activeKeys: apiKeys.length, requests24h: 12, errors24h: 1, assetsToday: 3, uploadsToday: 2, uploadBytesToday: 2048, limitedProjects: 1, openQuotaEvents: events.length, cleanupPending: 1 }, recent: [] });
    if (url.pathname === "/api/internal/quota/events") return jsonResponse({ events });
    if (url.pathname === "/api/internal/quota/audits") return jsonResponse({ audits });
    if (url.pathname === "/api/internal/quota/usage") {
      const projectName = url.searchParams.get("projectName") ?? "customer_a";
      return jsonResponse({ projectName, quota: { projectName, enabled: projectName === "customer_a", readQpm: projectName === "customer_a" ? 100 : null, writeQpm: projectName === "customer_a" ? 20 : null, maxConcurrency: null, dailyAssetCreates: null, dailyUploadFiles: null, dailyUploadBytes: null, totalAssets: 10, totalStorageBytes: 1024 }, usage: { readQpm: 70, writeQpm: 4, totalAssets: 3, totalStorageBytes: 512, cleanupPending: 1 }, cleanupObjects: [{ recordId: "upload-1", objectKey: `avatar-assets/${projectName}/portrait.png`, sizeBytes: 512, status: "cleanup_pending", cleanupAttempts: 2, createdAt: "2026-08-13 00:00:00" }] });
    }
    if (url.pathname === "/api/internal/apikey/quota") return jsonResponse({ quota: { keyId: url.searchParams.get("keyId"), readQpm: 50, writeQpm: null, maxConcurrency: null, dailyAssetCreates: null, dailyUploadFiles: null, dailyUploadBytes: null } });
    if (url.pathname === "/api/internal/project/quota" && init?.method === "PUT") return jsonResponse({ quota: {} });
    if (url.pathname === "/api/internal/apikey/quota" && init?.method === "PUT") return jsonResponse({ quota: {} });
    if (url.pathname === "/api/internal/quota/event/ack") return jsonResponse({ acknowledged: true });
    if (url.pathname === "/api/internal/project/create" && init?.method === "POST") {
      if (data.projectCreateError) return jsonResponse({ error: { message: data.projectCreateError } }, 422);
      return jsonResponse({ project: JSON.parse(String(init.body)) }, 201);
    }
    if (url.pathname === "/api/internal/project/delete" && init?.method === "DELETE") return jsonResponse({ deleted: true });
    return jsonResponse({ error: { message: `未模拟接口 ${url.pathname}` } }, 500);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

async function login() {
  const user = userEvent.setup();
  render(<ConsolePage />);
  await screen.findByRole("heading", { name: "登录内部控制台" });
  await user.type(screen.getByLabelText("用户名"), "owner");
  await user.type(screen.getByLabelText("密码"), "correct-password");
  await user.click(screen.getByRole("button", { name: "登录控制台" }));
  await waitFor(() => expect(screen.queryByRole("heading", { name: "登录内部控制台" })).not.toBeInTheDocument());
  return user;
}

describe("内部控制台", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("使用独立管理员账号登录，并以同源 Session 加载控制台", async () => {
    const { calls } = installFetch();
    await login();
    expect(screen.getByText("INTERNAL CONTROL PLANE")).toBeInTheDocument();
    expect(calls.some((call) => call.path === "/api/internal/auth/me")).toBe(true);
    expect(calls.some((call) => call.path === "/api/internal/auth/login")).toBe(true);
    expect(calls.every((call) => !new Headers(call.init?.headers).has("x-admin-token"))).toBe(true);
    expect(calls.every((call) => call.init?.credentials === "same-origin")).toBe(true);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("登录锁定时展示 Retry-After", async () => {
    installFetch({ loginError: { message: "登录尝试过多，账号已临时锁定", code: "admin_login_locked", status: 429, retryAfter: 300 } });
    const user = userEvent.setup();
    render(<ConsolePage />);
    await screen.findByRole("heading", { name: "登录内部控制台" });
    await user.type(screen.getByLabelText("用户名"), "owner");
    await user.type(screen.getByLabelText("密码"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "登录控制台" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("300 秒后重试");
  });

  it("已禁用管理员输入正确密码时展示账号禁用提示", async () => {
    installFetch({ loginError: { message: "管理员账号已禁用，请联系超级管理员", code: "admin_user_disabled", status: 403 } });
    const user = userEvent.setup();
    render(<ConsolePage />);
    await screen.findByRole("heading", { name: "登录内部控制台" });
    await user.type(screen.getByLabelText("用户名"), "operator");
    await user.type(screen.getByLabelText("密码"), "correct-password");
    await user.click(screen.getByRole("button", { name: "登录控制台" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("账号已禁用");
  });

  it("首次登录必须修改密码，并带 CSRF 完成修改", async () => {
    const { calls } = installFetch({ mustChangePassword: true });
    const user = await login();
    expect(await screen.findByRole("heading", { name: "首次登录，请修改密码" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("当前密码"), "correct-password");
    await user.type(screen.getByLabelText(/^新密码/), "New-password-123!");
    await user.type(screen.getByLabelText("确认新密码"), "New-password-123!");
    await user.click(screen.getByRole("button", { name: "保存新密码" }));
    expect(await screen.findByRole("heading", { name: "登录内部控制台" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("密码已修改");
    const call = calls.find((item) => item.path === "/api/internal/auth/change-password");
    expect(new Headers(call?.init?.headers).get("x-csrf-token")).toBe("csrf-test");
  });

  it("超级管理员登录必须完成TOTP二次验证", async () => {
    const { calls } = installFetch({ role: "super_admin", totpRequired: true });
    const user = await login();
    expect(await screen.findByRole("heading", { name: "超级管理员二次验证" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("动态验证码或恢复码"), "123456");
    await user.click(screen.getByRole("button", { name: "验证并登录" }));
    expect(await screen.findByRole("heading", { name: "超级管理员安全中心" })).toBeInTheDocument();
    const loginCalls = calls.filter((call) => call.path === "/api/internal/auth/login");
    expect(JSON.parse(String(loginCalls.at(-1)?.init?.body))).toMatchObject({ totpCode: "123456" });
    expect(screen.queryByRole("button", { name: "项目" })).not.toBeInTheDocument();
    expect(await screen.findByText("超级管理员账号已登录")).toBeInTheDocument();
  });

  it("未绑定TOTP的超级管理员必须保存恢复码后才能进入", async () => {
    installFetch({ role: "super_admin", mfaSetupRequired: true });
    const user = await login();
    expect(await screen.findByRole("heading", { name: "绑定TOTP验证器" })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "TOTP绑定二维码" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("6位动态验证码"), "654321");
    await user.click(screen.getByRole("button", { name: "确认绑定" }));
    expect(await screen.findByRole("heading", { name: "保存一次性恢复码" })).toBeInTheDocument();
    expect(screen.getByText("AAAA-BBBB-CCCC-DDDD", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "进入安全管理" })).toBeDisabled();
    await user.click(screen.getByLabelText("我已将恢复码保存在安全位置"));
    await user.click(screen.getByRole("button", { name: "进入安全管理" }));
    expect(await screen.findByRole("heading", { name: "超级管理员安全中心" })).toBeInTheDocument();
  });

  it("超级管理员可以在前端安全更换TOTP验证器", async () => {
    const { calls } = installFetch({ role: "super_admin" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    await user.click(await screen.findByRole("button", { name: "更换验证器" }));
    expect(screen.getByRole("heading", { name: "验证当前身份" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("超级管理员当前密码"), "correct-password");
    await user.type(screen.getByLabelText("当前验证器动态验证码"), "123456");
    await user.click(screen.getByRole("button", { name: "验证并生成新二维码" }));
    expect(await screen.findByRole("heading", { name: "扫描新的二维码" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "新的TOTP绑定二维码" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("新验证器动态验证码"), "654321");
    await user.click(screen.getByRole("button", { name: "确认更换" }));
    expect(await screen.findByRole("heading", { name: "保存新的恢复码" })).toBeInTheDocument();
    expect(screen.getByText("NEW1-AAAA-BBBB-CCCC", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "完成更换" })).toBeDisabled();
    await user.click(screen.getByLabelText("我已将新的恢复码保存在安全位置"));
    await user.click(screen.getByRole("button", { name: "完成更换" }));
    expect(screen.queryByRole("heading", { name: "保存新的恢复码" })).not.toBeInTheDocument();

    const start = calls.find((call) => call.path === "/api/internal/auth/totp/rotate/setup");
    const confirm = calls.find((call) => call.path === "/api/internal/auth/totp/rotate/confirm");
    expect(JSON.parse(String(start?.init?.body))).toEqual({ currentPassword: "correct-password", currentTotpCode: "123456" });
    expect(JSON.parse(String(confirm?.init?.body))).toEqual({ code: "654321" });
    expect(new Headers(start?.init?.headers).get("x-csrf-token")).toBe("csrf-test");
    expect(new Headers(confirm?.init?.headers).get("x-csrf-token")).toBe("csrf-test");
  });

  it("超级管理员只查看磁盘空间并保存阈值配置", async () => {
    const { calls } = installFetch({ role: "super_admin", monitorPercent: 68.4 });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    expect(await screen.findByRole("heading", { name: /磁盘空间监控/ })).toBeInTheDocument();
    expect(screen.getByText("68.4%")).toBeInTheDocument();
    expect(screen.getByText("C:\\data")).toBeInTheDocument();
    expect(screen.queryByLabelText("磁盘占用趋势图")).not.toBeInTheDocument();
    expect(screen.queryByText("邮件告警")).not.toBeInTheDocument();
    expect(calls.some((call) => call.path === "/api/internal/admin/system-monitor/history")).toBe(false);

    const warning = screen.getByLabelText("预警阈值");
    await user.clear(warning);
    await user.type(warning, "82");
    await user.type(screen.getByLabelText("磁盘监控配置密码"), "correct-password");
    await user.click(screen.getByRole("button", { name: "保存监控配置" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/admin/system-monitor/settings")).toBe(true));
    const settingsCall = calls.find((call) => call.path === "/api/internal/admin/system-monitor/settings");
    expect(JSON.parse(String(settingsCall?.init?.body))).toMatchObject({ warningPercent: 82, currentPassword: "correct-password" });
    expect(new Headers(settingsCall?.init?.headers).get("x-csrf-token")).toBe("csrf-test");

  });

  it("切换项目并展示用量和审计", async () => {
    installFetch();
    const user = await login();
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    expect(await screen.findByText("额度已启用")).toBeInTheDocument();
    expect(screen.getByText("avatar-assets/customer_a/portrait.png")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.8", { exact: false })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("企业项目"), "customer_b");
    expect(await screen.findByText("当前不限额")).toBeInTheDocument();
  });

  it("保存项目额度时发送正确契约和 CSRF", async () => {
    const { calls } = installFetch();
    const user = await login();
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    await screen.findByText("额度已启用");
    const projectForm = screen.getByRole("heading", { name: "项目总额度" }).closest("form")!;
    const writeQpm = within(projectForm).getAllByRole("spinbutton")[1] as HTMLInputElement;
    await user.clear(writeQpm); await user.type(writeQpm, "15");
    await user.click(within(projectForm).getByRole("button", { name: "保存项目额度" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/project/quota" && call.init?.method === "PUT")).toBe(true));
    const call = calls.find((item) => item.path === "/api/internal/project/quota" && item.init?.method === "PUT");
    expect(new Headers(call?.init?.headers).get("x-csrf-token")).toBe("csrf-test");
    expect(JSON.parse(String(call?.init?.body))).toMatchObject({ projectName: "customer_a", writeQpm: 15 });
  });

  it("超级管理员可管理账号和撤销其他会话", async () => {
    const { calls } = installFetch({ role: "super_admin" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    expect(await screen.findByText("运营管理员")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.8")).toBeInTheDocument();
    expect(screen.getByText("admin.auth.login")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "重置密码" })[0]).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/auth/sessions/session-old" && call.init?.method === "DELETE")).toBe(true));
  });

  it("服务器备份校验通过后要求密码、TOTP和确认文字才能恢复", async () => {
    const { calls } = installFetch({ role: "super_admin" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    expect(await screen.findByText("avatar_proxy-20260819-080000-000001.db", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "恢复" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "校验" }));
    expect(await screen.findByText("校验通过")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "恢复" }));
    const dialog = screen.getByRole("dialog", { name: "恢复 SQLite 数据库" });
    await user.type(within(dialog).getByLabelText("超级管理员当前密码"), "correct-password");
    await user.type(within(dialog).getByLabelText("新一组 TOTP 动态验证码"), "654321");
    await user.type(within(dialog).getByLabelText("输入“恢复数据库”确认"), "恢复数据库");
    await user.click(within(dialog).getByRole("button", { name: "确认恢复" }));
    expect(await screen.findByRole("heading", { name: "登录内部控制台" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("数据库恢复成功");
    const restoreCall = calls.find((call) => call.path.endsWith("/restore"));
    expect(JSON.parse(String(restoreCall?.init?.body))).toEqual({ currentPassword: "correct-password", totpCode: "654321", confirmation: "恢复数据库" });
    expect(new Headers(restoreCall?.init?.headers).get("x-csrf-token")).toBe("csrf-test");
  });

  it("备份时间带时区偏移时可正常显示", async () => {
    installFetch({ role: "super_admin", backupCreatedAt: "2026-08-19T08:00:00+00:00" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    expect(await screen.findByText("avatar_proxy-20260819-080000-000001.db", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("时间未知")).not.toBeInTheDocument();
  });

  it("备份时间异常时显示占位文案而不使页面崩溃", async () => {
    installFetch({ role: "super_admin", backupCreatedAt: "not-a-date" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    expect(await screen.findByText("时间未知")).toBeInTheDocument();
    expect(screen.getByText("avatar_proxy-20260819-080000-000001.db", { exact: false })).toBeInTheDocument();
  });

  it("创建管理员后可一次复制完整的登录交付文本", async () => {
    installFetch({ role: "super_admin" });
    const user = await login();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    await user.click(await screen.findByRole("button", { name: "创建管理员" }));
    const createDialog = screen.getByRole("dialog", { name: "创建管理员" });
    await user.type(within(createDialog).getByLabelText("用户名"), "operator.new");
    await user.type(within(createDialog).getByLabelText("显示名称"), "新运营管理员");
    await user.type(within(createDialog).getByLabelText("确认超级管理员密码"), "correct-password");
    await user.click(within(createDialog).getByRole("button", { name: "创建管理员" }));

    const deliveryText = await screen.findByLabelText("可转发的管理员登录信息");
    expect((deliveryText as HTMLTextAreaElement).value).toContain("登录地址：http://localhost:3000");
    expect((deliveryText as HTMLTextAreaElement).value).toContain("用户名：operator.new");
    expect((deliveryText as HTMLTextAreaElement).value).toContain("一次性初始密码：Temp-Password-123!");
    expect((deliveryText as HTMLTextAreaElement).value).toContain("首次登录后系统会要求修改密码");

    await user.click(screen.getByRole("button", { name: "复制完整登录信息" }));
    expect(writeText).toHaveBeenCalledWith((deliveryText as HTMLTextAreaElement).value);
    expect(screen.getByRole("button", { name: "已复制，可直接发送" })).toBeInTheDocument();
  });

  it("超级管理员禁用普通管理员后可以永久删除", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = installFetch({ role: "super_admin" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "安全管理" }));
    const operatorRow = (await screen.findByText("运营管理员")).closest(".tableRow")!;
    await user.click(within(operatorRow).getByRole("button", { name: "禁用" }));
    let confirmation = screen.getByRole("dialog", { name: "再次确认超级管理员身份" });
    await user.type(within(confirmation).getByLabelText("超级管理员当前密码"), "correct-password");
    await user.click(within(confirmation).getByRole("button", { name: "验证并继续" }));
    const disabledRow = (await screen.findByText("已禁用")).closest(".tableRow")!;
    await user.click(within(disabledRow).getByRole("button", { name: "删除" }));
    confirmation = screen.getByRole("dialog", { name: "再次确认超级管理员身份" });
    await user.type(within(confirmation).getByLabelText("超级管理员当前密码"), "correct-password");
    await user.click(within(confirmation).getByRole("button", { name: "确认永久删除" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/admin/users/admin-2" && call.init?.method === "DELETE")).toBe(true));
    expect(screen.queryByText("运营管理员")).not.toBeInTheDocument();
  });

  it("普通管理员看不到账号管理入口", async () => {
    const { calls } = installFetch({ role: "admin" });
    await login();
    expect(screen.queryByRole("button", { name: "安全管理" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目" })).toBeInTheDocument();
    expect(calls.some((call) => call.path === "/api/internal/admin/users")).toBe(false);
  });

  it("会话过期后立即回到登录页", async () => {
    installFetch({ expireOnPath: "/api/internal/project/quota" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    const heading = await screen.findByRole("heading", { name: "项目总额度" });
    await user.click(within(heading.closest("form")!).getByRole("button", { name: "保存项目额度" }));
    expect(await screen.findByRole("heading", { name: "登录内部控制台" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("会话已过期");
  });

  it("项目存在 API Key 时禁止确认删除", async () => {
    const { calls } = installFetch({ projects: [{ name: "customer_a", displayName: "客户 A", description: "", keyCount: 1, activeKeyCount: 0, activeAssetCount: 0 }], apiKeys: [{ id: "key-a", name: "停用 Key", keyPrefix: "vap_live_a…", projectName: "customer_a", status: "disabled", createdAt: "2026-08-13 00:00:00" }] });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "项目" }));
    await user.click(screen.getByRole("button", { name: "删除项目 客户 A" }));
    expect(screen.getByText("该项目仍关联 1 个 API Key，因此不能删除。", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认删除" })).toBeDisabled();
    expect(calls.some((call) => call.path === "/api/internal/project/delete")).toBe(false);
  });

  it("新建项目时展示火山校验错误", async () => {
    const { calls } = installFetch({ projectCreateError: "火山引擎中不存在该 ProjectName，请先在火山控制台创建项目" });
    const user = await login();
    await user.click(screen.getByRole("button", { name: "项目" }));
    await user.click(screen.getByRole("button", { name: "新建项目" }));
    await user.type(screen.getByLabelText("火山 ProjectName"), "missing-project");
    await user.click(screen.getByRole("button", { name: "创建项目" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("火山引擎中不存在该 ProjectName");
    expect(new Headers(calls.find((call) => call.path === "/api/internal/project/create")?.init?.headers).get("x-csrf-token")).toBe("csrf-test");
  });
});
