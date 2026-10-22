import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AdminApiError, type AdminApi } from "../app/admin-api";
import ProviderChannelsPanel from "../app/provider-channels-panel";

async function setup(create: (init?: RequestInit) => Promise<Record<string, unknown>>) {
  const api = vi.fn<AdminApi>(async (path, init) => {
    if (init?.method === "POST") return create(init);
    if (path.endsWith("/projects")) return { projects: [{ name: "test_hb", displayName: "测试项目" }] };
    return { channels: [] };
  });
  render(<ProviderChannelsPanel adminApi={api} />);
  await waitFor(() => expect(screen.queryByText("渠道加载中…")).not.toBeInTheDocument());
  await waitFor(() => expect(api).toHaveBeenCalledWith("/api/internal/provider/projects"));
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "创建渠道" }));
  const dialog = screen.getByRole("dialog");
  await user.type(within(dialog).getByLabelText("渠道名称"), "ModelTop测试渠道");
  await user.selectOptions(within(dialog).getByLabelText("供应商"), "modeltop");
  await user.type(within(dialog).getByLabelText(/^供应商 API Key/), "test-provider-secret");
  await user.type(within(dialog).getByLabelText("超级管理员当前密码"), "test-owner-password");
  await user.type(within(dialog).getByLabelText("TOTP 动态验证码"), "123456");
  return { api, user, dialog, posts: () => api.mock.calls.filter(([, init]) => init?.method === "POST") };
}

describe("渠道弹窗提交反馈", () => {
  it("Vega凭证成对提交，站点及SubAppId不混入Secret", async () => {
    const create = vi.fn().mockResolvedValue({ channel: {} });
    const { user, dialog } = await setup(create);
    await user.selectOptions(within(dialog).getByLabelText("供应商"), "vega");
    await user.selectOptions(within(dialog).getByLabelText("腾讯云站点"), "international");
    await user.type(within(dialog).getByLabelText("SubAppId"), "123456");
    await user.type(within(dialog).getByLabelText("SecretId"), "example-id-12345678");
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    const body = JSON.parse(create.mock.calls[0][0].body);
    expect(body.provider).toBe("vega");
    expect(body.config).toEqual({ site: "international", subAppId: "123456" });
    expect(JSON.parse(body.secret)).toEqual({ secretId: "example-id-12345678", secretKey: "test-provider-secret" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it.each([
    ["invalid_csrf_token", 403, "安全校验已失效"],
    ["csrf_token_refreshed", 403, "安全校验已更新"],
    ["admin_reauthentication_failed", 401, "密码不正确"],
    ["invalid_admin_totp", 401, "验证码错误或已过期"],
    ["admin_totp_replayed", 401, "等待下一组"],
    ["super_admin_required", 403, "重新登录超级管理员"],
  ])("%s错误在弹窗按钮上方可见，不泄漏凭证", async (code, status, text) => {
    const create = vi.fn().mockRejectedValue(new AdminApiError(code === "csrf_token_refreshed" ? "安全校验已更新，请重新提交" : "操作失败", Number(status), String(code), undefined, "req_channel_test"));
    const { user, dialog } = await setup(create);
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    const error = await within(dialog).findByRole("alert");
    expect(error).toHaveTextContent(String(text));
    expect(error).toHaveTextContent("req_channel_test");
    expect(error).not.toHaveTextContent("test-provider-secret");
    expect(error).not.toHaveTextContent("test-owner-password");
    expect(error).toHaveFocus();
    expect(within(dialog).getByRole("button", { name: "加密保存渠道" })).toBeEnabled();
    if (["csrf_token_refreshed", "invalid_admin_totp", "admin_totp_replayed"].includes(String(code))) {
      expect(within(dialog).getByLabelText("TOTP 动态验证码")).toHaveValue("");
    }
  });

  it("前端必填校验直接提示，不发送请求", async () => {
    const { user, dialog, posts } = await setup(async () => ({}));
    await user.clear(within(dialog).getByLabelText("渠道名称"));
    await user.type(within(dialog).getByLabelText("渠道名称"), "   ");
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("请填写渠道名称");
    expect(posts()).toHaveLength(0);
  });

  it("短Key和不完整验证码不会静默拦截", async () => {
    const { user, dialog, posts } = await setup(async () => ({}));
    const secret = within(dialog).getByLabelText(/^供应商 API Key/);
    await user.clear(secret); await user.type(secret, "short");
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("8～4096");
    await user.type(secret, "-long-enough");
    await user.clear(within(dialog).getByLabelText("TOTP 动态验证码"));
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("请输入6位");
    expect(posts()).toHaveLength(0);
  });

  it("提交中有加载态，按钮/关闭禁用，重复submit不会再次创建", async () => {
    let finish!: (result: Record<string, unknown>) => void;
    const { user, dialog, posts } = await setup(() => new Promise((resolve) => { finish = resolve; }));
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    expect(within(dialog).getByRole("button", { name: "正在创建" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "关闭" })).toBeDisabled();
    fireEvent.submit(dialog.querySelector("form")!);
    expect(posts()).toHaveLength(1);
    finish({ channel: {} });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("渠道已创建");
  });

  it.each([new TypeError("Failed to fetch"), new DOMException("aborted", "AbortError")])("网络/超时错误提示先确认结果，避免重复创建", async (error) => {
    const { user, dialog } = await setup(async () => { throw error; });
    await user.click(within(dialog).getByRole("button", { name: "加密保存渠道" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("刷新渠道列表");
    await user.click(within(dialog).getByRole("button", { name: "关闭" }));
    await user.click(screen.getByRole("button", { name: "创建渠道" }));
    const fresh = screen.getByRole("dialog");
    expect(within(fresh).getByLabelText(/^供应商 API Key/)).toHaveValue("");
    expect(within(fresh).getByLabelText("超级管理员当前密码")).toHaveValue("");
    expect(within(fresh).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("真实20秒超时会解除加载状态，且不自动重试", async () => {
    const { dialog, posts } = await setup((init) => new Promise((_, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      fireEvent.submit(dialog.querySelector("form")!);
      expect(within(dialog).getByRole("button", { name: "正在创建" })).toBeDisabled();
      await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
      expect(within(dialog).getByRole("alert")).toHaveTextContent("请求等待超时");
      expect(within(dialog).getByRole("button", { name: "加密保存渠道" })).toBeEnabled();
      expect(posts()).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
