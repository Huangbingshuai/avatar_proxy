#!/usr/bin/env python3
"""Verify the public Star Proxy ingress for LocalMiniDrama WeChat callbacks."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CALLBACK_PATH = "/minidrama/payments/callbacks/wechat"


def request(url: str, *, method: str, body: bytes | None = None) -> tuple[int, bytes, str]:
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type", "")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that the public callback bypasses login and reaches WeChat signature verification."
    )
    parser.add_argument("--base-url", default="https://api.richbest.cn")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        health_status, _, _ = request(f"{base_url}/health", method="GET")
        get_status, _, _ = request(f"{base_url}{CALLBACK_PATH}", method="GET")
        post_status, post_body, content_type = request(
            f"{base_url}{CALLBACK_PATH}", method="POST", body=b"{}"
        )
    except URLError as error:
        fail(f"gateway is unreachable ({type(error.reason).__name__})")

    if health_status != 200:
        fail(f"health endpoint returned HTTP {health_status}, expected 200")
    if get_status != 405:
        fail(f"callback GET returned HTTP {get_status}, expected 405")
    if post_status != 401:
        fail(f"unsigned callback returned HTTP {post_status}, expected 401")
    if "json" not in content_type.lower():
        fail("unsigned callback did not return JSON; login or Basic Auth may still intercept it")

    try:
        payload = json.loads(post_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("unsigned callback returned invalid JSON")

    if not isinstance(payload, dict) or payload.get("code") != "INVALID_SIGNATURE":
        fail("unsigned callback did not reach WeChat signature verification (expected INVALID_SIGNATURE)")
    if payload.get("message") != "微信支付通知验签失败":
        fail("unsigned callback returned an unexpected signature failure message")

    print("PASS: gateway health, POST-only routing, and signature-verification handoff are valid")


if __name__ == "__main__":
    main()
