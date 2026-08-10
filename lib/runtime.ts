import { env } from "cloudflare:workers";

export type RuntimeEnv = {
  DB: D1Database;
  VOLCENGINE_ACCESS_KEY?: string;
  VOLCENGINE_SECRET_KEY?: string;
  CONSOLE_ADMIN_TOKEN?: string;
};

export function getRuntimeEnv(): RuntimeEnv {
  return env as unknown as RuntimeEnv;
}

export function getRawDb(): D1Database {
  const db = getRuntimeEnv().DB;
  if (!db) throw new Error("D1 binding DB is unavailable");
  return db;
}

let schemaReady: Promise<void> | undefined;

export function ensureSchema() {
  if (!schemaReady) {
    const db = getRawDb();
    schemaReady = db.batch([
      db.prepare(`CREATE TABLE IF NOT EXISTS projects (
        name TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )`),
      db.prepare(`CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        key_prefix TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        project_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_used_at TEXT,
        FOREIGN KEY(project_name) REFERENCES projects(name)
      )`),
      db.prepare(`CREATE TABLE IF NOT EXISTS request_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key_id TEXT NOT NULL,
        project_name TEXT NOT NULL,
        action TEXT NOT NULL,
        status_code INTEGER NOT NULL,
        duration_ms INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )`),
      db.prepare("CREATE INDEX IF NOT EXISTS idx_api_keys_project_status ON api_keys(project_name, status)"),
      db.prepare("CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at)"),
    ]).then(() => undefined).catch((error) => {
      schemaReady = undefined;
      throw error;
    });
  }
  return schemaReady;
}

export function jsonError(message: string, status: number, code: string) {
  return Response.json({ error: { code, message } }, { status });
}
