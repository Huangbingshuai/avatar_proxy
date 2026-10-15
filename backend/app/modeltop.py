"""ModelTop's public catalogue and USD rate snapshot; no network calls at startup."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

MODELTOP_RATE_VERSION = "2026-10-15"
MODELTOP_RATE_EFFECTIVE_MONTH = "2026-10"
MODELTOP_RATE_SOURCE_URL = "https://modeltop.ai/#/market"
MODELTOP_FX = Decimal("6.706494")
MODELTOP_FX_SOURCE_URL = "https://open.er-api.com/v6/latest/USD"
MODELTOP_FX_TIMESTAMP = "2026-10-15T00:02:31Z"
MODELTOP_IMAGE_IDS = ("gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst")


def modeltop_alias(model: str) -> str:
    return model.replace("dreamina-seedance-2-5", "dreamina-seedance-2.5").replace("dreamina-seedance-2-0", "dreamina-seedance-2.0")
MODELTOP_VIDEO_PRICES = {
    "dreamina-seedance-2-5": {"480p": ("10.70", "6.40"), "720p": ("10.70", "6.40"), "1080p": ("11.70", "7.00")},
    "dreamina-seedance-2-0": {"480p": ("7.00", "4.30"), "720p": ("7.00", "4.30"), "1080p": ("7.70", "4.70"), "4k": ("4.00", "2.40")},
    "dreamina-seedance-2-0-fast": {"480p": ("5.60", "3.30"), "720p": ("5.60", "3.30")},
    "dreamina-seedance-2-0-mini": {"480p": ("3.50", "2.10"), "720p": ("3.50", "2.10")},
}
MODELTOP_VIDEO_IDS = tuple(model + suffix for model in MODELTOP_VIDEO_PRICES for suffix in ("", "-filter-off"))
# USD / million tokens. GPT Image 2 has no separately published cache-input
# row in ModelTop's detail table: leave that price missing, not free/guessed.
MODELTOP_IMAGE_PRICES = {
    model: (("input_tokens", "text", "5"), ("input_tokens", "image", "8"), ("output_tokens", "image", "30"))
    + ((("cached_input_tokens", "", "1.25"),) if "2.5" in model else ())
    for model in MODELTOP_IMAGE_IDS
}


def modeltop_cny(usd: str) -> Decimal:
    return (Decimal(usd) * MODELTOP_FX).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


MODELTOP_RATES = {
    modeltop_alias(model): tuple((metric, "modeltop:" + dimension, 1_000_000, modeltop_cny(usd)) for metric, dimension, usd in prices)
    for model, prices in MODELTOP_IMAGE_PRICES.items()
}
for _model, _prices in MODELTOP_VIDEO_PRICES.items():
    for _suffix in ("", "-filter-off"):
        MODELTOP_RATES[modeltop_alias(_model + _suffix)] = tuple(
            ("output_tokens", f"modeltop:{resolution}:{variant}", 1_000_000, modeltop_cny(prices[index]))
            for resolution, prices in _prices.items()
            for index, variant in enumerate(("no_video", "video"))
        )

MODELTOP_MODEL_CATALOG = tuple(
    (modeltop_alias(model), modeltop_alias(model), "modeltop", "image", "openai_image", model,
     {"generations": True, "maxN": 10, "billingMetric": "image_tokens", "billingUnit": 1_000_000,
      "imageTokenBilling": True, "qualityLevels": ["auto", "low", "medium", "high"] + (["xhigh", "max"] if "2.5" in model else []),
      "customSizes": "2.5" in model, "outputFormat": "2.5" in model})
    for model in MODELTOP_IMAGE_IDS
) + tuple(
    (modeltop_alias(model), modeltop_alias(model), "modeltop", "video", "async_video", model,
     {"text": True, "image": True, "video": True, "audio": True, "generateAudio": True,
      "durationMin": 4, "durationMax": 30 if "2-5" in model else 15, "smartDuration": True,
      "resolutions": list(MODELTOP_VIDEO_PRICES[model.removesuffix("-filter-off")]),
      "maxContent": 50 if "2-5" in model else 20, "maxN": 1, "cameraFixed": False,
      "seed": True, "serviceTiers": ["default"], "maxImages": 30 if "2-5" in model else 9,
      "maxVideos": 10 if "2-5" in model else 3, "maxAudios": 10 if "2-5" in model else 3,
      "audioOnly": "2-5" in model, "returnLastFrame": True,
      "cancelSupported": False, "billingMetric": "output_tokens", "billingUnit": 1_000_000})
    for model in MODELTOP_VIDEO_IDS
)

MODELTOP_MODELS = {row[0]: row for row in MODELTOP_MODEL_CATALOG}


def image_token_measurements(usage: dict[str, Any]):
    """Never price aggregate image input at the cheaper text-input rate."""
    def count(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    details = usage.get("input_tokens_details")
    output = usage.get("output_tokens_details")
    if not isinstance(details, dict) or not isinstance(output, dict):
        return None, "usage_unknown"
    text = count(details.get("text_tokens"))
    image = count(details.get("image_tokens"))
    generated = count(output.get("image_tokens"))
    total_input = count(usage.get("input_tokens"))
    cached = count(details.get("cached_tokens", 0))
    if None in (text, image, generated, total_input, cached):
        return None, "usage_unknown"
    if text + image != total_input or cached > total_input:
        return None, "usage_invalid"
    if cached:
        split = details.get("cached_tokens_details")
        if isinstance(split, dict):
            cached_text, cached_image = count(split.get("text_tokens")), count(split.get("image_tokens"))
            if cached_text is None or cached_image is None:
                return None, "cached_input_split_unknown"
        elif not image:
            cached_text, cached_image = cached, 0
        elif not text:
            cached_text, cached_image = 0, cached
        else:
            return None, "cached_input_split_unknown"
        if cached_text + cached_image != cached or cached_text > text or cached_image > image:
            return None, "usage_invalid"
        text -= cached_text
        image -= cached_image
    measurements = [("input_tokens", "text", Decimal(text)), ("input_tokens", "image", Decimal(image)),
                    ("output_tokens", "image", Decimal(generated))]
    if cached:
        measurements.append(("cached_input_tokens", "", Decimal(cached)))
    return measurements, None
