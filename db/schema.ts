import { sql } from "drizzle-orm";
import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const projects = sqliteTable("projects", {
  name: text("name").primaryKey(),
  displayName: text("display_name").notNull(),
  description: text("description").notNull().default(""),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});

export const apiKeys = sqliteTable("api_keys", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  keyPrefix: text("key_prefix").notNull(),
  keyHash: text("key_hash").notNull().unique(),
  projectName: text("project_name").notNull().references(() => projects.name),
  status: text("status", { enum: ["active", "revoked"] }).notNull().default("active"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  lastUsedAt: text("last_used_at"),
});

export const requestLogs = sqliteTable("request_logs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  apiKeyId: text("api_key_id").notNull(),
  projectName: text("project_name").notNull(),
  action: text("action").notNull(),
  statusCode: integer("status_code").notNull(),
  durationMs: integer("duration_ms").notNull(),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});
