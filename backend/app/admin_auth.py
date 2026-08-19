import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from .config import Settings
from .database import Database
from .errors import ApiError


@dataclass(frozen=True)
class AdminPrincipal:
    id: str
    username: str
    display_name: str
    role: str
    session_id: str
    csrf_token: str
    must_change_password: bool


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_username(value: str) -> str:
    return value.strip().lower()


class AdminAuthService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.time,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        self.password_hasher = password_hasher or PasswordHasher(
            time_cost=settings.admin_argon2_time_cost,
            memory_cost=settings.admin_argon2_memory_cost,
            parallelism=settings.admin_argon2_parallelism,
        )
        self._dummy_hash = self.password_hasher.hash(secrets.token_urlsafe(24))

    @staticmethod
    def generate_initial_password() -> str:
        return secrets.token_urlsafe(18)

    @staticmethod
    def validate_password(password: str, username: str) -> None:
        if len(password) < 14 or len(password) > 128:
            raise ApiError("密码长度必须为 14 到 128 个字符", 422, "invalid_admin_password")
        if password.casefold() == username.casefold():
            raise ApiError("密码不能与用户名相同", 422, "invalid_admin_password")

    @staticmethod
    def _user_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "displayName": row["display_name"],
            "role": row["role"],
            "status": row["status"],
            "mustChangePassword": bool(row["must_change_password"]),
            "failedAttempts": int(row["failed_attempts"]),
            "lockedUntil": row["locked_until"],
            "lastLoginAt": row["last_login_at"],
            "lastLoginIp": row["last_login_ip"],
            "passwordChangedAt": row["password_changed_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _session_payload(row: sqlite3.Row | dict[str, Any], current_id: str | None = None) -> dict[str, Any]:
        return {
            "id": row["id"],
            "current": row["id"] == current_id,
            "createdAt": int(row["created_at"]),
            "lastSeenAt": int(row["last_seen_at"]),
            "absoluteExpiresAt": int(row["absolute_expires_at"]),
            "sourceIp": row["source_ip"],
            "userAgent": row["user_agent"],
        }

    def _audit(
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
        self.database.write_admin_audit(
            actor=actor,
            actor_id=actor_id,
            source_ip=source_ip,
            user_agent=user_agent,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            outcome=outcome,
            connection=connection,
        )

    def create_initial_super_admin(
        self,
        username: str,
        display_name: str,
        *,
        password: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        normalized = _normalize_username(username)
        initial_password = password or self.generate_initial_password()
        self.validate_password(initial_password, normalized)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone() is not None:
                raise ApiError("初始超级管理员已经存在", 409, "initial_admin_exists")
            user_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO admin_users "
                "(id,username,username_normalized,display_name,password_hash,role,must_change_password) "
                "VALUES (?,?,?,?,?,'super_admin',1)",
                (user_id, username.strip(), normalized, display_name.strip(), self.password_hasher.hash(initial_password)),
            )
            row = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
            self._audit(
                actor="admin-cli",
                actor_id=None,
                source_ip=None,
                user_agent="admin-cli",
                action="admin.user.bootstrap",
                target_type="admin_user",
                target_id=user_id,
                after={"username": row["username"], "role": "super_admin"},
                connection=connection,
            )
        return self._user_payload(row), initial_password

    def create_admin(
        self,
        actor: AdminPrincipal,
        username: str,
        display_name: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> tuple[dict[str, Any], str]:
        self.require_super_admin(actor)
        normalized = _normalize_username(username)
        initial_password = self.generate_initial_password()
        self.validate_password(initial_password, normalized)
        user_id = str(uuid.uuid4())
        try:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO admin_users "
                    "(id,username,username_normalized,display_name,password_hash,role,must_change_password,created_by_id) "
                    "VALUES (?,?,?,?,?,'admin',1,?)",
                    (
                        user_id,
                        username.strip(),
                        normalized,
                        display_name.strip(),
                        self.password_hasher.hash(initial_password),
                        actor.id,
                    ),
                )
                row = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
                self._audit(
                    actor=actor.username,
                    actor_id=actor.id,
                    source_ip=source_ip,
                    user_agent=user_agent,
                    action="admin.user.create",
                    target_type="admin_user",
                    target_id=user_id,
                    after={"username": row["username"], "role": "admin", "status": "active"},
                    connection=connection,
                )
        except sqlite3.IntegrityError as error:
            raise ApiError("管理员用户名已存在", 409, "admin_username_exists") from error
        return self._user_payload(row), initial_password

    def _locked_retry_after(self, locked_until: int | None, now: int) -> int:
        return max(1, int(locked_until or now) - now)

    def _raise_locked(self, locked_until: int | None, now: int) -> None:
        retry = self._locked_retry_after(locked_until, now)
        raise ApiError(
            "登录失败次数过多，请稍后再试",
            429,
            "admin_login_locked",
            details={"lockedUntil": locked_until},
            headers={"Retry-After": str(retry)},
        )

    def _record_login_failure(
        self,
        user_id: str | None,
        attempted_username: str,
        source_ip: str | None,
        user_agent: str | None,
        now: int,
    ) -> None:
        locked_until: int | None = None
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone() if user_id else None
            if row is not None:
                window_started = row["failure_window_started_at"]
                if window_started is None or now - int(window_started) >= self.settings.admin_login_window_seconds:
                    failures = 1
                    window_started = now
                else:
                    failures = int(row["failed_attempts"]) + 1
                if failures >= self.settings.admin_login_max_failures:
                    locked_until = now + self.settings.admin_login_lock_seconds
                connection.execute(
                    "UPDATE admin_users SET failed_attempts=?,failure_window_started_at=?,locked_until=?,"
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (failures, window_started, locked_until, user_id),
                )
            self._audit(
                actor=attempted_username,
                actor_id=user_id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.auth.login",
                target_type="admin_user",
                target_id=user_id or attempted_username,
                after={"result": "locked" if locked_until else "failed"},
                outcome="failure",
                connection=connection,
            )
        if locked_until:
            self._raise_locked(locked_until, now)
        raise ApiError("用户名或密码错误", 401, "invalid_admin_credentials")

    def login(
        self,
        username: str,
        password: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        now = int(self.clock())
        normalized = _normalize_username(username)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM admin_users WHERE username_normalized=?", (normalized,)
            ).fetchone()
        if row is not None and row["locked_until"] is not None and int(row["locked_until"]) > now:
            self._raise_locked(int(row["locked_until"]), now)
        candidate_hash = row["password_hash"] if row is not None else self._dummy_hash
        try:
            valid = self.password_hasher.verify(candidate_hash, password)
        except (VerifyMismatchError, VerificationError):
            valid = False
        if row is None or not valid:
            self._record_login_failure(
                row["id"] if row is not None else None,
                username.strip(),
                source_ip,
                user_agent,
                now,
            )
        if row["status"] != "active":
            with self.database.connect() as connection:
                self._audit(
                    actor=row["username"],
                    actor_id=row["id"],
                    source_ip=source_ip,
                    user_agent=user_agent,
                    action="admin.auth.login",
                    target_type="admin_user",
                    target_id=row["id"],
                    after={"result": "disabled"},
                    outcome="failure",
                    connection=connection,
                )
            raise ApiError(
                "管理员账号已禁用，请联系超级管理员",
                403,
                "admin_user_disabled",
            )
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        session_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT * FROM admin_users WHERE id=?", (row["id"],)).fetchone()
            if current["status"] != "active":
                raise ApiError(
                    "管理员账号已禁用，请联系超级管理员",
                    403,
                    "admin_user_disabled",
                )
            if current["locked_until"] is not None and int(current["locked_until"]) > now:
                self._raise_locked(int(current["locked_until"]), now)
            password_hash = current["password_hash"]
            if self.password_hasher.check_needs_rehash(password_hash):
                password_hash = self.password_hasher.hash(password)
            connection.execute(
                "UPDATE admin_users SET password_hash=?,failed_attempts=0,failure_window_started_at=NULL,"
                "locked_until=NULL,last_login_at=CURRENT_TIMESTAMP,last_login_ip=?,updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (password_hash, source_ip, current["id"]),
            )
            connection.execute(
                "INSERT INTO admin_sessions "
                "(id,admin_user_id,token_hash,csrf_hash,created_at,last_seen_at,absolute_expires_at,source_ip,user_agent) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    current["id"],
                    _sha256(token),
                    _sha256(csrf_token),
                    now,
                    now,
                    now + self.settings.admin_session_absolute_seconds,
                    source_ip,
                    (user_agent or "")[:512] or None,
                ),
            )
            self._audit(
                actor=current["username"],
                actor_id=current["id"],
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.auth.login",
                target_type="admin_session",
                target_id=session_id,
                after={"result": "success"},
                connection=connection,
            )
            updated = connection.execute("SELECT * FROM admin_users WHERE id=?", (current["id"],)).fetchone()
            session = connection.execute("SELECT * FROM admin_sessions WHERE id=?", (session_id,)).fetchone()
        return self._user_payload(updated), self._session_payload(session, session_id), token, csrf_token

    def authenticate_session(
        self,
        token: str | None,
        csrf_cookie: str | None,
        csrf_header: str | None,
        *,
        require_csrf: bool,
    ) -> AdminPrincipal:
        if not token:
            raise ApiError("请先登录控制台", 401, "admin_session_required")
        now = int(self.clock())
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT s.*,u.username,u.display_name,u.role,u.status,u.must_change_password "
                "FROM admin_sessions s JOIN admin_users u ON u.id=s.admin_user_id "
                "WHERE s.token_hash=?",
                (_sha256(token),),
            ).fetchone()
            if row is None or row["revoked_at"] is not None:
                raise ApiError("控制台会话无效", 401, "invalid_admin_session")
            if row["status"] != "active":
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='user_disabled' WHERE id=?",
                    (now, row["id"]),
                )
                raise ApiError("管理员账号已禁用", 401, "admin_user_disabled")
            if now >= int(row["absolute_expires_at"]) or now - int(row["last_seen_at"]) >= self.settings.admin_session_idle_seconds:
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='expired' WHERE id=?",
                    (now, row["id"]),
                )
                raise ApiError("控制台会话已过期", 401, "admin_session_expired")
            if not csrf_cookie or not hmac.compare_digest(_sha256(csrf_cookie), row["csrf_hash"]):
                raise ApiError("CSRF 令牌无效", 403, "invalid_csrf_token")
            if require_csrf and (not csrf_header or not hmac.compare_digest(csrf_header, csrf_cookie)):
                raise ApiError("CSRF 令牌无效", 403, "invalid_csrf_token")
            connection.execute("UPDATE admin_sessions SET last_seen_at=? WHERE id=?", (now, row["id"]))
        return AdminPrincipal(
            id=row["admin_user_id"],
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            session_id=row["id"],
            csrf_token=csrf_cookie,
            must_change_password=bool(row["must_change_password"]),
        )

    @staticmethod
    def principal_payload(principal: AdminPrincipal) -> dict[str, Any]:
        return {
            "id": principal.id,
            "username": principal.username,
            "displayName": principal.display_name,
            "role": principal.role,
            "status": "active",
            "mustChangePassword": principal.must_change_password,
        }

    @staticmethod
    def require_super_admin(principal: AdminPrincipal) -> None:
        if principal.role != "super_admin":
            raise ApiError("只有超级管理员可以管理管理员账号", 403, "super_admin_required")

    def list_users(self, actor: AdminPrincipal) -> list[dict[str, Any]]:
        self.require_super_admin(actor)
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM admin_users ORDER BY created_at,id").fetchall()
        return [self._user_payload(row) for row in rows]

    def list_audits(self, actor: AdminPrincipal, limit: int = 100) -> list[dict[str, Any]]:
        self.require_super_admin(actor)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id,actor,actor_id AS actorId,source_ip AS sourceIp,user_agent AS userAgent,"
                "action,target_type AS targetType,target_id AS targetId,before_json AS beforeJson,"
                "after_json AS afterJson,outcome,created_at AS createdAt "
                "FROM admin_audit_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_user_enabled(
        self,
        actor: AdminPrincipal,
        user_id: str,
        *,
        enabled: bool,
        source_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        self.require_super_admin(actor)
        if not enabled and actor.id == user_id:
            raise ApiError("不能禁用当前登录账号", 409, "cannot_disable_self")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise ApiError("管理员不存在", 404, "admin_user_not_found")
            if row["role"] == "super_admin" and not enabled:
                raise ApiError("不能禁用唯一的超级管理员", 409, "last_super_admin_protected")
            target_status = "active" if enabled else "disabled"
            connection.execute(
                "UPDATE admin_users SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (target_status, user_id),
            )
            if not enabled:
                now = int(self.clock())
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='user_disabled' "
                    "WHERE admin_user_id=? AND revoked_at IS NULL",
                    (now, user_id),
                )
            updated = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
            self._audit(
                actor=actor.username,
                actor_id=actor.id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.user.enable" if enabled else "admin.user.disable",
                target_type="admin_user",
                target_id=user_id,
                before={"status": row["status"]},
                after={"status": target_status},
                connection=connection,
            )
        return self._user_payload(updated)

    def reset_password(
        self,
        actor: AdminPrincipal,
        user_id: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> tuple[dict[str, Any], str]:
        self.require_super_admin(actor)
        if actor.id == user_id:
            raise ApiError(
                "超级管理员不能通过管理接口重置自身密码，请使用修改密码或服务器 CLI",
                409,
                "cannot_reset_self",
            )
        initial_password = self.generate_initial_password()
        now = int(self.clock())
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise ApiError("管理员不存在", 404, "admin_user_not_found")
            self.validate_password(initial_password, row["username"])
            connection.execute(
                "UPDATE admin_users SET password_hash=?,must_change_password=1,failed_attempts=0,"
                "failure_window_started_at=NULL,locked_until=NULL,password_changed_at=CURRENT_TIMESTAMP,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (self.password_hasher.hash(initial_password), user_id),
            )
            connection.execute(
                "UPDATE admin_sessions SET revoked_at=?,revoke_reason='password_reset' "
                "WHERE admin_user_id=? AND revoked_at IS NULL",
                (now, user_id),
            )
            updated = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
            self._audit(
                actor=actor.username,
                actor_id=actor.id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.user.reset_password",
                target_type="admin_user",
                target_id=user_id,
                after={"mustChangePassword": True},
                connection=connection,
            )
        return self._user_payload(updated), initial_password

    def delete_admin(
        self,
        actor: AdminPrincipal,
        user_id: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        self.require_super_admin(actor)
        if actor.id == user_id:
            raise ApiError("不能删除当前登录账号", 409, "cannot_delete_self")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM admin_users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise ApiError("管理员不存在", 404, "admin_user_not_found")
            if row["role"] == "super_admin":
                raise ApiError("不能删除唯一的超级管理员", 409, "last_super_admin_protected")
            if row["status"] != "disabled":
                raise ApiError(
                    "请先禁用管理员账号，再执行删除",
                    409,
                    "admin_user_must_be_disabled",
                )
            deleted = self._user_payload(row)
            connection.execute("DELETE FROM admin_users WHERE id=?", (user_id,))
            self._audit(
                actor=actor.username,
                actor_id=actor.id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.user.delete",
                target_type="admin_user",
                target_id=user_id,
                before={
                    "username": row["username"],
                    "role": row["role"],
                    "status": row["status"],
                },
                after={"deleted": True},
                connection=connection,
            )
        return deleted

    def reset_password_from_cli(self, username: str) -> tuple[dict[str, Any], str]:
        normalized = _normalize_username(username)
        initial_password = self.generate_initial_password()
        now = int(self.clock())
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM admin_users WHERE username_normalized=?", (normalized,)
            ).fetchone()
            if row is None:
                raise ApiError("管理员不存在", 404, "admin_user_not_found")
            self.validate_password(initial_password, row["username"])
            connection.execute(
                "UPDATE admin_users SET password_hash=?,must_change_password=1,failed_attempts=0,"
                "failure_window_started_at=NULL,locked_until=NULL,password_changed_at=CURRENT_TIMESTAMP,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (self.password_hasher.hash(initial_password), row["id"]),
            )
            connection.execute(
                "UPDATE admin_sessions SET revoked_at=?,revoke_reason='password_reset_cli' "
                "WHERE admin_user_id=? AND revoked_at IS NULL",
                (now, row["id"]),
            )
            updated = connection.execute("SELECT * FROM admin_users WHERE id=?", (row["id"],)).fetchone()
            self._audit(
                actor="admin-cli",
                actor_id=None,
                source_ip=None,
                user_agent="admin-cli",
                action="admin.user.reset_password",
                target_type="admin_user",
                target_id=row["id"],
                after={"mustChangePassword": True},
                connection=connection,
            )
        return self._user_payload(updated), initial_password

    def change_password(
        self,
        actor: AdminPrincipal,
        current_password: str,
        new_password: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self.validate_password(new_password, actor.username)
        now = int(self.clock())
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM admin_users WHERE id=?", (actor.id,)).fetchone()
        try:
            self.password_hasher.verify(row["password_hash"], current_password)
        except (VerifyMismatchError, VerificationError) as error:
            raise ApiError("当前密码错误", 401, "invalid_current_password") from error
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE admin_users SET password_hash=?,must_change_password=0,password_changed_at=CURRENT_TIMESTAMP,"
                "failed_attempts=0,failure_window_started_at=NULL,locked_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (self.password_hasher.hash(new_password), actor.id),
            )
            connection.execute(
                "UPDATE admin_sessions SET revoked_at=?,revoke_reason='password_changed' "
                "WHERE admin_user_id=? AND revoked_at IS NULL",
                (now, actor.id),
            )
            self._audit(
                actor=actor.username,
                actor_id=actor.id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.auth.change_password",
                target_type="admin_user",
                target_id=actor.id,
                after={"mustChangePassword": False},
                connection=connection,
            )

    def logout(self, actor: AdminPrincipal, source_ip: str | None, user_agent: str | None) -> None:
        now = int(self.clock())
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE admin_sessions SET revoked_at=?,revoke_reason='logout' WHERE id=? AND revoked_at IS NULL",
                (now, actor.session_id),
            )
            self._audit(
                actor=actor.username,
                actor_id=actor.id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.auth.logout",
                target_type="admin_session",
                target_id=actor.session_id,
                connection=connection,
            )

    def list_sessions(self, actor: AdminPrincipal) -> list[dict[str, Any]]:
        now = int(self.clock())
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM admin_sessions WHERE admin_user_id=? AND revoked_at IS NULL "
                "AND absolute_expires_at>? ORDER BY created_at DESC",
                (actor.id, now),
            ).fetchall()
        return [self._session_payload(row, actor.session_id) for row in rows]

    def revoke_session(
        self,
        actor: AdminPrincipal,
        session_id: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> bool:
        now = int(self.clock())
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE admin_sessions SET revoked_at=?,revoke_reason='manual' "
                "WHERE id=? AND admin_user_id=? AND revoked_at IS NULL",
                (now, session_id, actor.id),
            )
            if cursor.rowcount == 0:
                raise ApiError("会话不存在或已撤销", 404, "admin_session_not_found")
            self._audit(
                actor=actor.username,
                actor_id=actor.id,
                source_ip=source_ip,
                user_agent=user_agent,
                action="admin.auth.revoke_session",
                target_type="admin_session",
                target_id=session_id,
                connection=connection,
            )
        return session_id == actor.session_id
