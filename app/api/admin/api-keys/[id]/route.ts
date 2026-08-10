import { requireAdmin } from "@/lib/admin";
import { ensureSchema, getRawDb, jsonError } from "@/lib/runtime";

export async function DELETE(request: Request, context: { params: Promise<{ id: string }> }) {
  const denied = requireAdmin(request);
  if (denied) return denied;
  await ensureSchema();
  const { id } = await context.params;
  const result = await getRawDb().prepare("UPDATE api_keys SET status = 'revoked' WHERE id = ? AND status = 'active'").bind(id).run();
  if (!result.meta.changes) return jsonError("API Key 不存在或已撤销", 404, "api_key_not_found");
  return Response.json({ revoked: true });
}
