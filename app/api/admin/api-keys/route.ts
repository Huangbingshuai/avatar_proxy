import { requireAdmin } from "@/lib/admin";
import { generateApiKey, sha256 } from "@/lib/crypto";
import { ensureSchema, getRawDb, jsonError } from "@/lib/runtime";

export async function GET(request: Request) {
  const denied = requireAdmin(request);
  if (denied) return denied;
  await ensureSchema();
  const result = await getRawDb().prepare(`
    SELECT id, name, key_prefix AS keyPrefix, project_name AS projectName, status,
      created_at AS createdAt, last_used_at AS lastUsedAt
    FROM api_keys ORDER BY created_at DESC
  `).all();
  return Response.json({ apiKeys: result.results });
}

export async function POST(request: Request) {
  const denied = requireAdmin(request);
  if (denied) return denied;
  const body = await request.json() as { name?: string; projectName?: string };
  const name = body.name?.trim() ?? "";
  const projectName = body.projectName?.trim() ?? "";
  if (!name || !projectName) return jsonError("名称和项目为必填项", 400, "invalid_request");
  await ensureSchema();
  const project = await getRawDb().prepare("SELECT name FROM projects WHERE name = ?").bind(projectName).first();
  if (!project) return jsonError("项目不存在", 404, "project_not_found");

  const apiKey = generateApiKey();
  const id = crypto.randomUUID();
  const keyPrefix = `${apiKey.slice(0, 16)}…`;
  await getRawDb().prepare(
    "INSERT INTO api_keys (id, name, key_prefix, key_hash, project_name) VALUES (?, ?, ?, ?, ?)"
  ).bind(id, name, keyPrefix, await sha256(apiKey), projectName).run();
  return Response.json({ apiKey: { id, name, keyPrefix, projectName, status: "active" }, secret: apiKey }, { status: 201 });
}
