import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminApiError, refreshAdminCsrf, requestAdminApi, type AdminUser } from "../app/admin-api";

afterEach(() => vi.unstubAllGlobals());
const user = { id: "owner", role: "super_admin", mfaVerified: true, mustChangePassword: false } as AdminUser;

describe("管理请求安全错误与只读CSRF恢复", () => {
  it("仅对已绑定且开启免TOTP登录的同一超级管理员允许恢复CSRF，不伪造MFA状态", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { ...user, mfaVerified: false, totpEnabled: true, loginTotpBypass: true }, csrfToken: "csrf-password-only" })));
    vi.stubGlobal("fetch", fetch);
    await expect(refreshAdminCsrf(user)).resolves.toBe("csrf-password-only");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { ...user, mfaVerified: false, totpEnabled: false, loginTotpBypass: true }, csrfToken: "must-not-use" }))));
    await expect(refreshAdminCsrf(user)).rejects.toMatchObject({ code: "invalid_admin_session" });
  });

  it("保留错误码和请求编号且照常发送Session/CSRF", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "invalid_csrf_token", message: "CSRF 令牌无效" } }), { status: 403, headers: { "x-request-id": "req_csrf_test" } }));
    vi.stubGlobal("fetch", fetch);
    await expect(requestAdminApi("/api/internal/provider/channels", { method: "POST", body: "{}" }, "csrf-old"))
      .rejects.toMatchObject({ status: 403, code: "invalid_csrf_token", requestId: "req_csrf_test" });
    expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
    expect(new Headers(fetch.mock.calls[0][1].headers).get("x-csrf-token")).toBe("csrf-old");
  });

  it("FastAPI校验明细只展示字段，不展示密码、Key或input", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [
      { loc: ["body", "secret"], input: "provider-secret-never-display", msg: "secret-never-display" },
      { loc: ["body", "currentPassword"], input: "password-never-display" },
    ] }), { status: 422 })));
    const error = await requestAdminApi("/api/internal/provider/channels").catch((error: AdminApiError) => error);
    expect(error).toMatchObject({ code: "invalid_request_parameter" });
    expect(error.message).toContain("供应商 API Key");
    expect(error.message).not.toContain("never-display");
    expect(error.message).not.toContain("object Object");
  });

  it("非JSON成功响应不能误报保存成功", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>gateway</html>", { status: 200 })));
    await expect(requestAdminApi("/api/internal/provider/channels")).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("同一账号仅GET获取CSRF，不重放写请求", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ user, csrfToken: "csrf-new" }));
    vi.stubGlobal("fetch", fetch);
    await expect(refreshAdminCsrf(user)).resolves.toBe("csrf-new");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/internal/auth/me");
    expect(fetch.mock.calls[0][1].method).toBe("GET");
  });

  it.each([
    { ...user, id: "other-owner" }, { ...user, role: "admin" },
    { ...user, mfaVerified: false }, { ...user, mustChangePassword: true },
  ])("身份或安全状态变化时不静默接管新会话", async (changedUser) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ user: changedUser, csrfToken: "csrf-new" })));
    await expect(refreshAdminCsrf(user)).rejects.toMatchObject({ code: "invalid_admin_session" });
  });

  it("会话恢复失败或缺少CSRF时拒绝继续使用旧令牌", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ user })));
    await expect(refreshAdminCsrf(user)).rejects.toMatchObject({ code: "invalid_admin_session" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ error: { code: "admin_session_expired", message: "会话过期" } }, { status: 401 })));
    await expect(refreshAdminCsrf(user)).rejects.toMatchObject({ code: "admin_session_expired" });
  });

  it("只读会话恢复最多等待5秒，不让提交按钮无限等待", async () => {
    vi.stubGlobal("fetch", vi.fn((_path, init) => new Promise((_, reject) => {
      init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      const result = refreshAdminCsrf(user).catch((error) => error);
      await vi.advanceTimersByTimeAsync(5_000);
      expect(await result).toMatchObject({ name: "AbortError" });
    } finally {
      vi.useRealTimers();
    }
  });
});
