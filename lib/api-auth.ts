import { ensureSchema, getRawDb, jsonError } from "./runtime";
import { sha256 } from "./crypto";

export type ApiPrincipal = { id: string; projectName: string };

export async function authenticateApiKey(request: Request): Promise<ApiPrincipal | Response> {
  const authorization = request.headers.get("authorization") ?? "";
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  if (!match) return jsonError("请使用 Authorization: Bearer <API_KEY>", 401, "missing_api_key");

  await ensureSchema();
  const keyHash = await sha256(match[1]);
  const row = await getRawDb().prepare(
    "SELECT id, project_name AS projectName FROM api_keys WHERE key_hash = ? AND status = 'active' LIMIT 1"
  ).bind(keyHash).first<ApiPrincipal>();
  if (!row) return jsonError("API Key 无效或已撤销", 401, "invalid_api_key");

  await getRawDb().prepare("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?").bind(row.id).run();
  return row;
}
