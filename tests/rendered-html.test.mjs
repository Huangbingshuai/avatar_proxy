import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("server-renders the internal Avatar Proxy console", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>Avatar Proxy · 内部控制台<\/title>/i);
  assert.match(html, /正在验证会话/);
  assert.doesNotMatch(html, /CONSOLE_ADMIN_TOKEN|X-Admin-Token/i);
  assert.match(html, /控制台与公网 API/);
  assert.match(html, /http:\/\/(?:localhost|127\.0\.0\.1):8000/);
  assert.doesNotMatch(
    html,
    /SEEDANCE_(?:ARK_)?API_KEY|VOLCENGINE_(?:ACCESS|SECRET)_KEY|TOS_(?:ACCESS|SECRET)_KEY|test-admin|test-ak|test-sk|test-ark-key|C:\\Users\\/i,
  );
});
