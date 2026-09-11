import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import ApiCallLogsPanel from "../app/api-call-logs-panel";


it("查看调用详情时暂停刷新并在收起后立即更新", async () => {
  const projects = [{ name: "customer_a", displayName: "客户 A" }];
  const apiKeys = [{ id: "key-a", name: "生产 Key", keyPrefix: "vap_live_a…", projectName: "customer_a" }];
  const response = {
    items: [{
      id: 1,
      requestId: "request-log-1",
      apiKeyId: "key-a",
      apiKeyName: "生产 Key",
      apiKeyPrefix: "vap_live_a…",
      projectName: "customer_a",
      method: "GET",
      path: "/api/asset/list",
      routeTemplate: "/api/asset/list",
      action: "list_assets",
      modelAlias: null,
      requestParams: { query: { groupId: "group-1" } },
      statusCode: 200,
      success: true,
      responseSummary: { contentType: "application/json", bodyBytes: 1191 },
      durationMs: 65,
      responseBytes: 1191,
      sourceIp: "127.0.0.1",
      userAgent: "node",
      isModelCall: false,
      createdAt: "2026-09-11 08:00:00",
    }],
    total: 1,
    limit: 50,
    offset: 0,
  };
  const initialApi = vi.fn(async () => response);
  const refreshedApi = vi.fn(async () => response);
  const user = userEvent.setup();
  const { rerender } = render(
    <ApiCallLogsPanel projects={projects} apiKeys={apiKeys} adminApi={initialApi} />,
  );

  await user.selectOptions(screen.getByLabelText("客户项目"), "customer_a");
  await user.selectOptions(screen.getByLabelText("业务 Key"), "key-a");
  expect(await screen.findByText("/api/asset/list")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "展开详情" }));
  expect(screen.getByText("list_assets")).toBeInTheDocument();

  rerender(<ApiCallLogsPanel projects={projects} apiKeys={apiKeys} adminApi={refreshedApi} />);
  await new Promise((resolve) => window.setTimeout(resolve, 20));
  expect(refreshedApi).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "收起详情" })).toBeInTheDocument();
  expect(screen.getByText("list_assets")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "收起详情" }));
  await waitFor(() => expect(refreshedApi).toHaveBeenCalled());
  expect(screen.getByText("实时更新")).toBeInTheDocument();
});
