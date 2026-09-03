import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(import.meta.dirname, "..");
const nginxTemplate = readFileSync(
  resolve(root, "deploy/volcengine/api-nginx.conf.template"),
  "utf8",
);
const compose = readFileSync(resolve(root, "deploy/volcengine/compose.yaml"), "utf8");
const edgeNginx = readFileSync(resolve(root, "deploy/volcengine/nginx.conf"), "utf8");

function callbackLocation(): string {
  const start = nginxTemplate.indexOf(
    "location = /minidrama/payments/callbacks/wechat {",
  );
  const end = nginxTemplate.indexOf("\n    location = /health", start);
  expect(start).toBeGreaterThanOrEqual(0);
  expect(end).toBeGreaterThan(start);
  return nginxTemplate.slice(start, end);
}

describe("LocalMiniDrama WeChat callback gateway", () => {
  it("exposes only the exact callback path and rejects non-POST methods", () => {
    const location = callbackLocation();
    expect(location).toContain("if ($request_method != POST)");
    expect(location).toContain("return 405;");
  });

  it("forwards the original body and required WeChat Pay headers", () => {
    const location = callbackLocation();
    expect(location).toContain(
      "proxy_pass http://${PAYMENT_ORIGIN}/api/v1/payments/callbacks/wechat;",
    );
    expect(location).toContain("proxy_pass_request_headers on;");
    expect(location).toContain("proxy_pass_request_body on;");
    expect(location).not.toMatch(/\bproxy_set_body\b|\bsub_filter\b/);

    for (const header of [
      "Wechatpay-Timestamp",
      "Wechatpay-Nonce",
      "Wechatpay-Signature",
      "Wechatpay-Serial",
    ]) {
      expect(location).toContain(`proxy_set_header ${header} $http_${header.toLowerCase().replace("-", "_")};`);
    }
    expect(location).toContain("proxy_set_header Content-Type $content_type;");
  });

  it("uses the handoff timeouts and never retries the payment POST", () => {
    const location = callbackLocation();
    expect(location).toContain("proxy_connect_timeout 5s;");
    expect(location).toContain("proxy_send_timeout 30s;");
    expect(location).toContain("proxy_read_timeout 30s;");
    expect(location).toContain("proxy_next_upstream off;");
    expect(location).toContain("proxy_intercept_errors off;");
  });

  it("uses a safe callback log that excludes body and signature values", () => {
    expect(nginxTemplate).toContain("log_format minidrama_callback_safe");
    const logFormat = nginxTemplate.slice(0, nginxTemplate.indexOf("server {"));
    expect(logFormat).not.toMatch(/request_body|http_wechatpay_signature/i);
  });

  it("keeps the gateway isolated and resolves only the two deployment variables", () => {
    expect(compose).toContain(
      'PAYMENT_ORIGIN: "${PAYMENT_ORIGIN:-host.docker.internal:10588}"',
    );
    expect(compose).toContain(
      'PAYMENT_ORIGIN_HOST: "${PAYMENT_ORIGIN_HOST:-drama.richbest.cn}"',
    );
    expect(compose).toContain(
      'NGINX_ENVSUBST_FILTER: "^(PAYMENT_ORIGIN|PAYMENT_ORIGIN_HOST)$"',
    );
    expect(compose).toContain('"host.docker.internal:host-gateway"');
    expect(compose).not.toMatch(/lens-rhyme_default|minidrama.*network/i);
  });
});

describe("model request body limits", () => {
  it("does not let the user edge impose a lower Base64 limit than the HTTPS gateway", () => {
    expect(nginxTemplate).toContain("client_max_body_size 210m;");
    expect(edgeNginx).toContain("client_max_body_size 210m;");
  });
});
