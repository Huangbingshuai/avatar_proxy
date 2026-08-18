import { beforeEach, describe, expect, it, vi } from "vitest";

import { getArkVideoUsage } from "../user-portal/src/api";


function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}


describe("工具前端方舟用量查询", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("只在查询请求头中发送方舟 Key，并解析 Seedance 聚合用量", async () => {
    const calls: Array<{ url: URL; authorization: string | null }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const authorization = new Headers(init?.headers).get("authorization");
      calls.push({ url, authorization });
      if (url.pathname === "/api/video/ark-usage") {
        return jsonResponse({
          source: "volcengine_ark",
          scope: "ark_api_key",
          keySuffix: "123456789abc",
          start: url.searchParams.get("start"),
          end: url.searchParams.get("end"),
          interval: url.searchParams.get("interval"),
          dataDelayMinutes: { min: 5, max: 30 },
          billingAmountIncluded: false,
          summary: { inputTokens: 0, outputTokens: 35800, totalTokens: 35800, requestCount: 2, metrics: {} },
          records: [{
            date: "2026-08-18",
            modelName: "doubao-seedance-2-5",
            endpointId: "ep-example",
            inputTokens: 0,
            outputTokens: 35800,
            totalTokens: 35800,
            requestCount: 2,
          }],
        });
      }
      return jsonResponse({ error: { message: "unexpected request" } }, 500);
    }));

    const arkKey = "ark-customer-secret-key-123456";
    const result = await getArkVideoUsage(arkKey, "2026-08-01", "2026-08-18", "Day");
    expect(result.summary.totalTokens).toBe(35800);
    expect(result.records[0]?.modelName).toBe("doubao-seedance-2-5");
    expect(result.keySuffix).toBe("123456789abc");

    const arkCall = calls.find((call) => call.url.pathname === "/api/video/ark-usage");
    expect(arkCall?.authorization).toBe(`Bearer ${arkKey}`);
    expect(arkCall?.url.searchParams.get("interval")).toBe("Day");
    expect(arkCall?.url.toString()).not.toContain(arkKey);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
