import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import MonitorEmailSettingsForm, { type MonitorEmailSettings } from "../app/monitor-email-settings";
import type { AdminApi } from "../app/admin-api";

const providers: MonitorEmailSettings["providers"] = [
  { id: "qq", label: "QQ 邮箱", host: "smtp.qq.com", domains: ["qq.com", "foxmail.com"], helpUrl: "https://service.mail.qq.com/" },
  { id: "163", label: "网易 163", host: "smtp.163.com", domains: ["163.com"], helpUrl: "https://help.mail.126.com/" },
  { id: "126", label: "网易 126", host: "smtp.126.com", domains: ["126.com"], helpUrl: "https://help.mail.126.com/" },
  { id: "yeah", label: "网易 Yeah", host: "smtp.yeah.net", domains: ["yeah.net"], helpUrl: "https://help.mail.126.com/" },
];
const email: MonitorEmailSettings = { enabled: true, configured: true, source: "legacy_env",
  recipients: ["ops@qq.com", "owner@163.com"], activeAccountId: "old", providers,
  accounts: [{ id: "old", provider: "qq", host: "smtp.qq.com", port: 465, username: "alerts@qq.com",
    fromEmail: "alerts@qq.com", security: "ssl", timeoutSeconds: 10, passwordConfigured: true }] };

function setup(value = email, failure = "") {
  const api = vi.fn(async (_path: string, options?: RequestInit) => {
    if (failure) throw new Error(failure);
    const payload = JSON.parse(String(options?.body));
    if (!payload.accounts) return { sent: true };
    return { email: { ...value, ...payload, source: "panel", accounts: payload.accounts.map((item: Record<string, unknown>) => ({
      ...item, password: undefined, passwordConfigured: true,
    })) } };
  });
  function Wrapper() {
    const [settings, setSettings] = useState(value);
    return <MonitorEmailSettingsForm email={settings} adminApi={api as AdminApi} onSaved={setSettings} />;
  }
  render(<Wrapper />);
  return { user: userEvent.setup(), api };
}
async function addNetease(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "添加邮箱" }));
  await user.click(screen.getByRole("button", { name: "网易 163" }));
  await user.type(screen.getByLabelText("发件邮箱地址"), "alerts@163.com");
  await user.type(screen.getByLabelText("SMTP授权码"), "netease-test-secret");
  await user.click(screen.getByRole("button", { name: "完成编辑" }));
}

describe("简化的多邮箱通知设置", () => {
  it("删除最后一个发件邮箱后可验证密码保存，自动停用邮件通知", async () => {
    const { user, api } = setup();
    await user.click(screen.getByRole("button", { name: "移除发件邮箱 alerts@qq.com" }));
    expect(screen.getByText("未绑定发件邮箱（可选）")).toBeVisible();
    expect(screen.getByLabelText("启用磁盘邮件通知")).not.toBeChecked();
    expect(screen.getByLabelText("启用磁盘邮件通知")).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存邮件设置" })).toBeDisabled();
    await user.type(screen.getByLabelText("邮件配置验证密码"), "test-password");
    await user.click(screen.getByRole("button", { name: "保存邮件设置" }));
    expect(await screen.findByRole("status")).toHaveTextContent("邮件通知已停用，不影响磁盘监控");
    const saved = JSON.parse(String(api.mock.calls[0][1]?.body));
    expect(saved).toMatchObject({ enabled: false, accounts: [], activeAccountId: null });
    expect(saved.recipients).toEqual(email.recipients);
    expect(screen.getByRole("button", { name: "发送测试邮件" })).toBeDisabled();
  });

  it("删除最后一个收件人可保存，发件授权码仍保留，重新添加需主动启用", async () => {
    const { user, api } = setup();
    for (const recipient of email.recipients) {
      await user.click(screen.getByRole("button", { name: `移除收件邮箱 ${recipient}` }));
    }
    expect(screen.getByLabelText("启用磁盘邮件通知")).not.toBeChecked();
    await user.type(screen.getByLabelText("邮件配置验证密码"), "test-password");
    await user.click(screen.getByRole("button", { name: "保存邮件设置" }));
    await screen.findByRole("status");
    const saved = JSON.parse(String(api.mock.calls[0][1]?.body));
    expect(saved).toMatchObject({ enabled: false, recipients: [], activeAccountId: "old" });
    expect(saved.accounts).toHaveLength(1);
    expect(saved.accounts[0]).not.toHaveProperty("password");
    await user.type(screen.getByLabelText("添加收件邮箱"), "new@qq.com");
    await user.click(screen.getByRole("button", { name: /^添加$/ }));
    expect(screen.getByLabelText("启用磁盘邮件通知")).not.toBeChecked();
    expect(screen.getByLabelText("启用磁盘邮件通知")).toBeEnabled();
    await user.click(screen.getByLabelText("启用磁盘邮件通知"));
    expect(screen.getByLabelText("启用磁盘邮件通知")).toBeChecked();
  });

  it("保留旧邮箱，不展示SMTP字段或授权码，收件人可跨服务", () => {
    setup();
    expect(screen.getByText("alerts@qq.com")).toBeInTheDocument();
    expect(screen.getByText("原有邮箱已保留，授权码无需重新填写。")).toBeInTheDocument();
    expect(screen.queryByLabelText("SMTP服务器")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("SMTP授权码")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "移除收件邮箱 owner@163.com" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存邮件设置" })).toBeDisabled();
  });

  it("添加网易邮箱只填地址和授权码，切换默认发件不丢失旧配置", async () => {
    const { user, api } = setup();
    await addNetease(user);
    expect(api).not.toHaveBeenCalled();
    await user.click(screen.getByRole("radio", { name: "使用 alerts@163.com 发件" }));
    await user.type(screen.getByLabelText("邮件配置验证密码"), "test-password");
    expect(screen.getByRole("button", { name: "发送测试邮件" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "保存邮件设置" }));
    expect(await screen.findByRole("status")).toHaveTextContent("邮件设置已保存");
    const saved = JSON.parse(String(api.mock.calls[0][1]?.body));
    expect(saved.accounts).toHaveLength(2);
    expect(saved.accounts[0]).not.toHaveProperty("password");
    expect(saved.accounts[1]).toMatchObject({ provider: "163", host: "smtp.163.com", username: "alerts@163.com", password: "netease-test-secret", port: 465 });
    expect(saved.activeAccountId).toBe(saved.accounts[1].id);
    expect(screen.getByLabelText("邮件配置验证密码")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "编辑 alerts@163.com" }));
    expect(screen.getByLabelText("SMTP授权码")).toHaveValue("");
  });

  it("批量添加收件人、去重、移除和自己接收，无需收件授权码", async () => {
    const { user, api } = setup();
    await user.click(screen.getByLabelText("添加收件邮箱"));
    await user.paste("other@126.com;third@qq.com\nother@126.com");
    expect(screen.getAllByRole("button", { name: "移除收件邮箱 other@126.com" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "移除收件邮箱 ops@qq.com" }));
    await user.click(screen.getByRole("button", { name: "自己也接收：alerts@qq.com" }));
    await user.type(screen.getByLabelText("邮件配置验证密码"), "test-password");
    await user.click(screen.getByRole("button", { name: "保存邮件设置" }));
    await waitFor(() => expect(api).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(api.mock.calls[0][1]?.body)).recipients).toEqual(["owner@163.com", "other@126.com", "third@qq.com", "alerts@qq.com"]);
  });

  it("变更已有邮箱身份必须重新输入授权码，取消编辑不保存", async () => {
    const { user, api } = setup();
    await user.click(screen.getByRole("button", { name: "编辑 alerts@qq.com" }));
    expect(screen.getByLabelText("SMTP授权码")).toHaveValue("");
    await user.clear(screen.getByLabelText("发件邮箱地址"));
    await user.type(screen.getByLabelText("发件邮箱地址"), "new@qq.com");
    await user.click(screen.getByRole("button", { name: "完成编辑" }));
    expect(screen.getByRole("alert")).toHaveTextContent("重新填写授权码");
    await user.click(screen.getByRole("button", { name: "取消编辑邮箱" }));
    expect(api).not.toHaveBeenCalled();
    expect(screen.getByText("alerts@qq.com")).toBeInTheDocument();
    expect(screen.queryByText("new@qq.com")).not.toBeInTheDocument();
  });

  it("服务不匹配、无授权码和重复发件地址均提示，不新增账号", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "添加邮箱" }));
    await user.type(screen.getByLabelText("发件邮箱地址"), "wrong@163.com");
    await user.click(screen.getByRole("button", { name: "完成编辑" }));
    expect(screen.getByRole("alert")).toHaveTextContent("与所选服务不匹配");
    await user.clear(screen.getByLabelText("发件邮箱地址"));
    await user.type(screen.getByLabelText("发件邮箱地址"), "alerts@qq.com");
    await user.click(screen.getByRole("button", { name: "完成编辑" }));
    expect(screen.getByRole("alert")).toHaveTextContent("授权码");
    await user.type(screen.getByLabelText("SMTP授权码"), "new-test-secret");
    await user.click(screen.getByRole("button", { name: "完成编辑" }));
    expect(screen.getByRole("alert")).toHaveTextContent("已添加");
  });

  it("其他邮箱才展开高级参数，测试使用已保存配置并清空验证密码", async () => {
    const { user, api } = setup();
    await user.click(screen.getByRole("button", { name: "添加邮箱" }));
    await user.click(screen.getByRole("button", { name: "其他邮箱" }));
    expect(screen.getByLabelText("SMTP服务器")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "取消编辑邮箱" }));
    await user.type(screen.getByLabelText("邮件配置验证密码"), "test-password");
    await user.click(screen.getByRole("button", { name: "发送测试邮件" }));
    expect(await screen.findByRole("status")).toHaveTextContent("测试邮件已发送");
    expect(api.mock.calls[0][0]).toBe("/api/internal/admin/system-monitor/email/test");
    expect(screen.getByLabelText("邮件配置验证密码")).toHaveValue("");
  });

  it("加载中禁止操作，保存失败清空本次输入的授权码并保留邮箱草稿", async () => {
    const api = vi.fn();
    const rendered = render(<MonitorEmailSettingsForm adminApi={api as AdminApi} onSaved={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("正在加载");
    expect(screen.getByLabelText("启用磁盘邮件通知")).toBeDisabled();
    rendered.unmount();
    const { user } = setup(email, "服务暂不可用");
    await addNetease(user);
    await user.type(screen.getByLabelText("邮件配置验证密码"), "test-password");
    await user.click(screen.getByRole("button", { name: "保存邮件设置" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("服务暂不可用");
    expect(screen.getByLabelText("邮件配置验证密码")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "编辑 alerts@163.com" }));
    expect(screen.getByLabelText("SMTP授权码")).toHaveValue("");
    expect(within(screen.getByRole("region", { name: "编辑发件邮箱" })).getByLabelText("发件邮箱地址")).toHaveValue("alerts@163.com");
  });
});
