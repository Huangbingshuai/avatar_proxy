import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConsolePage from "../app/page";


type MockData = {
  projects?: Array<Record<string, unknown>>;
  apiKeys?: Array<Record<string, unknown>>;
  events?: Array<Record<string, unknown>>;
  audits?: Array<Record<string, unknown>>;
  projectQuotaError?: string;
};


function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}


function installFetch(data: MockData = {}) {
  const projects = data.projects ?? [
    { name: "customer_a", displayName: "客户 A", description: "", keyCount: 1, activeKeyCount: 1 },
    { name: "customer_b", displayName: "客户 B", description: "", keyCount: 1, activeKeyCount: 1 },
  ];
  const apiKeys = data.apiKeys ?? [
    { id: "key-a", name: "生产 Key", keyPrefix: "vap_live_a…", projectName: "customer_a", status: "active", createdAt: "2026-08-13 00:00:00" },
    { id: "key-b", name: "批处理 Key", keyPrefix: "vap_live_b…", projectName: "customer_b", status: "active", createdAt: "2026-08-13 00:00:00" },
  ];
  const events = data.events ?? [
    { id: 7, projectName: "customer_a", scopeType: "project", metric: "read_qpm", threshold: 90, limitValue: 100, usedValue: 90, acknowledged: false, createdAt: "2026-08-13 00:00:00" },
  ];
  const audits = data.audits ?? [
    { id: 8, sourceIp: "10.0.0.8", action: "quota.project.update", targetType: "project", targetId: "customer_a", createdAt: "2026-08-13 00:00:00" },
  ];
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    calls.push({ path: `${url.pathname}${url.search}`, init });
    const token = new Headers(init?.headers).get("x-admin-token");
    if (token !== "valid-token") {
      return jsonResponse({ error: { message: "管理令牌无效" } }, 401);
    }
    if (url.pathname === "/api/internal/project/list") return jsonResponse({ projects });
    if (url.pathname === "/api/internal/apikey/list") return jsonResponse({ apiKeys });
    if (url.pathname === "/api/internal/overview") {
      return jsonResponse({
        stats: { projects: projects.length, activeKeys: apiKeys.length, requests24h: 12, errors24h: 1, assetsToday: 3, uploadsToday: 2, uploadBytesToday: 2048, limitedProjects: 1, openQuotaEvents: events.filter((event) => !event.acknowledged).length, cleanupPending: 1 },
        recent: [],
      });
    }
    if (url.pathname === "/api/internal/quota/events") return jsonResponse({ events });
    if (url.pathname === "/api/internal/quota/audits") return jsonResponse({ audits });
    if (url.pathname === "/api/internal/quota/usage") {
      const projectName = url.searchParams.get("projectName") ?? "customer_a";
      return jsonResponse({
        projectName,
        quota: {
          projectName,
          enabled: projectName === "customer_a",
          readQpm: projectName === "customer_a" ? 100 : null,
          writeQpm: projectName === "customer_a" ? 20 : null,
          maxConcurrency: null,
          dailyAssetCreates: null,
          dailyUploadFiles: null,
          dailyUploadBytes: null,
          totalAssets: 10,
          totalStorageBytes: 1024,
        },
        usage: { readQpm: 70, writeQpm: 4, totalAssets: 3, totalStorageBytes: 512, cleanupPending: 1 },
        cleanupObjects: [{ recordId: "upload-1", objectKey: `avatar-assets/${projectName}/portrait.png`, sizeBytes: 512, status: "cleanup_pending", cleanupAttempts: 2, createdAt: "2026-08-13 00:00:00" }],
      });
    }
    if (url.pathname === "/api/internal/apikey/quota") {
      return jsonResponse({ quota: { keyId: url.searchParams.get("keyId"), readQpm: 50, writeQpm: null, maxConcurrency: null, dailyAssetCreates: null, dailyUploadFiles: null, dailyUploadBytes: null } });
    }
    if (url.pathname === "/api/internal/project/quota" && init?.method === "PUT") {
      if (data.projectQuotaError) return jsonResponse({ error: { message: data.projectQuotaError } }, 400);
      return jsonResponse({ quota: {} });
    }
    if (url.pathname === "/api/internal/apikey/quota" && init?.method === "PUT") return jsonResponse({ quota: {} });
    if (url.pathname === "/api/internal/quota/event/ack") return jsonResponse({ acknowledged: true });
    return jsonResponse({ error: { message: `未模拟接口 ${url.pathname}` } }, 500);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}


async function unlock(token = "valid-token") {
  const user = userEvent.setup();
  render(<ConsolePage />);
  await user.type(screen.getByLabelText("管理令牌"), token);
  await user.click(screen.getByRole("button", { name: "进入控制台" }));
  return user;
}


describe("内部控制台", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("使用管理令牌解锁并加载控制台", async () => {
    const { calls } = installFetch();
    await unlock();

    await waitFor(() => expect(screen.queryByText("解锁内部控制台")).not.toBeInTheDocument());
    expect(screen.getByText("INTERNAL CONTROL PLANE")).toBeInTheDocument();
    expect(calls.filter((call) => call.path.startsWith("/api/internal/")).length).toBe(5);
    expect(calls.every((call) => new Headers(call.init?.headers).get("x-admin-token") === "valid-token")).toBe(true);
  });

  it("加载失败时保持锁定并展示服务端错误", async () => {
    installFetch();
    await unlock("wrong-token");

    expect(await screen.findByText("管理令牌无效")).toBeInTheDocument();
    expect(screen.getByText("解锁内部控制台")).toBeInTheDocument();
  });

  it("切换项目并展示启用状态、用量、待清理对象和审计", async () => {
    installFetch();
    const user = await unlock();
    await waitFor(() => expect(screen.queryByText("解锁内部控制台")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "额度与用量" }));

    expect(await screen.findByText("额度已启用")).toBeInTheDocument();
    expect(screen.getByText("上限 100")).toBeInTheDocument();
    expect(screen.getByText("avatar-assets/customer_a/portrait.png")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.8", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("90% · 90/100", { exact: false })).toBeInTheDocument();

    const projectSelect = screen.getByLabelText("企业项目");
    await user.selectOptions(projectSelect, "customer_b");
    expect(await screen.findByText("当前不限额")).toBeInTheDocument();
    expect(screen.getByText("avatar-assets/customer_b/portrait.png")).toBeInTheDocument();
    expect(screen.getAllByText("不限额").length).toBeGreaterThan(1);
  });

  it("保存项目额度与 Key 子额度时发送正确契约", async () => {
    const { calls } = installFetch();
    const user = await unlock();
    await waitFor(() => expect(screen.queryByText("解锁内部控制台")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    await screen.findByText("额度已启用");

    const projectForm = screen.getByRole("heading", { name: "项目总额度" }).closest("form");
    expect(projectForm).not.toBeNull();
    const writeQpm = within(projectForm!).getAllByRole("spinbutton")[1] as HTMLInputElement;
    await user.clear(writeQpm);
    await user.type(writeQpm, "15");
    await user.click(within(projectForm!).getByRole("button", { name: "保存项目额度" }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/project/quota" && call.init?.method === "PUT")).toBe(true));
    const projectCall = calls.find((call) => call.path === "/api/internal/project/quota" && call.init?.method === "PUT");
    expect(JSON.parse(String(projectCall?.init?.body))).toMatchObject({ projectName: "customer_a", enabled: true, writeQpm: 15, readQpm: 100 });

    const keyForm = screen.getByRole("heading", { name: "API Key 子额度" }).closest("form");
    expect(keyForm).not.toBeNull();
    const keyWriteQpm = within(keyForm!).getAllByRole("spinbutton")[1] as HTMLInputElement;
    await user.type(keyWriteQpm, "5");
    await user.click(within(keyForm!).getByRole("button", { name: "保存 Key 子额度" }));
    expect(await screen.findByText("API Key 子额度已保存；留空字段继续继承项目")).toBeInTheDocument();

    const keyCall = calls.find((call) => call.path === "/api/internal/apikey/quota" && call.init?.method === "PUT");
    expect(JSON.parse(String(keyCall?.init?.body))).toMatchObject({ keyId: "key-a", readQpm: 50, writeQpm: 5 });
  });

  it("确认额度事件并显示空数据状态", async () => {
    const { calls } = installFetch({ projects: [], apiKeys: [], events: [], audits: [] });
    const user = await unlock();
    await waitFor(() => expect(screen.queryByText("解锁内部控制台")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    expect(screen.getByText("暂无额度事件")).toBeInTheDocument();
    expect(screen.getByText("当前没有待处理对象")).toBeInTheDocument();
    expect(screen.getByText("暂无额度修改记录")).toBeInTheDocument();
    expect(calls.some((call) => call.path.includes("quota/usage"))).toBe(false);
  });

  it("确认额度事件会调用确认接口并刷新", async () => {
    const { calls } = installFetch();
    const user = await unlock();
    await waitFor(() => expect(screen.queryByText("解锁内部控制台")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    await user.click(await screen.findByRole("button", { name: "确认" }));

    await waitFor(() => expect(calls.some((call) => call.path === "/api/internal/quota/event/ack")).toBe(true));
    const acknowledgement = calls.find((call) => call.path === "/api/internal/quota/event/ack");
    expect(JSON.parse(String(acknowledgement?.init?.body))).toEqual({ eventId: 7 });
    expect(calls.filter((call) => call.path === "/api/internal/project/list").length).toBeGreaterThan(1);
  });

  it("项目额度保存失败时展示接口错误", async () => {
    installFetch({ projectQuotaError: "项目额度配置无效" });
    const user = await unlock();
    await waitFor(() => expect(screen.queryByText("解锁内部控制台")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "额度与用量" }));
    await screen.findByText("额度已启用");
    const projectForm = screen.getByRole("heading", { name: "项目总额度" }).closest("form");
    await user.click(within(projectForm!).getByRole("button", { name: "保存项目额度" }));
    expect(await screen.findByText("项目额度配置无效")).toBeInTheDocument();
  });
});
