import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SEEDREAM_MAX_INPUT_IMAGE_BYTES = 10 * 1024 * 1024


BUILTIN_MODEL_CATALOG = (
    ("deepseek-v4-flash", "DeepSeek V4 Flash", "volcengine_ark", "text", "openai_text", "deepseek-v4-flash-260425", {"chat": True, "responses": True, "stream": True}),
    ("glm-5.2", "GLM 5.2", "volcengine_ark", "text", "openai_text", "glm-5-2-260617", {"chat": True, "responses": True, "stream": True}),
    ("seedream-5.0-pro", "Seedream 5.0 Pro", "volcengine_ark", "image", "openai_image", "doubao-seedream-5-0-pro-260628", {"generations": True, "imageInput": True, "maxInputImages": 10, "maxInputImageBytes": SEEDREAM_MAX_INPUT_IMAGE_BYTES, "maxN": 1}),
    ("seedream-5.0-lite", "Seedream 5.0 Lite", "volcengine_ark", "image", "openai_image", "doubao-seedream-5-0-lite-260128", {"generations": True, "imageInput": True, "maxInputImages": 10, "maxInputImageBytes": SEEDREAM_MAX_INPUT_IMAGE_BYTES, "sequentialImages": True, "maxN": 15, "outputFormat": True, "webSearch": True}),
    ("seedream-5.0", "Seedream 5.0", "volcengine_ark", "image", "openai_image", "doubao-seedream-5-0-260128", {"generations": True, "imageInput": True, "maxInputImages": 10, "maxInputImageBytes": SEEDREAM_MAX_INPUT_IMAGE_BYTES, "maxN": 1, "outputFormat": True, "webSearch": True}),
    ("seedream-4.5", "Seedream 4.5", "volcengine_ark", "image", "openai_image", "doubao-seedream-4-5-251128", {"generations": True, "imageInput": True, "maxInputImages": 10, "maxInputImageBytes": SEEDREAM_MAX_INPUT_IMAGE_BYTES, "sequentialImages": True, "maxN": 15}),
    ("seedream-4.0", "Seedream 4.0", "volcengine_ark", "image", "openai_image", "doubao-seedream-4-0-250828", {"generations": True, "imageInput": True, "maxInputImages": 10, "maxInputImageBytes": SEEDREAM_MAX_INPUT_IMAGE_BYTES, "sequentialImages": True, "maxN": 15}),
    ("doubao-seed-2.1-pro", "Doubao Seed 2.1 Pro", "volcengine_ark", "text", "openai_text", "doubao-seed-2-1-pro-260628", {"chat": True, "responses": True, "stream": True, "imageInput": True, "vision": True}),
    ("doubao-seed-2.1-turbo", "Doubao Seed 2.1 Turbo", "volcengine_ark", "text", "openai_text", "doubao-seed-2-1-turbo-260628", {"chat": True, "responses": True, "stream": True, "imageInput": True, "vision": True}),
    ("doubao-seed-2.0-pro", "Doubao Seed 2.0 Pro", "volcengine_ark", "text", "openai_text", "doubao-seed-2-0-pro-260215", {"chat": True, "responses": True, "stream": True, "imageInput": True, "vision": True}),
    ("doubao-seed-2.0-lite", "Doubao Seed 2.0 Lite", "volcengine_ark", "text", "openai_text", "doubao-seed-2-0-lite-260428", {"chat": True, "responses": True, "stream": True, "imageInput": True, "vision": True}),
    ("doubao-seed-2.0-mini", "Doubao Seed 2.0 Mini", "volcengine_ark", "text", "openai_text", "doubao-seed-2-0-mini-260215", {"chat": True, "responses": True, "stream": True, "imageInput": True, "vision": True}),
    ("seedance-2.5", "Seedance 2.5", "volcengine_ark", "video", "async_video", "doubao-seedance-2-5-260628", {"text": True, "image": True, "video": True, "audio": True, "generateAudio": True, "durationMin": 4, "durationMax": 30, "smartDuration": True, "resolutions": ["480p", "720p", "1080p"], "maxContent": 50, "maxN": 1}),
    ("seedance-2.0", "Seedance 2.0", "volcengine_ark", "video", "async_video", "doubao-seedance-2-0-260128", {"text": True, "image": True, "video": True, "audio": True, "generateAudio": True, "durationMin": 4, "durationMax": 15, "smartDuration": True, "resolutions": ["480p", "720p", "1080p"], "maxContent": 20, "maxN": 1}),
    ("seedance-2.0-fast", "Seedance 2.0 Fast", "volcengine_ark", "video", "async_video", "doubao-seedance-2-0-fast-260128", {"text": True, "image": True, "video": True, "audio": True, "generateAudio": True, "durationMin": 4, "durationMax": 15, "smartDuration": True, "resolutions": ["480p", "720p"], "maxContent": 20, "maxN": 1}),
    ("seedance-2.0-mini", "Seedance 2.0 Mini", "volcengine_ark", "video", "async_video", "doubao-seedance-2-0-mini-260615", {"text": True, "image": True, "video": True, "audio": True, "durationMin": 4, "durationMax": 15, "smartDuration": True, "resolutions": ["480p", "720p"], "maxContent": 20, "maxN": 1}),
    ("seedance-1.0-pro", "Seedance 1.0 Pro", "volcengine_ark", "video", "async_video", "doubao-seedance-1-0-pro-250528", {"text": True, "image": True, "durationMin": 2, "durationMax": 12, "frames": True, "resolutions": ["480p", "720p", "1080p"], "maxN": 1}),
    ("seedance-1.0-pro-fast", "Seedance 1.0 Pro Fast", "volcengine_ark", "video", "async_video", "doubao-seedance-1-0-pro-fast-251015", {"text": True, "image": True, "durationMin": 2, "durationMax": 12, "frames": True, "resolutions": ["480p", "720p", "1080p"], "maxN": 1}),
    ("wan3.0-video", "Wan 3.0 Video", "aliyun_bailian", "video", "async_video", "wan3.0-video", {"image": True, "maxN": 1}),
    ("minimax-h3", "MiniMax H3", "minimax", "video", "async_video", "MiniMax-H3", {"image": True, "maxN": 1}),
    ("image2.0", "Image 2.0", "openai", "image", "openai_image", "gpt-image-2", {"generations": True}),
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT,
    deleted_at TEXT,
    FOREIGN KEY(project_name) REFERENCES projects(name)
);
CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    action TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS video_usage (
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    task_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(api_key_id, task_id)
);
CREATE TABLE IF NOT EXISTS video_tasks (
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    task_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hidden INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(api_key_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_api_keys_project_status ON api_keys(project_name, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name_nocase ON projects(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_video_usage_api_key_created_at ON video_usage(api_key_id, created_at);
CREATE INDEX IF NOT EXISTS idx_video_tasks_api_key_created_at ON video_tasks(api_key_id, created_at DESC);
CREATE TABLE IF NOT EXISTS project_quotas (
    project_name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    read_qpm INTEGER,
    write_qpm INTEGER,
    max_concurrency INTEGER,
    daily_asset_creates INTEGER,
    daily_upload_files INTEGER,
    daily_upload_bytes INTEGER,
    total_assets INTEGER,
    total_storage_bytes INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS api_key_quotas (
    api_key_id TEXT PRIMARY KEY,
    read_qpm INTEGER,
    write_qpm INTEGER,
    max_concurrency INTEGER,
    daily_asset_creates INTEGER,
    daily_upload_files INTEGER,
    daily_upload_bytes INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS quota_usage_windows (
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    window_start TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    reserved INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(scope_type, scope_id, metric, window_start)
);
CREATE TABLE IF NOT EXISTS quota_reservations (
    reservation_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    window_start TEXT NOT NULL,
    amount INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(reservation_id, scope_type, scope_id, metric)
);
CREATE TABLE IF NOT EXISTS asset_records (
    record_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    api_key_id TEXT NOT NULL,
    group_id TEXT,
    asset_id TEXT,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    bucket TEXT,
    object_key TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    asset_type TEXT NOT NULL DEFAULT 'Image',
    content_type TEXT,
    media_metadata_json TEXT,
    status TEXT NOT NULL,
    cleanup_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS quota_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    api_key_id TEXT,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    threshold INTEGER NOT NULL,
    limit_value INTEGER NOT NULL,
    used_value INTEGER NOT NULL,
    window_start TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TEXT,
    UNIQUE(scope_type, scope_id, metric, threshold, window_start)
);
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    source_ip TEXT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS admin_users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    username_normalized TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin' CHECK(role IN ('super_admin','admin')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
    must_change_password INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    failure_window_started_at INTEGER,
    locked_until INTEGER,
    last_login_at TEXT,
    last_login_ip TEXT,
    password_changed_at TEXT,
    totp_secret_encrypted TEXT,
    totp_pending_secret_encrypted TEXT,
    totp_pending_session_id TEXT,
    totp_pending_expires_at INTEGER,
    totp_enabled_at TEXT,
    totp_last_timecode INTEGER,
    created_by_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(created_by_id) REFERENCES admin_users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    absolute_expires_at INTEGER NOT NULL,
    source_ip TEXT,
    user_agent TEXT,
    mfa_verified INTEGER NOT NULL DEFAULT 0,
    revoked_at INTEGER,
    revoke_reason TEXT,
    FOREIGN KEY(admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS admin_recovery_codes (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_at TEXT,
    FOREIGN KEY(admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS admin_security_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info','warning','critical')),
    message TEXT NOT NULL,
    actor_id TEXT,
    actor TEXT NOT NULL,
    source_ip TEXT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    details_json TEXT,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS admin_backup_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL CHECK(status IN ('running','success','failed')),
    database_file TEXT,
    audit_file TEXT,
    database_bytes INTEGER,
    audit_bytes INTEGER,
    error TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS admin_restore_runs (
    id TEXT PRIMARY KEY,
    backup_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success','failed')),
    actor TEXT NOT NULL,
    source_ip TEXT,
    rollback_backup_id TEXT,
    summary_json TEXT,
    error TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS system_monitor_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    enabled INTEGER NOT NULL DEFAULT 1,
    warning_percent REAL NOT NULL DEFAULT 80,
    critical_percent REAL NOT NULL DEFAULT 90,
    emergency_percent REAL NOT NULL DEFAULT 95,
    recovery_percent REAL NOT NULL DEFAULT 75,
    updated_by TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS disk_usage_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    total_bytes INTEGER NOT NULL,
    used_bytes INTEGER NOT NULL,
    available_bytes INTEGER NOT NULL,
    reserved_bytes INTEGER NOT NULL DEFAULT 0,
    used_percent REAL NOT NULL,
    level TEXT NOT NULL CHECK(level IN ('normal','warning','critical','emergency')),
    sampled_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS system_monitor_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    active_disk_incident_id TEXT,
    disk_alerted_levels_json TEXT NOT NULL DEFAULT '[]',
    recovery_streak INTEGER NOT NULL DEFAULT 0,
    probe_failure_streak INTEGER NOT NULL DEFAULT 0,
    probe_alert_active INTEGER NOT NULL DEFAULT 0,
    last_sampled_at INTEGER,
    last_persisted_at INTEGER,
    last_error TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS system_monitor_email_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at INTEGER NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    FOREIGN KEY(alert_id) REFERENCES admin_security_alerts(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS provider_channels (
    id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    name TEXT NOT NULL,
    provider TEXT NOT NULL CHECK(provider IN ('openai','volcengine_ark','aliyun_bailian','minimax')),
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
    last_test_status TEXT CHECK(last_test_status IN ('success','failed')),
    last_test_at TEXT,
    last_test_latency_ms INTEGER,
    last_test_error TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE RESTRICT,
    UNIQUE(project_name, name)
);
CREATE TABLE IF NOT EXISTS provider_credentials (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    secret_ciphertext TEXT NOT NULL,
    secret_hint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','retired')),
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retired_at TEXT,
    FOREIGN KEY(channel_id) REFERENCES provider_channels(id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS model_catalog (
    alias TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    modality TEXT NOT NULL CHECK(modality IN ('text','image','video')),
    protocol TEXT NOT NULL,
    upstream_model TEXT NOT NULL,
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_model_bindings (
    project_name TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    upstream_model TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(project_name, model_alias),
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE,
    FOREIGN KEY(model_alias) REFERENCES model_catalog(alias) ON DELETE RESTRICT,
    FOREIGN KEY(channel_id) REFERENCES provider_channels(id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS api_key_model_permissions (
    api_key_id TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(api_key_id, model_alias),
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE,
    FOREIGN KEY(model_alias) REFERENCES model_catalog(alias) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS inference_tasks (
    id TEXT PRIMARY KEY,
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    upstream_model TEXT NOT NULL,
    upstream_task_id TEXT,
    operation TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','canceled')),
    progress INTEGER NOT NULL DEFAULT 0,
    request_hash TEXT NOT NULL,
    idempotency_key TEXT,
    result_url TEXT,
    result_format TEXT,
    error_code TEXT,
    error_message TEXT,
    provider_request_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    billing_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE RESTRICT,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE RESTRICT,
    FOREIGN KEY(model_alias) REFERENCES model_catalog(alias) ON DELETE RESTRICT,
    FOREIGN KEY(channel_id) REFERENCES provider_channels(id) ON DELETE RESTRICT,
    FOREIGN KEY(credential_id) REFERENCES provider_credentials(id) ON DELETE RESTRICT,
    UNIQUE(api_key_id, operation, idempotency_key)
);
CREATE TABLE IF NOT EXISTS inference_usage (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    task_id TEXT,
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    provider_request_id TEXT,
    status TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    generated_images INTEGER,
    video_seconds REAL,
    video_width INTEGER,
    video_height INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settled_at TEXT,
    FOREIGN KEY(task_id) REFERENCES inference_tasks(id) ON DELETE SET NULL,
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE RESTRICT,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE RESTRICT,
    FOREIGN KEY(model_alias) REFERENCES model_catalog(alias) ON DELETE RESTRICT,
    FOREIGN KEY(channel_id) REFERENCES provider_channels(id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS billing_model_rates (
    id TEXT PRIMARY KEY,
    model_alias TEXT NOT NULL,
    metric TEXT NOT NULL CHECK(metric IN ('input_tokens','output_tokens','image','video_second')),
    resolution TEXT NOT NULL DEFAULT '',
    effective_month TEXT NOT NULL,
    unit_size INTEGER NOT NULL CHECK(unit_size > 0),
    unit_price_micros INTEGER NOT NULL CHECK(unit_price_micros >= 0),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(model_alias) REFERENCES model_catalog(alias) ON DELETE RESTRICT,
    UNIQUE(model_alias,metric,resolution,effective_month)
);
CREATE TABLE IF NOT EXISTS project_billing_terms (
    id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    effective_month TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    discount_bps INTEGER NOT NULL DEFAULT 10000 CHECK(discount_bps BETWEEN 0 AND 10000),
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE RESTRICT,
    UNIQUE(project_name,effective_month)
);
CREATE TABLE IF NOT EXISTS billing_statements (
    id TEXT PRIMARY KEY,
    statement_number TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    billing_month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','confirmed','paid')),
    currency TEXT NOT NULL DEFAULT 'CNY' CHECK(currency='CNY'),
    subtotal_micros INTEGER NOT NULL DEFAULT 0,
    discount_micros INTEGER NOT NULL DEFAULT 0,
    adjustment_micros INTEGER NOT NULL DEFAULT 0,
    total_micros INTEGER NOT NULL DEFAULT 0,
    pending_count INTEGER NOT NULL DEFAULT 0,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TEXT,
    confirmed_by TEXT,
    paid_at TEXT,
    paid_by TEXT,
    payment_reference TEXT,
    payment_note TEXT,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE RESTRICT,
    UNIQUE(project_name,billing_month)
);
CREATE TABLE IF NOT EXISTS billing_usage_items (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK(source_type IN ('relay','legacy_video')),
    source_id TEXT NOT NULL,
    api_key_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    usage_month TEXT NOT NULL,
    billing_month TEXT NOT NULL,
    late_from_month TEXT,
    occurred_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('rated','pending','excluded')),
    pending_reason TEXT,
    discount_bps INTEGER NOT NULL DEFAULT 10000,
    list_amount_micros INTEGER,
    net_amount_micros INTEGER,
    statement_id TEXT,
    rated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE RESTRICT,
    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE RESTRICT,
    FOREIGN KEY(statement_id) REFERENCES billing_statements(id) ON DELETE RESTRICT,
    UNIQUE(source_type,source_id)
);
CREATE TABLE IF NOT EXISTS billing_usage_components (
    item_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    resolution TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL,
    unit_size INTEGER NOT NULL,
    rate_id TEXT,
    unit_price_micros INTEGER,
    list_amount_micros INTEGER,
    net_amount_micros INTEGER,
    PRIMARY KEY(item_id,metric,resolution),
    FOREIGN KEY(item_id) REFERENCES billing_usage_items(id) ON DELETE CASCADE,
    FOREIGN KEY(rate_id) REFERENCES billing_model_rates(id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS billing_statement_lines (
    id TEXT PRIMARY KEY,
    statement_id TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    metric TEXT NOT NULL,
    resolution TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL,
    unit_size INTEGER NOT NULL,
    unit_price_micros INTEGER NOT NULL,
    list_amount_micros INTEGER NOT NULL,
    net_amount_micros INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(statement_id) REFERENCES billing_statements(id) ON DELETE CASCADE,
    UNIQUE(statement_id,model_alias,metric,resolution,unit_price_micros)
);
CREATE TABLE IF NOT EXISTS billing_adjustments (
    id TEXT PRIMARY KEY,
    statement_id TEXT NOT NULL,
    amount_micros INTEGER NOT NULL CHECK(amount_micros != 0),
    reason TEXT NOT NULL,
    adjustment_type TEXT NOT NULL DEFAULT 'manual' CHECK(adjustment_type IN ('manual','late_usage')),
    source_item_id TEXT,
    source_statement_id TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(statement_id) REFERENCES billing_statements(id) ON DELETE CASCADE,
    FOREIGN KEY(source_statement_id) REFERENCES billing_statements(id) ON DELETE RESTRICT,
    FOREIGN KEY(source_item_id) REFERENCES billing_usage_items(id) ON DELETE RESTRICT,
    UNIQUE(source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_quota_events_open ON quota_events(acknowledged, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_asset_records_project_status ON asset_records(project_name, status);
CREATE INDEX IF NOT EXISTS idx_asset_records_asset_id ON asset_records(project_name, asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_records_cleanup ON asset_records(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_admin_users_status ON admin_users(status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_users_single_super
    ON admin_users(role) WHERE role='super_admin';
CREATE INDEX IF NOT EXISTS idx_admin_sessions_user_active
    ON admin_sessions(admin_user_id, revoked_at, absolute_expires_at);
CREATE INDEX IF NOT EXISTS idx_admin_recovery_codes_user
    ON admin_recovery_codes(admin_user_id, used_at);
CREATE INDEX IF NOT EXISTS idx_admin_security_alerts_open
    ON admin_security_alerts(acknowledged_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_backup_runs_started
    ON admin_backup_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_restore_runs_started
    ON admin_restore_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_disk_usage_samples_sampled
    ON disk_usage_samples(sampled_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_monitor_email_deliveries_pending
    ON system_monitor_email_deliveries(status, next_attempt_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_monitor_email_deliveries_alert
    ON system_monitor_email_deliveries(alert_id) WHERE alert_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_provider_channels_project_status
    ON provider_channels(project_name, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_credentials_active
    ON provider_credentials(channel_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_project_model_bindings_channel
    ON project_model_bindings(channel_id, enabled);
CREATE INDEX IF NOT EXISTS idx_api_key_model_permissions_key
    ON api_key_model_permissions(api_key_id, enabled);
CREATE INDEX IF NOT EXISTS idx_inference_tasks_lookup
    ON inference_tasks(api_key_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inference_tasks_channel_status
    ON inference_tasks(channel_id, status);
CREATE INDEX IF NOT EXISTS idx_inference_usage_project_created
    ON inference_usage(project_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_rates_lookup
    ON billing_model_rates(model_alias,metric,resolution,effective_month DESC);
CREATE INDEX IF NOT EXISTS idx_billing_terms_lookup
    ON project_billing_terms(project_name,effective_month DESC);
CREATE INDEX IF NOT EXISTS idx_billing_items_month
    ON billing_usage_items(project_name,billing_month,status);
CREATE INDEX IF NOT EXISTS idx_billing_statements_month
    ON billing_statements(billing_month,status);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            asset_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(asset_records)").fetchall()
            }
            if "asset_type" not in asset_columns:
                connection.execute(
                    "ALTER TABLE asset_records ADD COLUMN asset_type TEXT NOT NULL DEFAULT 'Image'"
                )
            if "content_type" not in asset_columns:
                connection.execute("ALTER TABLE asset_records ADD COLUMN content_type TEXT")
            if "media_metadata_json" not in asset_columns:
                connection.execute("ALTER TABLE asset_records ADD COLUMN media_metadata_json TEXT")
            api_key_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(api_keys)").fetchall()
            }
            if "deleted_at" not in api_key_columns:
                connection.execute("ALTER TABLE api_keys ADD COLUMN deleted_at TEXT")
            audit_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(admin_audit_logs)").fetchall()
            }
            if "actor_id" not in audit_columns:
                connection.execute("ALTER TABLE admin_audit_logs ADD COLUMN actor_id TEXT")
            if "outcome" not in audit_columns:
                connection.execute(
                    "ALTER TABLE admin_audit_logs ADD COLUMN outcome TEXT NOT NULL DEFAULT 'success'"
                )
            if "user_agent" not in audit_columns:
                connection.execute("ALTER TABLE admin_audit_logs ADD COLUMN user_agent TEXT")
            user_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(admin_users)").fetchall()
            }
            for column, definition in {
                "totp_secret_encrypted": "TEXT",
                "totp_pending_secret_encrypted": "TEXT",
                "totp_pending_session_id": "TEXT",
                "totp_pending_expires_at": "INTEGER",
                "totp_enabled_at": "TEXT",
                "totp_last_timecode": "INTEGER",
            }.items():
                if column not in user_columns:
                    connection.execute(f"ALTER TABLE admin_users ADD COLUMN {column} {definition}")
            session_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(admin_sessions)").fetchall()
            }
            if "mfa_verified" not in session_columns:
                connection.execute(
                    "ALTER TABLE admin_sessions ADD COLUMN mfa_verified INTEGER NOT NULL DEFAULT 0"
                )
            inference_task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(inference_tasks)").fetchall()
            }
            if inference_task_columns and "upstream_model" not in inference_task_columns:
                connection.execute(
                    "ALTER TABLE inference_tasks ADD COLUMN upstream_model TEXT NOT NULL DEFAULT ''"
                )
            provider_channel_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(provider_channels)").fetchall()
            }
            if provider_channel_columns and "deleted_at" not in provider_channel_columns:
                connection.execute("ALTER TABLE provider_channels ADD COLUMN deleted_at TEXT")
            model_catalog_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(model_catalog)").fetchall()
            }
            if model_catalog_columns and "upstream_model" not in model_catalog_columns:
                connection.execute(
                    "ALTER TABLE model_catalog ADD COLUMN upstream_model TEXT NOT NULL DEFAULT ''"
                )
            if inference_task_columns and "billing_metadata_json" not in inference_task_columns:
                connection.execute(
                    "ALTER TABLE inference_tasks ADD COLUMN billing_metadata_json TEXT NOT NULL DEFAULT '{}'"
                )
            billing_item_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(billing_usage_items)").fetchall()
            }
            if billing_item_columns and "late_from_month" not in billing_item_columns:
                connection.execute("ALTER TABLE billing_usage_items ADD COLUMN late_from_month TEXT")
            billing_adjustment_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(billing_adjustments)").fetchall()
            }
            if billing_adjustment_columns and "adjustment_type" not in billing_adjustment_columns:
                connection.execute(
                    "ALTER TABLE billing_adjustments ADD COLUMN adjustment_type TEXT NOT NULL DEFAULT 'manual'"
                )
            if billing_adjustment_columns and "source_item_id" not in billing_adjustment_columns:
                connection.execute("ALTER TABLE billing_adjustments ADD COLUMN source_item_id TEXT")
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_adjustments_source_item "
                    "ON billing_adjustments(source_item_id) WHERE source_item_id IS NOT NULL"
                )
            connection.execute(
                "INSERT OR IGNORE INTO system_monitor_settings(id) VALUES (1)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO system_monitor_state(id) VALUES (1)"
            )
            for alias, display_name, provider, modality, protocol, upstream_model, capabilities in BUILTIN_MODEL_CATALOG:
                connection.execute(
                    "INSERT INTO model_catalog "
                    "(alias,display_name,provider,modality,protocol,upstream_model,capabilities_json) "
                    "VALUES (?,?,?,?,?,?,?) ON CONFLICT(alias) DO UPDATE SET "
                    "display_name=excluded.display_name,provider=excluded.provider,"
                    "modality=excluded.modality,protocol=excluded.protocol,"
                    "upstream_model=excluded.upstream_model,"
                    "capabilities_json=excluded.capabilities_json,updated_at=CURRENT_TIMESTAMP",
                    (
                        alias,
                        display_name,
                        provider,
                        modality,
                        protocol,
                        upstream_model,
                        json.dumps(capabilities, separators=(",", ":")),
                    ),
                )
            # Retired or unavailable models remain in historical task/usage rows,
            # but are hidden from catalogs and cannot receive new traffic.
            connection.execute(
                "UPDATE model_catalog SET enabled=0,updated_at=CURRENT_TIMESTAMP "
                "WHERE alias IN ("
                "'seedance-1.0-lite-t2v','seedance-1.0-lite-i2v',"
                "'seedance-1.5-pro',"
                "'seedream-3.0-t2i','seededit-3.0-i2i',"
                "'doubao-seed-1.8','doubao-seed-1.6-vision'"
                ")"
            )
            # Early local catalogs used two aliases that did not match the fixed
            # upstream IDs. Migrate every reference atomically so existing project
            # bindings, legacy key permissions, tasks and usage remain available.
            for legacy_alias, canonical_alias in (
                ("glm-5.3", "glm-5.2"),
                ("wan3.0", "wan3.0-video"),
            ):
                if not connection.execute(
                    "SELECT 1 FROM model_catalog WHERE alias=?", (legacy_alias,)
                ).fetchone():
                    continue
                connection.execute(
                    "DELETE FROM project_model_bindings WHERE model_alias=? AND EXISTS ("
                    "SELECT 1 FROM project_model_bindings current WHERE current.project_name="
                    "project_model_bindings.project_name AND current.model_alias=?)",
                    (legacy_alias, canonical_alias),
                )
                connection.execute(
                    "DELETE FROM api_key_model_permissions WHERE model_alias=? AND EXISTS ("
                    "SELECT 1 FROM api_key_model_permissions current WHERE current.api_key_id="
                    "api_key_model_permissions.api_key_id AND current.model_alias=?)",
                    (legacy_alias, canonical_alias),
                )
                for table in (
                    "project_model_bindings",
                    "api_key_model_permissions",
                    "inference_tasks",
                    "inference_usage",
                ):
                    connection.execute(
                        f"UPDATE {table} SET model_alias=? WHERE model_alias=?",
                        (canonical_alias, legacy_alias),
                    )
                connection.execute("DELETE FROM model_catalog WHERE alias=?", (legacy_alias,))
            connection.execute("UPDATE api_keys SET status = 'disabled' WHERE status = 'revoked'")
            # A process can stop after reserving quota but before committing or rolling it
            # back. No requests are in flight during startup, so all persisted reservations
            # are orphaned and can be released safely.
            reservations = connection.execute(
                "SELECT scope_type, scope_id, metric, window_start, amount FROM quota_reservations"
            ).fetchall()
            for reservation in reservations:
                connection.execute(
                    "UPDATE quota_usage_windows SET reserved=MAX(0,reserved-?) "
                    "WHERE scope_type=? AND scope_id=? AND metric=? AND window_start=?",
                    (
                        reservation["amount"], reservation["scope_type"], reservation["scope_id"],
                        reservation["metric"], reservation["window_start"],
                    ),
                )
            connection.execute("DELETE FROM quota_reservations")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def write_admin_audit(
        self,
        *,
        actor: str,
        actor_id: str | None,
        source_ip: str | None,
        user_agent: str | None,
        action: str,
        target_type: str,
        target_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        outcome: str = "success",
        connection: sqlite3.Connection | None = None,
    ) -> None:
        parameters = (
            actor,
            actor_id,
            source_ip,
            (user_agent or "")[:512] or None,
            action,
            target_type,
            target_id,
            json.dumps(before, ensure_ascii=False, separators=(",", ":")) if before is not None else None,
            json.dumps(after, ensure_ascii=False, separators=(",", ":")) if after is not None else None,
            outcome,
        )
        sql = (
            "INSERT INTO admin_audit_logs "
            "(actor,actor_id,source_ip,user_agent,action,target_type,target_id,before_json,after_json,outcome) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)"
        )
        if connection is not None:
            connection.execute(sql, parameters)
            return
        with self.connect() as owned_connection:
            owned_connection.execute(sql, parameters)

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT p.name, p.display_name AS displayName, p.description, p.created_at AS createdAt,
                    COUNT(k.id) AS keyCount,
                    SUM(CASE WHEN k.status = 'active' THEN 1 ELSE 0 END) AS activeKeyCount,
                    (SELECT COUNT(*) FROM asset_records a
                     WHERE a.project_name = p.name AND a.status != 'deleted') AS activeAssetCount
                FROM projects p LEFT JOIN api_keys k
                    ON k.project_name = p.name AND k.status != 'deleted'
                GROUP BY p.name ORDER BY p.created_at DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def create_project(self, name: str, display_name: str, description: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO projects (name, display_name, description) VALUES (?, ?, ?)",
                (name, display_name, description),
            )
        return {"name": name, "displayName": display_name, "description": description}

    def resolve_project_name(self, name: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name FROM projects WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
        return row["name"] if row else None

    def delete_project(self, name: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name FROM projects WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            if row is None:
                return None
            canonical_name = row["name"]
            key_count = connection.execute(
                "SELECT COUNT(*) FROM api_keys WHERE project_name = ? AND status != 'deleted'",
                (canonical_name,),
            ).fetchone()[0]
            asset_count = connection.execute(
                "SELECT COUNT(*) FROM asset_records WHERE project_name = ? AND status != 'deleted'",
                (canonical_name,),
            ).fetchone()[0]
            channel_count = connection.execute(
                "SELECT COUNT(*) FROM provider_channels WHERE project_name = ? AND deleted_at IS NULL",
                (canonical_name,),
            ).fetchone()[0]
            billing_count = connection.execute(
                "SELECT COUNT(*) FROM billing_statements WHERE project_name=?",
                (canonical_name,),
            ).fetchone()[0]
            if key_count or asset_count or channel_count or billing_count:
                return {
                    "deleted": False,
                    "projectName": canonical_name,
                    "keyCount": key_count,
                    "assetCount": asset_count,
                    "channelCount": channel_count,
                    "billingCount": billing_count,
                }
            connection.execute(
                "DELETE FROM quota_reservations WHERE scope_type='project' AND scope_id=?",
                (canonical_name,),
            )
            connection.execute(
                "DELETE FROM quota_usage_windows WHERE scope_type='project' AND scope_id=?",
                (canonical_name,),
            )
            # Billing terms are mutable configuration, not invoice history. They
            # must not leave a foreign-key tombstone when a never-billed project
            # is intentionally removed.
            connection.execute(
                "DELETE FROM project_billing_terms WHERE project_name=?", (canonical_name,)
            )
            connection.execute("DELETE FROM projects WHERE name = ?", (canonical_name,))
        return {
            "deleted": True,
            "projectName": canonical_name,
            "keyCount": 0,
            "assetCount": 0,
            "channelCount": 0,
            "billingCount": 0,
        }

    def project_exists(self, name: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM projects WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone() is not None

    def list_api_keys(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT id, name, key_prefix AS keyPrefix, project_name AS projectName, status,
                    created_at AS createdAt, last_used_at AS lastUsedAt
                FROM api_keys WHERE status != 'deleted' ORDER BY created_at DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def create_api_key(self, key_id: str, name: str, prefix: str, key_hash: str, project_name: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO api_keys (id, name, key_prefix, key_hash, project_name) VALUES (?, ?, ?, ?, ?)",
                (key_id, name, prefix, key_hash, project_name),
            )

    def disable_api_key(self, key_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET status = 'disabled' WHERE id = ? AND status = 'active'", (key_id,)
            )
        return cursor.rowcount > 0

    def enable_api_key(self, key_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM api_keys WHERE id = ? AND status != 'deleted'",
                (key_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "disabled":
                return "active"
            connection.execute(
                "UPDATE api_keys SET status = 'active' WHERE id = ?",
                (key_id,),
            )
        return "enabled"

    def delete_api_key(self, key_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM api_keys WHERE id = ? AND status != 'deleted'",
                (key_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "disabled":
                return "active"
            has_inference_history = connection.execute(
                "SELECT EXISTS(SELECT 1 FROM inference_tasks WHERE api_key_id=?) OR "
                "EXISTS(SELECT 1 FROM inference_usage WHERE api_key_id=?) OR "
                "EXISTS(SELECT 1 FROM video_tasks WHERE api_key_id=?) OR "
                "EXISTS(SELECT 1 FROM video_usage WHERE api_key_id=?) OR "
                "EXISTS(SELECT 1 FROM billing_usage_items WHERE api_key_id=?)",
                (key_id, key_id, key_id, key_id, key_id),
            ).fetchone()[0]
            connection.execute(
                "DELETE FROM quota_reservations WHERE scope_type='key' AND scope_id=?", (key_id,)
            )
            connection.execute(
                "DELETE FROM quota_usage_windows WHERE scope_type='key' AND scope_id=?", (key_id,)
            )
            if has_inference_history:
                # Inference tasks and usage intentionally retain their API Key identity
                # for audit and billing, so their foreign keys use ON DELETE RESTRICT.
                # Revoke the credential irreversibly and hide the tombstone instead of
                # deleting history or violating those constraints.
                connection.execute(
                    "UPDATE api_keys SET status='deleted', deleted_at=CURRENT_TIMESTAMP, key_hash=? "
                    "WHERE id=?",
                    (f"deleted:{key_id}", key_id),
                )
                connection.execute(
                    "DELETE FROM api_key_model_permissions WHERE api_key_id = ?", (key_id,)
                )
                connection.execute("DELETE FROM api_key_quotas WHERE api_key_id = ?", (key_id,))
            else:
                connection.execute("DELETE FROM request_logs WHERE api_key_id = ?", (key_id,))
                connection.execute("DELETE FROM video_usage WHERE api_key_id = ?", (key_id,))
                connection.execute("DELETE FROM video_tasks WHERE api_key_id = ?", (key_id,))
                connection.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        return "deleted"

    def bind_api_key_project(self, key_id: str, project_name: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET project_name = ? WHERE id = ? AND status != 'deleted'",
                (project_name, key_id),
            )
        return cursor.rowcount > 0

    def find_api_key(self, key_hash: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, project_name AS projectName FROM api_keys WHERE key_hash = ? AND status = 'active' LIMIT 1",
                (key_hash,),
            ).fetchone()
        return self._dict(row)

    def touch_api_key(self, key_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (key_id,))

    def log_request(self, key_id: str, project_name: str, action: str, status_code: int, duration_ms: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO request_logs (api_key_id, project_name, action, status_code, duration_ms) VALUES (?, ?, ?, ?, ?)",
                (key_id, project_name, action, status_code, duration_ms),
            )

    def create_asset_record(
        self,
        record_id: str,
        project_name: str,
        key_id: str,
        source_type: str,
        source_url: str,
        *,
        bucket: str | None = None,
        object_key: str | None = None,
        size_bytes: int = 0,
        asset_type: str = "Image",
        content_type: str | None = None,
        media_metadata: dict[str, Any] | None = None,
        status: str = "uploaded_pending",
        group_id: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO asset_records "
                "(record_id, project_name, api_key_id, group_id, source_type, source_url, bucket, object_key, "
                "size_bytes, asset_type, content_type, media_metadata_json, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id, project_name, key_id, group_id, source_type, source_url, bucket,
                    object_key, size_bytes, asset_type, content_type,
                    json.dumps(media_metadata, ensure_ascii=False, separators=(",", ":")) if media_metadata else None,
                    status,
                ),
            )
        return self.get_asset_record(record_id) or {}

    def get_asset_record(self, record_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM asset_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        return self._dict(row)

    def find_upload_record(
        self, project_name: str, key_id: str, *, upload_id: str | None = None, source_url: str | None = None,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            if upload_id:
                row = connection.execute(
                    "SELECT * FROM asset_records WHERE record_id=? AND project_name=? AND api_key_id=? "
                    "AND source_type='tos' AND status IN ('uploaded_pending','registration_failed')",
                    (upload_id, project_name, key_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM asset_records WHERE project_name=? AND api_key_id=? AND source_url=? "
                    "AND source_type='tos' AND status IN ('uploaded_pending','registration_failed') "
                    "ORDER BY created_at DESC LIMIT 1",
                    (project_name, key_id, source_url),
                ).fetchone()
        return self._dict(row)

    def update_asset_record(
        self,
        record_id: str,
        status: str,
        *,
        group_id: str | None = None,
        asset_id: str | None = None,
        last_error: str | None = None,
        deleted: bool = False,
        increment_cleanup: bool = False,
    ) -> None:
        assignments = ["status=?", "updated_at=CURRENT_TIMESTAMP", "last_error=?"]
        values: list[Any] = [status, last_error]
        if group_id is not None:
            assignments.append("group_id=?")
            values.append(group_id)
        if asset_id is not None:
            assignments.append("asset_id=?")
            values.append(asset_id)
        if deleted:
            assignments.append("deleted_at=CURRENT_TIMESTAMP")
        if increment_cleanup:
            assignments.append("cleanup_attempts=cleanup_attempts+1")
        values.append(record_id)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE asset_records SET {', '.join(assignments)} WHERE record_id=?", values
            )

    def find_asset_by_asset_id(self, project_name: str, asset_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM asset_records WHERE project_name=? AND asset_id=? AND status!='deleted' LIMIT 1",
                (project_name, asset_id),
            ).fetchone()
        return self._dict(row)

    def cleanup_candidates(self, hours: int = 48, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM asset_records WHERE source_type='tos' AND ("
                "status='cleanup_pending' OR (status IN ('uploaded_pending','registration_failed') "
                "AND created_at <= datetime('now', ?))) ORDER BY updated_at LIMIT ?",
                (f"-{hours} hours", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_cleanup_objects(self, project_name: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT record_id AS recordId, object_key AS objectKey, size_bytes AS sizeBytes, "
                "status, cleanup_attempts AS cleanupAttempts, last_error AS lastError, "
                "created_at AS createdAt, updated_at AS updatedAt "
                "FROM asset_records WHERE project_name=? AND source_type='tos' "
                "AND status IN ('uploaded_pending','registration_failed','cleanup_pending') "
                "ORDER BY updated_at LIMIT ?",
                (project_name, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            stats = connection.execute("""
                SELECT
                    (SELECT COUNT(*) FROM projects) AS projects,
                    (SELECT COUNT(*) FROM api_keys WHERE status = 'active') AS activeKeys,
                    (SELECT COUNT(*) FROM request_logs WHERE created_at >= datetime('now', '-24 hours')) AS requests24h,
                    (SELECT COUNT(*) FROM request_logs WHERE status_code >= 400 AND created_at >= datetime('now', '-24 hours')) AS errors24h,
                    (SELECT COUNT(*) FROM asset_records WHERE status IN ('registering','active') AND date(created_at, '+8 hours')=date('now', '+8 hours')) AS assetsToday,
                    (SELECT COUNT(*) FROM asset_records WHERE source_type='tos' AND date(created_at, '+8 hours')=date('now', '+8 hours')) AS uploadsToday,
                    (SELECT COALESCE(SUM(size_bytes),0) FROM asset_records WHERE source_type='tos' AND date(created_at, '+8 hours')=date('now', '+8 hours')) AS uploadBytesToday,
                    (SELECT COUNT(DISTINCT project_name) FROM project_quotas WHERE enabled=1) AS limitedProjects,
                    (SELECT COUNT(*) FROM quota_events WHERE acknowledged=0) AS openQuotaEvents,
                    (SELECT COUNT(*) FROM asset_records WHERE status='cleanup_pending') AS cleanupPending
            """).fetchone()
            recent = connection.execute("""
                SELECT action, project_name AS projectName, status_code AS statusCode,
                    duration_ms AS durationMs, created_at AS createdAt
                FROM request_logs ORDER BY id DESC LIMIT 8
            """).fetchall()
        return {"stats": dict(stats), "recent": [dict(row) for row in recent]}
