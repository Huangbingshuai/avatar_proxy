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
  expireOnPath?: string;
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
  const currentUser = { id: "admin-1", username: "owner", displayName: "系统管理员", role: data.role ?? "super_admin", status: "active", mustChangePassword: Boolean(data.mustChangePassword), createdAt: "2026-08-10 00:00:00", lastLoginAt: "2026-08-19 08:00:00", lastLoginIp: "127.0.0.1" };
  let users = [currentUser, { id: "admin-2", username: "operator", displayName: "运营管理员", role: "admin", status: "active", mustChangePassword: false, createdAt: "2026-08-11 00:00:00", lastLoginAt: "2026-08-18 08:00:00", lastLoginIp: "10.0.0.8" }];
  const sessions = [
    { id: "session-current", current: true, createdAt: 1787107200, lastSeenAt: 1787107800, absoluteExpiresAt: 1787150400, sourceIp: "127.0.0.1", userAgent: "Windows Chrome" },
    { id: "session-old", current: false, createdAt: 1787020800, lastSeenAt: 1787024400, absoluteExpiresAt: 1787110800, sourceIp: "10.0.0.8", userAgent: "Macintosh Safari" },
  ];
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
    await user.click(screen.getByRole("button", { name: "管理员" }));
    expect(await screen.findByText("运营管理员")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.8")).toBeInTheDocument();
    expect(screen.getByText("admin.auth.login")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "重置密码" })[0]).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/auth/sessions/session-old" && call.init?.method === "DELETE")).toBe(true));
  });

  it("创建管理员后可一次复制完整的登录交付文本", async () => {
    installFetch({ role: "super_admin" });
    const user = await login();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: "管理员" }));
    await user.click(await screen.findByRole("button", { name: "创建管理员" }));
    const createDialog = screen.getByRole("dialog", { name: "创建管理员" });
    await user.type(within(createDialog).getByLabelText("用户名"), "operator.new");
    await user.type(within(createDialog).getByLabelText("显示名称"), "新运营管理员");
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
    await user.click(screen.getByRole("button", { name: "管理员" }));
    const operatorRow = (await screen.findByText("运营管理员")).closest(".tableRow")!;
    await user.click(within(operatorRow).getByRole("button", { name: "禁用" }));
    const disabledRow = (await screen.findByText("已禁用")).closest(".tableRow")!;
    await user.click(within(disabledRow).getByRole("button", { name: "删除" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/admin/users/admin-2" && call.init?.method === "DELETE")).toBe(true));
    expect(screen.queryByText("运营管理员")).not.toBeInTheDocument();
  });

  it("普通管理员看不到账号管理入口", async () => {
    const { calls } = installFetch({ role: "admin" });
    await login();
    expect(screen.queryByRole("button", { name: "管理员" })).not.toBeInTheDocument();
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
