import { authenticateApiKey } from "./api-auth";
import { callVolcengine } from "./volcengine";
import { jsonError } from "./runtime";

export async function proxyAction(request: Request, action: string, body: Record<string, unknown>) {
  const principal = await authenticateApiKey(request);
  if (principal instanceof Response) return principal;
  delete body.ProjectName;
  delete body.projectName;
  return callVolcengine(action, body, principal);
}

export async function readJson(request: Request) {
  try {
    return await request.json() as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function badJson() {
  return jsonError("请求体必须是合法 JSON", 400, "invalid_json");
}
