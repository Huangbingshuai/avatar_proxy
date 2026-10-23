"""Tencent VOD Vega adapter. No network access or credentials at import time.

Contract: customer-supplied Vega integration PDFs, reviewed 2026-10-22.
Only supplier-returned Usage fields are used for settlement, never requested time.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlsplit

from .errors import ApiError

VEGA_VERSION = "2026-10-22"
VEGA_FX = Decimal("6.689327")
VEGA_FX_SOURCE = "https://open.er-api.com/v6/latest/USD"
VEGA_FX_TIMESTAMP = "2026-10-22T00:02:31Z"
VEGA_SOURCE = "https://doc.weixin.qq.com/smartpage/a1_AT4ACga-AMYCNn9hEbBjPT9OliRaA"
VEGA_HOSTS = {"domestic": "vod.tencentcloudapi.com", "international": "vod.intl.tencentcloudapi.com"}
VERSIONS = ("1.0-lite", "1.0-pro", "1.0-pro-fast", "1.0-pro-mini", "1.5-pro")
VEGA_MODEL_CATALOG = tuple(
    (f"vega-{version}", f"Vega {version}", "vega", "video", "async_video", version,
     {"text": True, "image": True, "video": True, "audio": True, "generateAudio": True,
      "durationMin": 4, "durationMax": 30 if version == "1.5-pro" else 15,
      "smartDuration": version != "1.0-lite", "resolutions": ["480p", "768p", "1080p", "2k", "4k"]
      if version == "1.0-lite" else ["720p", "1080p", "2k", "4k"],
      "defaultResolution": "768p" if version == "1.0-lite" else "720p",
      "maxContent": 51 if version == "1.5-pro" else 13,
      "maxImages": 30 if version == "1.5-pro" else 9,
      "maxVideos": 10 if version == "1.5-pro" else 3,
      "maxAudios": 10 if version == "1.5-pro" else 3,
      "maxFiles": 50 if version == "1.5-pro" else 12,
      "audioOnly": False, "cancelSupported": False, "seed": version != "1.0-lite",
      "returnLastFrame": version != "1.0-lite", "billingMetric": "video_second", "billingUnit": 1,
      **({"outputFormats": ["mp4"]}
         if version != "1.0-lite" else {})})
    for version in VERSIONS
)

# Per-second catalogue: (without reference video, with reference video).
# The latter applies to BOTH input and output; Pro input has a 2/3 output floor.
# 480P Pro prices appear in the price sheet but are deliberately not advertised:
# its integration contract lists only 720P/1080P/2K/4K as supported output.
_PRICES = {
    "1.0-lite": ((".297", ".375", ".500", ".625", ".750"),
                 (".0457", ".0577", ".0769", ".0962", ".1154")),
    "1.0-pro": (((".416", ".795", "1.730", "4.300", "4.900"),
                  (".261", ".500", "1.080", "2.670", "3.000")),
                 ((".0640", ".1223", ".2662", ".6615", ".7538"),
                  (".0402", ".0769", ".1662", ".4108", ".4615"))),
    "1.5-pro": (((".606", "1.188", "2.587", "6.370", "7.007"),
                  (".364", ".740", "1.580", "3.860", "4.246")),
                 ((".0932", ".1828", ".3979", ".9800", "1.0780"),
                  (".0559", ".1138", ".2431", ".5938", ".6532"))),
    "1.0-pro-fast": (((".335", ".645", "1.400", "1.540", "1.694"),
                       (".207", ".408", ".867", ".953", "1.049")),
                      ((".0515", ".0992", ".2154", ".2369", ".2606"),
                       (".0318", ".0628", ".1333", ".1467", ".1613"))),
    "1.0-pro-mini": (((".209", ".412", ".900", ".990", "1.089"),
                       (".126", ".300", ".583", ".642", ".706")),
                      ((".0321", ".0633", ".1385", ".1523", ".1675"),
                       (".0194", ".0462", ".0897", ".0987", ".1086"))),
}
VEGA_RATES: dict[str, tuple] = {}
for _row in VEGA_MODEL_CATALOG:
    _version, _rules = _row[5], []
    for _index, _site in enumerate(VEGA_HOSTS):
        _multiplier = Decimal(1) if _site == "domestic" else VEGA_FX
        _raw = _PRICES[_version][_index]
        _plain, _reference = (_raw, _raw) if _version == "1.0-lite" else _raw
        for _resolution in _row[6]["resolutions"]:
            _price_index = ("480p", "768p", "1080p", "2k", "4k").index(_resolution.replace("720p", "768p"))
            for _variant, _amount in (("no_video", _plain[_price_index]), ("video", _reference[_price_index])):
                _rules.append(("video_second", f"{_site}:{_resolution}:{_variant}", 1,
                               (Decimal(_amount) * _multiplier).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)))
        if _version == "1.0-lite":
            _rules.append(("image", f"{_site}:input:after_five", 1,
                           (Decimal(".15" if _index == 0 else ".03") * _multiplier).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)))
    VEGA_RATES[_row[0]] = tuple(_rules)


def credentials(secret: str) -> dict[str, str]:
    try:
        value = json.loads(secret)
    except (ValueError, TypeError):
        value = None
    if not isinstance(value, dict) or not value or set(value) - {"secretId", "secretKey", "apiToken"}:
        raise ApiError("Vega凭证须包含SecretId/SecretKey或VL API Token", 422, "vega_credentials_invalid")
    pair = {"secretId", "secretKey"} & set(value)
    if pair and (pair != {"secretId", "secretKey"} or any(
            not isinstance(value[k], str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", value[k]) for k in pair)):
        raise ApiError("Vega的SecretId和SecretKey须完整填写", 422, "vega_credentials_invalid")
    token = value.get("apiToken")
    if "apiToken" in value and (not isinstance(token, str) or not 8 <= len(token) <= 4096
                               or any(not 33 <= ord(c) <= 126 for c in token)):
        raise ApiError("Vega-VL API Token格式无效", 422, "vega_credentials_invalid")
    return value


def api_token(secret: str) -> str:
    token = credentials(secret).get("apiToken")
    if not token:
        raise ApiError("Vega渠道尚未配置VL API Token，请在渠道轮换凭证中补充", 503, "vega_vl_token_missing")
    return token


def tc3_credentials(secret: str) -> dict[str, str]:
    keys = credentials(secret)
    if not keys.get("secretId") or not keys.get("secretKey"):
        raise ApiError("Vega视频和生图需要渠道的SecretId及SecretKey", 503, "vega_tc3_credentials_missing")
    return keys


def channel_config(config: dict[str, Any]) -> dict[str, str]:
    if set(config) - {"site", "subAppId"}:
        raise ApiError("Vega渠道仅接受site和subAppId", 422, "provider_config_field_forbidden")
    site, sub_app = config.get("site", "domestic"), str(config.get("subAppId", ""))
    if not isinstance(site, str) or site not in VEGA_HOSTS or not re.fullmatch(r"[1-9][0-9]{0,18}", sub_app):
        raise ApiError("请选择Vega国内/国际站并填写有效SubAppId", 422, "vega_config_invalid")
    return {"site": site, "subAppId": sub_app}


def signed_request(secret: str, config: dict[str, Any], action: str, payload: dict[str, Any], timestamp: int):
    config = channel_config(config)
    keys = tc3_credentials(secret)
    host = VEGA_HOSTS[config["site"]]
    body = json.dumps({**payload, "SubAppId": int(config["subAppId"])}, ensure_ascii=False, separators=(",", ":")).encode()
    content_type = "application/json; charset=utf-8"
    canonical = f"POST\n/\n\ncontent-type:{content_type}\nhost:{host}\nx-tc-action:{action.lower()}\n\ncontent-type;host;x-tc-action\n{hashlib.sha256(body).hexdigest()}"
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
    scope = f"{date}/vod/tc3_request"
    to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    def digest(key, text):
        return hmac.new(key, text.encode(), hashlib.sha256).digest()
    signing_key = digest(digest(digest(("TC3" + keys["secretKey"]).encode(), date), "vod"), "tc3_request")
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {"Content-Type": content_type, "Host": host, "X-TC-Action": action,
               "X-TC-Timestamp": str(timestamp), "X-TC-Version": "2018-07-17",
               "Authorization": f"TC3-HMAC-SHA256 Credential={keys['secretId']}/{scope}, SignedHeaders=content-type;host;x-tc-action, Signature={signature}"}
    return "https://" + host + "/", headers, body


def _invalid(message: str, code: str = "vega_parameter_invalid"):
    raise ApiError(message, 422, code)


def media_url(url: Any, *, assets: bool = True) -> str:
    if not isinstance(url, str) or len(url) > 8192:
        _invalid("Vega参考素材地址无效")
    if assets and re.fullmatch(r"asset://[A-Za-z0-9_-]+/?", url):
        return url
    try:
        parsed = urlsplit(url)
        if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password:
            return url
    except ValueError:
        pass
    _invalid("Vega仅接受HTTP(S)素材URL或本渠道已登记的asset://素材")


def submit_payload(route: Any, payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("metadata", {})
    if not isinstance(meta, dict):
        _invalid("metadata必须为对象")
    allowed = {"content", "resolution", "ratio", "generate_audio", "return_last_frame", "output_format", "vega"}
    unknown = set(meta) - allowed
    if unknown:
        _invalid("Vega不支持这些参数：" + ",".join(sorted(unknown)), "video_parameter_unsupported")
    caps, version = route.capabilities, route.upstream_model
    content = meta.get("content", [])
    if not isinstance(content, list) or len(content) > caps["maxContent"]:
        _invalid("Vega content格式或数量无效")
    prompts, files, counts, frame_roles = [], [], {"Image": 0, "Video": 0, "Audio": 0}, []
    for item in content:
        if not isinstance(item, dict):
            _invalid("content条目必须为对象")
        kind = item.get("type")
        if kind == "text":
            if set(item) != {"type", "text"} or not isinstance(item.get("text"), str):
                _invalid("文本参考格式无效")
            prompts.append(item["text"])
            continue
        if not isinstance(kind, str):
            _invalid("content类型无效")
        spec = {"image_url": ("Image", ("first_frame", "last_frame", "reference_image")),
                "video_url": ("Video", ("reference_video",)), "audio_url": ("Audio", ("reference_audio",))}.get(kind)
        if not spec or set(item) != {"type", kind, "role"}:
            _invalid("Vega参考素材格式无效")
        category, roles = spec
        source, role = item.get(kind), item.get("role")
        if role not in roles or not isinstance(source, dict) or set(source) != {"url"}:
            _invalid("Vega参考素材类型或用途无效")
        counts[category] += 1
        frame_roles.append(role)
        files.append({"Type": "Url", "Category": category, "Url": media_url(source["url"]),
                      "Usage": {"first_frame": "FirstFrame", "last_frame": "LastFrame"}.get(role, "Reference")})
    if not content:
        prompt = payload.get("prompt", "")
        if not isinstance(prompt, str):
            _invalid("prompt必须为字符串")
        prompts.append(prompt)
    prompt = "\n".join(prompts)
    if (not prompt.strip() and not files) or (version == "1.0-lite" and len(prompt) > 7000):
        _invalid("请提供提示词或参考素材；Lite提示词不超过7000字符")
    if (len(files) > caps["maxFiles"] or counts["Image"] > caps["maxImages"]
            or counts["Video"] > caps["maxVideos"] or counts["Audio"] > caps["maxAudios"]):
        _invalid("Vega参考素材数量超过当前模型上限", "video_content_limit")
    if counts["Audio"] and not (counts["Image"] or counts["Video"]):
        _invalid("参考音频必须搭配图片或视频")
    frames = {"first_frame", "last_frame"}
    if frame_roles.count("first_frame") > 1 or frame_roles.count("last_frame") > 1:
        _invalid("首尾帧各最多一张")
    if frames.intersection(frame_roles) and any(r not in frames for r in frame_roles):
        _invalid("首尾帧不能与全模态参考混用")
    duration = payload.get("duration", 4)
    if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
            or not (4 <= duration <= caps["durationMax"] or duration == -1 and caps["smartDuration"])):
        _invalid("Vega输出时长无效", "video_duration_invalid")
    resolution = meta.get("resolution", caps["defaultResolution"])
    if not isinstance(resolution, str) or resolution.lower() not in caps["resolutions"]:
        _invalid("Vega不支持该输出分辨率", "video_resolution_invalid")
    ratio = meta.get("ratio", "16:9")
    if ratio not in ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"):
        _invalid("视频比例无效")
    if version == "1.0-lite" and ratio == "adaptive" and not files:
        _invalid("Lite文生视频不支持adaptive，需指定明确比例")
    audio = meta.get("generate_audio", True)
    if not isinstance(audio, bool):
        _invalid("generate_audio必须为布尔值")
    output = {"StorageMode": "Temporary", "Duration": duration, "Resolution": resolution.upper(),
              "AspectRatio": ratio, "AudioGeneration": "Enabled" if audio else "Disabled"}
    options = meta.get("vega", {})
    if not isinstance(options, dict) or set(options) - {"enhance_prompt", "moderation_mode", "generate_mode", "video_quality_mode", "task_type"}:
        _invalid("vega额外参数无效")
    wand, additional = {"ReturnVegaUsage": True}, {}
    for key, upstream, values in (
        ("enhance_prompt", "EnhancePromptMode", {"auto", "enable", "disable"}),
        ("moderation_mode", "ModerationMode", {"Moderation_L1", "Moderation_L2"}),
        ("generate_mode", "GenerateMode", {"Standard", "Fast", "StandardMovie"}),
        ("video_quality_mode", "VideoQualityMode", {"Standard", "Fast", "SuperFast"}),
    ):
        if key in options:
            if options[key] not in tuple(values) or key in {"generate_mode", "video_quality_mode"} and version != "1.0-lite":
                _invalid("当前Vega版本不支持该额外参数值")
            wand[upstream] = options[key]
    for key, value in (("return_last_frame", meta.get("return_last_frame")), ("output_format", meta.get("output_format"))):
        if value is not None:
            if key == "output_format" and value not in caps.get("outputFormats", []):
                _invalid("当前Vega版本不支持该输出格式，请查询模型outputFormats能力", "video_output_format_invalid")
            if version == "1.0-lite" or (key == "return_last_frame" and not isinstance(value, bool)):
                _invalid("当前Vega版本不支持该输出选项")
            additional[key] = value
    if "task_type" in options:
        task_type = options["task_type"]
        if version != "1.5-pro" or task_type not in ("auto", "reference", "edit", "extend"):
            _invalid("task_type仅支持Vega 1.5 Pro")
        if task_type in ("edit", "extend") and (not counts["Video"] or ratio != "adaptive" or task_type == "edit" and duration != -1):
            _invalid("编辑/延长需要参考视频和adaptive比例；编辑时duration必须为-1")
        additional["omni_reference_task_type"] = task_type
    body = {"ModelName": "wand-vega-video", "ModelVersion": version, "Prompt": prompt,
            "FileInfos": files, "OutputConfig": output}
    if "seed" in payload:
        seed = payload["seed"]
        if not caps["seed"] or isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed <= 2**31-1:
            _invalid("当前Vega版本不支持该seed")
        body["Seed"] = seed
    ext = {"WandVegaParameters": json.dumps(wand, separators=(",", ":"))}
    if additional:
        ext["AdditionalParameters"] = json.dumps(additional, separators=(",", ":"))
    body["ExtInfo"] = json.dumps(ext, separators=(",", ":"))
    return body


def number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def video_result(data: dict[str, Any]) -> dict[str, Any]:
    task = data.get("AigcVideoTask")
    if not isinstance(task, dict):
        if data.get("Status") == "FINISH":
            raise ApiError("Vega返回了非视频任务结果", 502, "provider_response_invalid")
        return {"status": "running", "url": None, "usage": {}, "metadata": {}}
    output = task.get("Output") if isinstance(task.get("Output"), dict) else {}
    usage = output.get("Usage") if isinstance(output.get("Usage"), dict) else {}
    files = output.get("FileInfos") if isinstance(output.get("FileInfos"), list) else []
    main = next((item for item in files if isinstance(item, dict) and not item.get("UsageType") and item.get("FileUrl")), {})
    last = next((item for item in files if isinstance(item, dict) and item.get("UsageType") == "last_frame_url"), {})
    finished = task.get("Status", data.get("Status")) == "FINISH"
    # Missing error codes are NOT proof of success.
    success = finished and type(task.get("ErrCode")) is int and task["ErrCode"] == 0 and bool(main)
    status = "succeeded" if success else "failed" if finished else "queued" if task.get("Status") == "WAITING" else "running"
    tokens = {target: usage[source] for source, target in (("InputTokens", "input_tokens"), ("CompletionTokens", "completion_tokens"), ("TotalTokens", "total_tokens"))
              if isinstance(usage.get(source), int) and not isinstance(usage[source], bool) and usage[source] >= 0}
    task_input = task.get("Input") if isinstance(task.get("Input"), dict) else {}
    input_config = task_input.get("OutputConfig") if isinstance(task_input.get("OutputConfig"), dict) else {}
    metadata = {"usage": {**tokens, "vega": usage}, "resolution": str(input_config.get("Resolution") or "").lower() or None,
                "duration": usage.get("OutputSeconds"), "ratio": input_config.get("AspectRatio"),
                "last_frame_url": last.get("FileUrl")}
    return {"status": status, "url": main.get("FileUrl"), "usage": tokens,
            "seconds": usage.get("OutputSeconds"), "metadata": metadata,
            "error": task.get("Message") or ("Vega任务失败或缺少输出视频" if status == "failed" else None),
            "error_code": str(task.get("ErrCodeExt") or "provider_task_failed")}


def measurements(row: dict[str, Any]):
    billing = json.loads(row.get("billing_metadata_json") or "{}")
    metadata = json.loads(row.get("metadata_json") or "{}")
    usage = metadata.get("usage", {}).get("vega", {})
    resolution = str(metadata.get("resolution") or billing.get("resolution") or "").lower()
    site = billing.get("vegaSite")
    if site not in VEGA_HOSTS or resolution not in {"480p", "720p", "768p", "1080p", "2k", "4k"}:
        return None, "resolution_unknown"
    output, inputs = number(usage.get("OutputSeconds")), number(usage.get("InputSeconds"))
    if output is None or output <= 0:
        return None, "usage_unknown"
    lite = row.get("model_alias") == "vega-1.0-lite"
    has_video = billing.get("containsVideoInput") is True
    if (has_video or lite) and inputs is None:
        return None, "usage_unknown"
    if not has_video and inputs is not None and inputs > 0:
        return None, "usage_invalid"
    # Apply the published floor to REAL supplier input/output usage only. If VOD
    # already reports floored settlement seconds, max() does not charge it twice.
    charged_input = (inputs if lite else max(inputs, output * Decimal(2) / Decimal(3))) if has_video else Decimal(0)
    quantity = output + charged_input
    result = [("video_second", f"{site}:{resolution}:{'video' if has_video else 'no_video'}", quantity)]
    if lite:
        images = number(usage.get("InputImageCount"))
        if images is None or images != images.to_integral_value():
            return None, "usage_unknown"
        result.append(("image", f"{site}:input:after_five", max(Decimal(0), images - 5)))
    return result, None
