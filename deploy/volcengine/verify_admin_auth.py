"""Non-destructive console authentication smoke test.

Run this against the local console origin or the final HTTPS console origin. The
script creates and revokes only its own login session; it does not change users,
projects, API keys, quotas, or deployment state.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


@dataclass
class Result:
    status: int
    body: dict
    headers: object


def _request(opener, base_url: str, path: str, *, method: str = "GET", body=None, headers=None) -> Result:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["content-type"] = "application/json"
    request = Request(
        urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/")),
        data=payload,
        headers=request_headers,
        method=method,
    )
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error
    raw = response.read()
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssertionError(f"{path} did not return JSON (HTTP {response.status})") from error
    return Result(response.status, parsed, response.headers)


def _assert_status(result: Result, expected: int, label: str) -> None:
    if result.status != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {result.status}: {result.body}")


def _assert_no_store(result: Result, label: str) -> None:
    cache_control = result.headers.get("cache-control", "").lower()
    if "no-store" not in cache_control:
        raise AssertionError(f"{label}: missing Cache-Control: no-store")


def main() -> int:
    parser = argparse.ArgumentParser(description="验证管理员会话、CSRF、角色和同源代理")
    parser.add_argument("--base-url", default="http://127.0.0.1:3001", help="控制台 origin")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--expect-no-store",
        action="store_true",
        help="验证生产控制台网关强制返回 Cache-Control: no-store",
    )
    arguments = parser.parse_args()
    password = os.environ.get("ADMIN_VERIFY_PASSWORD") or getpass.getpass("管理员密码：")

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    checks: list[tuple[str, Result]] = []

    anonymous = _request(opener, arguments.base_url, "/api/internal/auth/me")
    _assert_status(anonymous, 401, "anonymous me")
    checks.append(("anonymous me", anonymous))

    legacy = _request(
        opener,
        arguments.base_url,
        "/api/internal/project/list",
        headers={"X-Admin-Token": "obsolete-shared-token"},
    )
    _assert_status(legacy, 401, "legacy token rejection")
    checks.append(("legacy token rejection", legacy))

    login = _request(
        opener,
        arguments.base_url,
        "/api/internal/auth/login",
        method="POST",
        body={"username": arguments.username, "password": password},
    )
    _assert_status(login, 200, "login")
    checks.append(("login", login))
    user = login.body.get("user") or {}
    csrf_token = login.body.get("csrfToken")
    if user.get("username", "").casefold() != arguments.username.strip().casefold():
        raise AssertionError("login returned a different administrator")
    if user.get("role") not in {"super_admin", "admin"}:
        raise AssertionError("login returned an unknown administrator role")
    if not isinstance(csrf_token, str) or len(csrf_token) < 32:
        raise AssertionError("login did not return a strong CSRF token")

    set_cookies = login.headers.get_all("set-cookie") or []
    session_cookie = next((value for value in set_cookies if value.startswith("avatar_admin_session=")), "")
    csrf_cookie = next((value for value in set_cookies if value.startswith("avatar_admin_csrf=")), "")
    session_lower = session_cookie.lower()
    csrf_lower = csrf_cookie.lower()
    if not session_cookie or "httponly" not in session_lower or "samesite=strict" not in session_lower:
        raise AssertionError("administrator session cookie is missing HttpOnly or SameSite=Strict")
    if "path=/api/internal" not in session_lower:
        raise AssertionError("administrator session cookie has an unexpected Path")
    if not csrf_cookie or "httponly" in csrf_lower or "samesite=strict" not in csrf_lower:
        raise AssertionError("CSRF cookie flags are invalid")
    if urlparse(arguments.base_url).scheme.lower() == "https":
        if "secure" not in session_lower or "secure" not in csrf_lower:
            raise AssertionError("HTTPS console cookies must include Secure")

    me = _request(opener, arguments.base_url, "/api/internal/auth/me")
    _assert_status(me, 200, "authenticated me")
    checks.append(("authenticated me", me))
    if (me.body.get("user") or {}).get("id") != user.get("id"):
        raise AssertionError("authenticated session resolved to a different administrator")

    if user.get("mustChangePassword"):
        logout = _request(
            opener,
            arguments.base_url,
            "/api/internal/auth/logout",
            method="POST",
            headers={"X-CSRF-Token": csrf_token},
        )
        _assert_status(logout, 200, "logout")
        checks.append(("logout", logout))
        if arguments.expect_no_store:
            for label, result in checks:
                _assert_no_store(result, label)
        print("登录与 Cookie 验证通过；该账号仍需先在控制台修改初始密码。")
        return 0

    projects = _request(opener, arguments.base_url, "/api/internal/project/list")
    _assert_status(projects, 200, "business console access")
    checks.append(("business console access", projects))

    users = _request(opener, arguments.base_url, "/api/internal/admin/users")
    expected_users_status = 200 if user.get("role") == "super_admin" else 403
    _assert_status(users, expected_users_status, "role boundary")
    checks.append(("role boundary", users))

    audits = _request(opener, arguments.base_url, "/api/internal/admin/audits")
    _assert_status(audits, expected_users_status, "security audit role boundary")
    checks.append(("security audit role boundary", audits))

    missing_csrf = _request(opener, arguments.base_url, "/api/internal/auth/logout", method="POST")
    _assert_status(missing_csrf, 403, "missing CSRF rejection")
    checks.append(("missing CSRF rejection", missing_csrf))

    logout = _request(
        opener,
        arguments.base_url,
        "/api/internal/auth/logout",
        method="POST",
        headers={"X-CSRF-Token": csrf_token},
    )
    _assert_status(logout, 200, "logout")
    checks.append(("logout", logout))

    revoked = _request(opener, arguments.base_url, "/api/internal/auth/me")
    _assert_status(revoked, 401, "revoked session")
    checks.append(("revoked session", revoked))

    if arguments.expect_no_store:
        for label, result in checks:
            _assert_no_store(result, label)

    print(
        "管理员认证验收通过：同源登录、Cookie、CSRF、角色边界、旧令牌拒绝和会话撤销均正常。"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"验收失败：{error}", file=sys.stderr)
        raise SystemExit(1) from error
