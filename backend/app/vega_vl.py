"""Vega-VL OpenAI Chat contract from the customer integration and price PDFs."""
from __future__ import annotations

import base64
import binascii
import hashlib
import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlsplit

from .errors import ApiError
from .vega import VEGA_FX

VERSION = "2026-10-22"
BASE_URL = "https://mmu.vod-qcloud.com/v1"
MODEL_CATALOG = tuple(
    (f"wand-vega-vl-1.0-{tier}", f"Vega-VL 1.0 {tier.title()}", "vega", "text", "openai_text",
     f"wand-vega-vl-1.0-{tier}", {"chat": True, "responses": False, "stream": True,
         "imageInput": True, "videoInput": True, "audioInput": True, "fileInput": True,
         "textOnly": tier != "pro", "maxVideos": 10, "thinking": True,
         "billingMetric": "input_tokens", "billingUnit": 1_000_000})
    for tier in ("lite", "flash", "pro")
)
MODELS = {row[0]: row for row in MODEL_CATALOG}
RATES = {}
for _tier, _domestic, _international in (
    ("lite", ("0.7", "2.6", "0.14"), ("0.14", "0.45", "0.028")),
    ("flash", ("3", "15", "0.6"), ("0.44", "2.21", "0.088")),
    ("pro", ("8", "40", "1"), ("1.25", "6.25", "0.15")),
):
    RATES[f"wand-vega-vl-1.0-{_tier}"] = tuple(
        (metric, site, 1_000_000, (Decimal(price) * multiplier).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
        for site, prices, multiplier in (("domestic", _domestic, Decimal(1)), ("international", _international, VEGA_FX))
        for metric, price in zip(("input_tokens", "output_tokens", "cached_input_tokens"), prices)
    )

FIELDS = {"model", "messages", "stream", "stream_options", "thinking_enabled", "reasoning_effort",
          "reasoning_split", "temperature", "max_tokens", "max_completion_tokens", "tools",
          "tool_choice", "response_format"}
MAX_MEDIA_BYTES = 100 * 1024 * 1024


def invalid(message: str, code: str = "vega_vl_parameter_invalid") -> None:
    raise ApiError(message, 422, code)


def channel_config(config: dict[str, Any]) -> dict[str, str]:
    if set(config) - {"site"} or config.get("site", "domestic") not in ("domestic", "international"):
        invalid("Vega-VL渠道仅接受国内/国际站site配置", "vega_vl_config_invalid")
    return {"site": config.get("site", "domestic")}


def media_url(value: Any, category: str) -> str:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        invalid("多模态素材地址无效")
    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        parts = header[5:].split(";")
        if (not separator or len(parts) != 2 or parts[1] != "base64" or not encoded
                or "/" not in parts[0] or category != "file" and not parts[0].startswith(category + "/")):
            invalid("多模态Data URL格式无效")
        if len(encoded) > ((MAX_MEDIA_BYTES + 2) // 3) * 4:
            invalid("内联多模态素材超过100 MiB限制")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            invalid("多模态素材Base64无效")
        if not raw or len(raw) > MAX_MEDIA_BYTES:
            invalid("内联多模态素材为空或过大")
        return value
    try:
        url = urlsplit(value)
        if url.scheme in ("https", "http") and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    invalid("多模态素材须为HTTP(S) URL或Data URL")


def validate_payload(payload: dict[str, Any], *, pro: bool) -> dict[str, Any]:
    unknown = set(payload) - FIELDS
    if unknown:
        invalid("Vega-VL不支持这些字段：" + ",".join(sorted(unknown)), "text_parameter_unsupported")
    for name in ("stream", "thinking_enabled", "reasoning_split"):
        if name in payload and type(payload[name]) is not bool:
            invalid(name + "必须为布尔值")
    if "stream_options" in payload:
        options = payload["stream_options"]
        if (not isinstance(options, dict) or set(options) - {"include_usage"}
                or "include_usage" in options and type(options["include_usage"]) is not bool):
            invalid("stream_options仅接受布尔值include_usage")
    if "reasoning_effort" in payload and payload["reasoning_effort"] not in ("none", "minimal", "low", "medium", "high", "xhigh"):
        invalid("reasoning_effort取值无效")
    if "temperature" in payload:
        value = payload["temperature"]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 2:
            invalid("temperature须为0到2的数字")
    for name in ("max_tokens", "max_completion_tokens"):
        if name in payload and (type(payload[name]) is not int or payload[name] <= 0):
            invalid(name + "须为正整数")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        invalid("messages须为非空数组")
    videos = 0
    media = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("system", "developer", "user", "assistant", "tool"):
            invalid("消息role无效")
        if set(message) - {"role", "content", "tool_calls", "tool_call_id", "name"}:
            invalid("消息包含不支持的字段")
        content = message.get("content")
        if content is None and message["role"] == "assistant" and isinstance(message.get("tool_calls"), list):
            continue
        if isinstance(content, str):
            continue
        if not isinstance(content, list) or not content:
            invalid("消息content须为字符串或非空Part数组")
        for part in content:
            if not isinstance(part, dict):
                invalid("多模态Part须为对象")
            kind = part.get("type")
            if kind == "text":
                if set(part) != {"type", "text"} or not isinstance(part["text"], str):
                    invalid("text Part格式无效")
                continue
            if kind not in ("image_url", "video_url", "input_audio", "file") or set(part) != {"type", kind}:
                invalid("Part类型或字段无效；文件字段须放入file对象")
            source = part[kind]
            if not isinstance(source, dict):
                invalid("多模态素材参数须为对象")
            media += 1
            if kind in ("image_url", "video_url"):
                if set(source) - ({"url", "detail"} if kind == "image_url" else {"url"}):
                    invalid("图片/视频Part包含不支持的字段")
                if kind == "image_url" and source.get("detail", "auto") not in ("auto", "low", "high"):
                    invalid("image_url.detail无效")
                media_url(source.get("url"), "image" if kind == "image_url" else "video")
                videos += int(kind == "video_url")
            elif kind == "input_audio":
                if set(source) == {"url"}:
                    media_url(source["url"], "audio")
                elif (set(source) == {"data", "format"} and source["format"] in ("mp3", "wav")
                      and isinstance(source["data"], str)):
                    media_url(f"data:audio/{source['format']};base64,{source['data']}", "audio")
                else:
                    invalid("音频须为url或Base64 data与mp3/wav format")
            elif set(source) == {"file_url"}:
                media_url(source["file_url"], "file")
                if source["file_url"].startswith("data:"):
                    invalid("内联文件须使用file_data与file_name")
            elif set(source) == {"file_data", "file_name"} and isinstance(source["file_name"], str) and source["file_name"]:
                if not isinstance(source["file_data"], str) or not source["file_data"].startswith("data:"):
                    invalid("file_data须为Data URL")
                media_url(source["file_data"], "file")
            else:
                invalid("file须提供file_url或file_data与file_name")
    if videos > 10:
        invalid("Vega-VL单次最多输入10个视频")
    if pro and not media:
        invalid("Vega-VL Pro需要图片、音频、视频或文件输入，不支持纯文本", "model_media_input_required")
    return dict(payload)


def session_header(principal: Any, value: str | None) -> dict[str, str]:
    if value is None:
        return {}
    if not value or len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        invalid("Tx-User-Session-Id长度或字符无效")
    # Scope cache/session affinity to the business Key; equal customer strings
    # must never accidentally share the supplier's session identity.
    scoped = f"{principal.project_name}:{principal.id}:{value}".encode()
    return {"Tx-User-Session-Id": hashlib.sha256(scoped).hexdigest()}


def normalized_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {k: v for k, v in value.items() if k in ("prompt_tokens", "completion_tokens", "total_tokens") and type(v) is int and v >= 0}
    details = value.get("prompt_tokens_details")
    if isinstance(details, dict):
        counts = [details[k] for k in ("cached_tokens", "cache_read_tokens") if type(details.get(k)) is int and details[k] >= 0]
        if counts:
            result["prompt_tokens_details"] = {"cached_tokens": max(counts)}
    return result


def measurements(row: dict[str, Any]):
    site = row.get("usage_dimension")
    if site not in ("domestic", "international"):
        return None, "usage_dimension_unknown"
    values = [row.get(k) for k in ("input_tokens", "output_tokens", "cached_input_tokens")]
    if any(type(v) is not int or v < 0 for v in values):
        return None, "usage_unknown"
    inputs, outputs, cached = values
    if cached > inputs:
        return None, "usage_invalid"
    return [("input_tokens", site, Decimal(inputs - cached)), ("output_tokens", site, Decimal(outputs)),
            ("cached_input_tokens", site, Decimal(cached))], None
