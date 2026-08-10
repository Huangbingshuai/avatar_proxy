import { getRuntimeEnv, jsonError } from "./runtime";
import { safeEqual } from "./crypto";

export function requireAdmin(request: Request) {
  const configured = getRuntimeEnv().CONSOLE_ADMIN_TOKEN;
  if (!configured) {
    return jsonError("服务端尚未配置 CONSOLE_ADMIN_TOKEN", 503, "admin_not_configured");
  }
  const supplied = request.headers.get("x-admin-token") ?? "";
  if (!safeEqual(supplied, configured)) {
    return jsonError("管理令牌无效", 401, "invalid_admin_token");
  }
  return null;
}
