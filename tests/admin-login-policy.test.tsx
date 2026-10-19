import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AdminLoginPolicy from "../app/admin-login-policy";
import { AdminApiError, type AdminApi } from "../app/admin-api";

const policyUrl = "/api/internal/admin/security/login-policy";
function setup(enabled = false, failure = "") {
  const api = vi.fn(async (_path: string, options?: RequestInit) => {
    if (options?.method === "PUT") {
      if (failure) throw new AdminApiError(failure, 403, "csrf_token_refreshed");
      const body = JSON.parse(String(options.body));
      return { policy: { loginTotpBypass: body.loginTotpBypass, totpEnabled: true },
        user: { id: "owner", role: "super_admin", loginTotpBypass: body.loginTotpBypass, mfaVerified: true }, otherSessionsRevoked: 2 };
    }
    return { policy: { loginTotpBypass: enabled, totpEnabled: true } };
  });
  const onUserChanged = vi.fn();
  const onRotate = vi.fn();
  render(<AdminLoginPolicy adminApi={api as AdminApi} onRotate={onRotate} onUserChanged={onUserChanged} />);
  return { api, onUserChanged, onRotate, user: userEvent.setup() };
}
async function open(user: ReturnType<typeof userEvent.setup>, enabled = false) {
  const button = await screen.findByRole("button", { name: enabled ? "恢复TOTP登录" : "开启免TOTP登录" });
  await waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
  return screen.getByRole("dialog");
}
async function confirm(user: ReturnType<typeof userEvent.setup>, dialog: HTMLElement) {
  await user.type(within(dialog).getByLabelText("登录安全设置验证密码"), "current-test-password");
  await user.type(within(dialog).getByLabelText("登录安全设置动态验证码"), "123456");
  await user.click(within(dialog).getByLabelText("确认修改登录验证方式"));
}

describe("超级管理员登录TOTP开关", () => {
  it("默认保护，不会自动改变登录方式，确认密码、TOTP和风险后才能开启", async () => {
    const { api, user, onUserChanged } = setup();
    const dialog = await open(user);
    expect(api.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(0);
    const save = within(dialog).getByRole("button", { name: "确认开启免TOTP登录" });
    expect(save).toBeDisabled();
    await user.type(within(dialog).getByLabelText("登录安全设置验证密码"), "current-test-password");
    await user.type(within(dialog).getByLabelText("登录安全设置动态验证码"), "123456");
    expect(save).toBeDisabled();
    await user.click(within(dialog).getByLabelText("确认修改登录验证方式"));
    await user.click(save);
    expect(await screen.findByRole("status")).toHaveTextContent("已开启免TOTP登录");
    expect(screen.getByRole("button", { name: "恢复TOTP登录" })).toBeEnabled();
    const call = api.mock.calls.find(([, options]) => options?.method === "PUT");
    expect(call?.[0]).toBe(policyUrl);
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ loginTotpBypass: true, currentPassword: "current-test-password", totpCode: "123456" });
    expect(onUserChanged).toHaveBeenCalledWith(expect.objectContaining({ loginTotpBypass: true, mfaVerified: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("恢复TOTP同样需要确认，成功后显示二次验证保护状态", async () => {
    const { api, user } = setup(true);
    const dialog = await open(user, true);
    expect(screen.getByText("仅密码登录")).toBeInTheDocument();
    await confirm(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "确认恢复TOTP登录" }));
    expect(await screen.findByRole("status")).toHaveTextContent("已恢复TOTP登录");
    expect(screen.getByText("二次验证保护中")).toBeInTheDocument();
    const call = api.mock.calls.find(([, options]) => options?.method === "PUT");
    expect(JSON.parse(String(call?.[1]?.body)).loginTotpBypass).toBe(false);
  });

  it("取消清空敏感输入，操作失败不切换状态、不自动重试", async () => {
    const { api, user } = setup(false, "请使用新的动态验证码重新提交");
    let dialog = await open(user);
    await confirm(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    dialog = await open(user);
    expect(within(dialog).getByLabelText("登录安全设置验证密码")).toHaveValue("");
    expect(within(dialog).getByLabelText("登录安全设置动态验证码")).toHaveValue("");
    await confirm(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "确认开启免TOTP登录" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("重新提交");
    expect(within(dialog).getByLabelText("登录安全设置验证密码")).toHaveValue("");
    expect(within(dialog).getByLabelText("登录安全设置动态验证码")).toHaveValue("");
    expect(api.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(1);
    expect(screen.getByText("二次验证保护中")).toBeInTheDocument();
  });

  it("读取失败时禁止开关，允许重新读取，不影响原有换绑入口", async () => {
    const api = vi.fn().mockRejectedValueOnce(new Error("加载失败")).mockResolvedValue({ policy: { loginTotpBypass: false, totpEnabled: true } });
    const rotate = vi.fn();
    const user = userEvent.setup();
    render(<AdminLoginPolicy adminApi={api} onRotate={rotate} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("加载失败");
    expect(screen.getByRole("button", { name: "开启免TOTP登录" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "重新读取" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "开启免TOTP登录" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "更换验证器" }));
    expect(rotate).toHaveBeenCalledTimes(1);
  });
});
