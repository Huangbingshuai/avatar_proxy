"""Vega image payloads and real-output billing; uses the shared Vega channel."""
from __future__ import annotations

import base64
import binascii
import io
import json
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from PIL import Image

from .errors import ApiError

VERSION = "2026-10-22"
MODEL_CATALOG = tuple(
    (f"vega-image-1.0-{tier}", f"Vega-Image 1.0 {tier.title()}", "vega", "image", "async_image", f"1.0-{tier}",
     {"generations": True, "imageInput": True, "maxInputImages": 3 if tier == "lite" else 6,
      "maxInputImageBytes": 10 * 1024 * 1024, "maxInlineImageBytes": 7 * 1024 * 1024,
      "maxN": 1 if tier == "lite" else 4, "maxPromptCharacters": 2000,
      "sizes": ["1K", "2K", "4K"], "asyncTasks": True, "billingMetric": "image", "billingUnit": 1,
      "inputFreeCount": 3 if tier == "pro" else None})
    for tier in ("lite", "flash", "pro")
)
MODELS = {row[0]: row for row in MODEL_CATALOG}
RATES = {
    f"vega-image-1.0-{tier}": (("image", "domestic:output", 1, Decimal(price)),
        ("image", "domestic:input:after_three", 1, Decimal("0.1" if tier == "pro" else "0")))
    for tier, price in (("lite", ".162"), ("flash", ".45"), ("pro", ".95"))
}
# The supplied image PDFs contain no international output prices. Those rates
# remain unconfigured rather than converting domestic prices into invented USD.
RATE_DIMENSIONS = ("domestic:output", "domestic:input:after_three", "international:output", "international:input:after_three")
PRESETS = {
    "1:1": (("1024x1024", "1080x1080"), ("2048x2048", "2160x2160"), ("4096x4096",)),
    "2:3": (("1024x1536", "1080x1620"), ("1440x2160",), ("3328x4992",)),
    "3:2": (("1536x1024", "1620x1080"), ("2160x1440",), ("4992x3328",)),
    "3:4": (("1080x1440",), ("1440x1920", "2160x2880"), ("3584x4800",)),
    "4:3": (("1440x1080",), ("1920x1440", "2880x2160"), ("4800x3584",)),
    "9:16": (("720x1280", "1080x1920"), ("1440x2560",), ("2160x3840",)),
    "16:9": (("1280x720", "1920x1080"), ("2560x1440",), ("3840x2160",)),
    "21:9": (("1512x648",), ("2520x1080",), ("5040x2160",)),
}


def invalid(message: str, code: str = "vega_image_parameter_invalid") -> None:
    raise ApiError(message, 422, code)


def output_size(size: Any, ratio: Any = None) -> tuple[str, str]:
    if not isinstance(size, str):
        invalid("size须为1K、2K、4K或文档中的像素预设")
    if ratio is not None and (not isinstance(ratio, str) or ratio not in PRESETS):
        invalid("aspect_ratio无效")
    if size.upper() in ("1K", "2K", "4K", "1080P"):
        return size.upper(), ratio or "1:1"
    for preset_ratio, tiers in PRESETS.items():
        for index, values in enumerate(tiers):
            if size.lower() in values:
                if ratio is not None and ratio != preset_ratio:
                    invalid("size像素预设与aspect_ratio不一致")
                return ("1K", "2K", "4K")[index], preset_ratio
    invalid("size不属于Vega-Image支持的像素预设")


def input_file(value: Any) -> tuple[dict[str, str], int]:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        invalid("参考图片地址无效", "image_input_invalid")
    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        mime = header.split(";")[0][5:]
        if not separator or header != f"data:{mime};base64" or mime not in ("image/jpeg", "image/png", "image/webp"):
            invalid("参考图Data URL须为JPEG、PNG或WebP Base64", "image_input_invalid")
        limit = 7 * 1024 * 1024
        if len(encoded) > ((limit + 2) // 3) * 4:
            invalid("内联图片总大小不能超过7 MiB", "image_input_too_large")
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                expected = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime]
                if image.format != expected:
                    invalid("参考图真实格式与Data URL不一致", "image_input_invalid")
                image.verify()
        except (ValueError, OSError, binascii.Error, Image.DecompressionBombError):
            invalid("参考图片Base64或真实媒体内容无效", "image_input_invalid")
        if not raw or len(raw) > limit:
            invalid("内联图片为空或大于7 MiB", "image_input_too_large")
        return {"Type": "Base64", "Base64": encoded}, len(raw)
    try:
        url = urlsplit(value)
        if url.scheme in ("https", "http") and url.hostname and not url.username and not url.password:
            return {"Type": "Url", "Url": value}, 0
    except ValueError:
        pass
    invalid("参考图须为HTTP(S) URL或图片Data URL", "image_input_invalid")


def submit_payload(route: Any, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"model", "prompt", "image", "n", "size", "aspect_ratio", "response_format", "watermark", "stream"}
    if set(payload) - allowed:
        invalid("Vega-Image请求包含不支持的字段", "image_parameter_unsupported")
    if payload.get("stream", False) is not False:
        invalid("Vega-Image不支持图片流式返回", "image_stream_unsupported")
    if payload.get("response_format", "url") != "url":
        invalid("Vega-Image返回临时图片URL，仅支持response_format=url", "image_response_format_invalid")
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str) or len(prompt) > 2000:
        invalid("Vega-Image提示词最多2000字符", "image_prompt_invalid")
    sources = payload.get("image", [])
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, list) or len(sources) > route.capabilities["maxInputImages"]:
        invalid("参考图片数量超过当前模型上限", "image_input_count_invalid")
    files, inline_bytes = [], 0
    for source in sources:
        item, count = input_file(source)
        files.append(item)
        inline_bytes += count
    if inline_bytes > 7 * 1024 * 1024:
        invalid("所有内联参考图总大小不能超过7 MiB", "image_input_too_large")
    if not prompt.strip() and not files:
        invalid("至少提供提示词或参考图片", "image_prompt_invalid")
    count = payload.get("n", 1)
    if type(count) is not int or not 1 <= count <= route.capabilities["maxN"]:
        invalid("生成张数超过当前模型或系统上限", "image_count_unsupported")
    resolution, ratio = output_size(payload.get("size", "1K"), payload.get("aspect_ratio"))
    output = {"StorageMode": "Temporary", "Resolution": resolution, "AspectRatio": ratio}
    if route.upstream_model != "1.0-lite":
        output["OutputImageCount"] = count
    if "watermark" in payload:
        if type(payload["watermark"]) is not bool:
            invalid("watermark须为布尔值")
        output["LogoAdd"] = "Enabled" if payload["watermark"] else "Disabled"
    return {"ModelName": "wand-vega-image", "ModelVersion": route.upstream_model, "Prompt": prompt,
            "FileInfos": files, "OutputConfig": output,
            "InputRegion": "Mainland" if route.channel_config["site"] == "domestic" else "Oversea"}


def task_result(data: dict[str, Any]) -> dict[str, Any]:
    task = data.get("AigcImageTask")
    if not isinstance(task, dict):
        raise ApiError("Vega未返回生图任务详情", 502, "provider_response_invalid")
    if task.get("Status", data.get("Status")) != "FINISH":
        return {"status": "running", "data": [], "progress": task.get("Progress", 0)}
    if type(task.get("ErrCode")) is not int or task["ErrCode"] != 0 or task.get("ErrCodeExt"):
        return {"status": "failed", "data": [], "error_code": str(task.get("ErrCodeExt") or "provider_task_failed"),
                "error": str(task.get("Message") or "Vega生图任务失败")[:500]}
    output = task.get("Output")
    files = output.get("FileInfos") if isinstance(output, dict) else None
    if not isinstance(files, list) or not files:
        raise ApiError("Vega生图任务完成但缺少输出图片", 502, "provider_response_invalid")
    images = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("FileUrl"), str):
            raise ApiError("Vega返回了无效图片结果", 502, "provider_response_invalid")
        try:
            url = urlsplit(item["FileUrl"])
            if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
                raise ValueError()
        except ValueError as error:
            raise ApiError("Vega返回了无效图片地址", 502, "provider_response_invalid") from error
        image = {"url": item["FileUrl"]}
        if isinstance(item.get("ExpireTime"), str):
            image["expires_at"] = item["ExpireTime"]
        meta = item.get("MetaData")
        if isinstance(meta, dict) and all(type(meta.get(k)) is int and meta[k] > 0 for k in ("Width", "Height")):
            image["size"] = f"{meta['Width']}x{meta['Height']}"
        images.append(image)
    confirmed = task.get("Input")
    inputs = confirmed.get("FileInfos") if isinstance(confirmed, dict) else None
    return {"status": "succeeded", "data": images, "progress": 100,
            "input_count": len(inputs) if isinstance(inputs, list) else None}


def measurements(row: dict[str, Any]):
    billing = json.loads(row.get("billing_metadata_json") or "{}")
    metadata = json.loads(row.get("metadata_json") or "{}")
    site = billing.get("vegaSite")
    if site not in ("domestic", "international"):
        return None, "usage_dimension_unknown"
    count = row.get("generated_images")
    if type(count) is not int or count <= 0:
        return None, "usage_unknown"
    result = [("image", f"{site}:output", Decimal(count))]
    if row["model_alias"] == "vega-image-1.0-pro":
        inputs = metadata.get("vegaInputImageCount")
        # The accepted request proves the free allowance wasn't exceeded;
        # chargeable input counts require the supplier-confirmed Input.FileInfos.
        if inputs is None and type(billing.get("inputImageCount")) is int and 0 <= billing["inputImageCount"] <= 3:
            inputs = 0
        if type(inputs) is not int or inputs < 0:
            return None, "usage_unknown"
        result.append(("image", f"{site}:input:after_three", Decimal(max(0, inputs - 3))))
    return result, None
