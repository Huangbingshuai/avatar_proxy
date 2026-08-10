import { requireAdmin } from "@/lib/admin";
import { ensureSchema, getRawDb, jsonError } from "@/lib/runtime";

export async function GET(request: Request) {
  const denied = requireAdmin(request);
  if (denied) return denied;
  await ensureSchema();
  const result = await getRawDb().prepare(`
    SELECT p.name, p.display_name AS displayName, p.description, p.created_at AS createdAt,
      COUNT(k.id) AS keyCount,
      SUM(CASE WHEN k.status = 'active' THEN 1 ELSE 0 END) AS activeKeyCount
    FROM projects p LEFT JOIN api_keys k ON k.project_name = p.name
    GROUP BY p.name ORDER BY p.created_at DESC
  `).all();
  return Response.json({ projects: result.results });
}

export async function POST(request: Request) {
  const denied = requireAdmin(request);
  if (denied) return denied;
  const body = await request.json() as { name?: string; displayName?: string; description?: string };
  const name = body.name?.trim() ?? "";
  const displayName = body.displayName?.trim() || name;
  if (!/^[a-z][a-z0-9_-]{1,62}$/.test(name)) {
    return jsonError("项目标识需以小写字母开头，仅含小写字母、数字、_、-，长度 2-63", 400, "invalid_project_name");
  }
  await ensureSchema();
  try {
    await getRawDb().prepare("INSERT INTO projects (name, display_name, description) VALUES (?, ?, ?)")
      .bind(name, displayName, body.description?.trim() ?? "").run();
    return Response.json({ project: { name, displayName, description: body.description?.trim() ?? "" } }, { status: 201 });
  } catch {
    return jsonError("项目标识已存在", 409, "project_exists");
  }
}
