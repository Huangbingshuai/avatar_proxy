import { afterEach, describe, expect, it, vi } from "vitest";
import { testRelayImage, testRelayTextStream } from "../user-portal/src/api";

afterEach(() => vi.unstubAllGlobals());

describe("customer generation resilience", () => {
  it("does not abort or automatically replay a slow image request", async () => {
    let finish!: (response: Response) => void;
    const fetcher = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetcher);
    const pending = testRelayImage("test-key", "gpt-image-2", "circle", "same-request");
    expect(fetcher).toHaveBeenCalledTimes(1);
    const init = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(init[1].signal).toBeUndefined();
    expect(new Headers(init[1].headers).get("Idempotency-Key")).toBe("same-request");
    finish(new Response(JSON.stringify({ data: [{ url: "https://example.com/a.png" }] })));
    await expect(pending).resolves.toMatchObject({ status: 200 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("explains ambiguous network failures without retrying", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetcher);
    await expect(testRelayImage("test-key", "gpt-image-2", "circle", "one")).rejects.toThrow("上游可能仍在执行");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("shows gateway ambiguity and preserves diagnostic request ids", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<h1>504</h1>", {
      status: 504, headers: { "x-request-id": "req-timeout" },
    })));
    await expect(testRelayImage("test-key", "gpt-image-2", "circle", "one")).rejects.toThrow("req-timeout");
  });

  it("surfaces SSE errors and does not call a truncated stream successful", async () => {
    for (const body of [
      'data: {"error":{"code":"provider_response_timeout","message":"等待供应商响应超时"}}\n\n',
      'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
    ]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
      await expect(testRelayTextStream("test-key", "glm-5.2", "hi")).rejects.toThrow(/超时|提前结束/);
    }
  });

  it("accepts a normally terminated stream", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      'data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n\n',
    )));
    const result = await testRelayTextStream("test-key", "glm-5.2", "hi");
    expect(JSON.stringify(result.body)).toContain("OK");
  });

  it("explains a network failure during streamed output", async () => {
    const body = new ReadableStream({ start(controller) { controller.error(new TypeError("network lost")); } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    await expect(testRelayTextStream("test-key", "glm-5.2", "hi")).rejects.toThrow("流式连接中断");
    expect(body.locked).toBe(false);
  });
});
