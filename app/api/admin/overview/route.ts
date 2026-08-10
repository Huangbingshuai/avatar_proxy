import { requireAdmin } from "@/lib/admin";
import { ensureSchema, getRawDb } from "@/lib/runtime";

export async function GET(request: Request) {
  const denied = requireAdmin(request);
  if (denied) return denied;
  await ensureSchema();
  const stats = await getRawDb().prepare(`
    SELECT
      (SELECT COUNT(*) FROM projects) AS projects,
      (SELECT COUNT(*) FROM api_keys WHERE status = 'active') AS activeKeys,
      (SELECT COUNT(*) FROM request_logs WHERE created_at >= datetime('now', '-24 hours')) AS requests24h,
      (SELECT COUNT(*) FROM request_logs WHERE status_code >= 400 AND created_at >= datetime('now', '-24 hours')) AS errors24h
  `).first();
  const recent = await getRawDb().prepare(`
    SELECT action, project_name AS projectName, status_code AS statusCode,
      duration_ms AS durationMs, created_at AS createdAt
    FROM request_logs ORDER BY id DESC LIMIT 8
  `).all();
  return Response.json({ stats, recent: recent.results });
}
