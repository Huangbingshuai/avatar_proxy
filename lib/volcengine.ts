import { deriveVolcengineSigningKey, hmacHex, sha256 } from "./crypto";
import { getRawDb, getRuntimeEnv, jsonError } from "./runtime";
import type { ApiPrincipal } from "./api-auth";

const REGION = "cn-beijing";
const SERVICE = "ark";
const VERSION = "2024-01-01";
const HOST = "ark.cn-beijing.volcengineapi.com";

function utcStamp(date: Date) {
  return date.toISOString().replace(/[:-]|\.\d{3}/g, "");
}

export async function callVolcengine(action: string, body: Record<string, unknown>, principal: ApiPrincipal) {
  const started = Date.now();
  const runtime = getRuntimeEnv();
  const accessKey = runtime.VOLCENGINE_ACCESS_KEY;
  const secretKey = runtime.VOLCENGINE_SECRET_KEY;
  if (!accessKey || !secretKey) {
    return jsonError("服务端尚未配置火山引擎 AK/SK", 503, "upstream_credentials_missing");
  }

  const payload = JSON.stringify({ ...body, ProjectName: principal.projectName });
  const payloadHash = await sha256(payload);
  const now = new Date();
  const xDate = utcStamp(now);
  const shortDate = xDate.slice(0, 8);
  const query = `Action=${encodeURIComponent(action)}&Version=${encodeURIComponent(VERSION)}`;
  const canonicalHeaders = `content-type:application/json\nhost:${HOST}\nx-content-sha256:${payloadHash}\nx-date:${xDate}\n`;
  const signedHeaders = "content-type;host;x-content-sha256;x-date";
  const canonicalRequest = `POST\n/\n${query}\n${canonicalHeaders}\n${signedHeaders}\n${payloadHash}`;
  const scope = `${shortDate}/${REGION}/${SERVICE}/request`;
  const stringToSign = `HMAC-SHA256\n${xDate}\n${scope}\n${await sha256(canonicalRequest)}`;
  const signingKey = await deriveVolcengineSigningKey(secretKey, shortDate, REGION, SERVICE);
  const signature = await hmacHex(signingKey, stringToSign);
  const authorization = `HMAC-SHA256 Credential=${accessKey}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;

  let response: Response;
  try {
    response = await fetch(`https://${HOST}/?${query}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        host: HOST,
        "x-content-sha256": payloadHash,
        "x-date": xDate,
        authorization,
      },
      body: payload,
    });
  } catch {
    return jsonError("无法连接火山引擎服务", 502, "upstream_unreachable");
  }

  const raw = await response.text();
  let data: unknown = raw;
  try { data = JSON.parse(raw); } catch { /* preserve upstream text */ }

  await getRawDb().prepare(
    "INSERT INTO request_logs (api_key_id, project_name, action, status_code, duration_ms) VALUES (?, ?, ?, ?, ?)"
  ).bind(principal.id, principal.projectName, action, response.status, Date.now() - started).run();

  return Response.json(data, {
    status: response.status,
    headers: { "x-upstream-service": "volcengine-ark" },
  });
}
