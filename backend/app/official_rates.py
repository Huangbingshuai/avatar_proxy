"""Official online inference list prices bundled with the billing console.

The values below are deliberately kept separate from provider routing.  They are
used only to initialise the global billing rate card and can subsequently be
changed by the super administrator.  Amounts are CNY list prices, before a
project discount is applied.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final


VOLCENGINE_RATE_SOURCE_URL: Final = "https://www.volcengine.com/docs/82379/1544106"
VOLCENGINE_SPEECH_RATE_SOURCE_URL: Final = "https://www.volcengine.com/docs/6561/1359370"
VOLCENGINE_RATE_VERSION: Final = "2026-09-04"
VOLCENGINE_RATE_EFFECTIVE_MONTH: Final = "2026-09"


def _rule(metric: str, dimension: str, unit_size: int, price: str) -> tuple[str, str, int, Decimal]:
    return metric, dimension, unit_size, Decimal(price)


# ``resolution`` in billing_model_rates is retained for database compatibility,
# but represents a general pricing dimension.  For example ``tokens:0-32000``
# is a text context tier and ``720p:video`` is a video-input pricing variant.
OFFICIAL_VOLCENGINE_RATES: Final[dict[str, tuple[tuple[str, str, int, Decimal], ...]]] = {
    "deepseek-v4-flash": (
        _rule("input_tokens", "", 1_000_000, "3.00"),
        _rule("cached_input_tokens", "", 1_000_000, "0.10"),
        _rule("output_tokens", "", 1_000_000, "9.00"),
    ),
    "deepseek-v4-pro": (
        _rule("input_tokens", "", 1_000_000, "9.00"),
        _rule("cached_input_tokens", "", 1_000_000, "0.30"),
        _rule("output_tokens", "", 1_000_000, "27.00"),
    ),
    "glm-5.2": (
        _rule("input_tokens", "", 1_000_000, "8.00"),
        _rule("cached_input_tokens", "", 1_000_000, "2.00"),
        _rule("output_tokens", "", 1_000_000, "28.00"),
    ),
    "doubao-seed-evolving": (
        _rule("input_tokens", "", 1_000_000, "6.00"),
        _rule("cached_input_tokens", "", 1_000_000, "1.20"),
        _rule("output_tokens", "", 1_000_000, "30.00"),
    ),
    "doubao-seed-2.1-pro": (
        _rule("input_tokens", "", 1_000_000, "6.00"),
        _rule("cached_input_tokens", "", 1_000_000, "1.20"),
        _rule("output_tokens", "", 1_000_000, "30.00"),
    ),
    "doubao-seed-2.1-turbo": (
        _rule("input_tokens", "", 1_000_000, "3.00"),
        _rule("cached_input_tokens", "", 1_000_000, "0.60"),
        _rule("output_tokens", "", 1_000_000, "15.00"),
    ),
    "doubao-seed-2.0-pro": (),
    "doubao-seed-2.0-lite": (),
    "doubao-seed-2.0-mini": (),
    "doubao-seed-2.0-code": (),
    "doubao-seed-character": (),
    "doubao-seed-translation": (
        _rule("input_tokens", "", 1_000_000, "1.20"),
        _rule("output_tokens", "", 1_000_000, "3.60"),
    ),
    "doubao-seedream-5.0-pro": (
        _rule("image", "input:after_first", 1, "0.02"),
        _rule("image", "output:le2610000", 1, "0.30"),
        _rule("image", "output:gt2610000", 1, "0.60"),
    ),
    # The non-suffixed 5.0 endpoint uses the current 5.0 image list price.
    "doubao-seedream-5.0": (_rule("image", "", 1, "0.22"),),
    "doubao-seedream-5.0-lite": (_rule("image", "", 1, "0.22"),),
    "doubao-seedream-4.5": (_rule("image", "", 1, "0.25"),),
    "doubao-seedream-4.0": (_rule("image", "", 1, "0.20"),),
    "doubao-seedance-2.5": (),
    "doubao-seedance-2.0": (),
    "doubao-seedance-2.0-fast": (),
    "doubao-seedance-2.0-mini": (),
    "doubao-seedance-1.0-pro": (
        _rule("output_tokens", "", 1_000_000, "15.00"),
    ),
    "doubao-seedance-1.0-pro-fast": (
        _rule("output_tokens", "", 1_000_000, "4.20"),
    ),
    "doubao-embedding-vision": (
        _rule("input_tokens", "text", 1_000_000, "0.70"),
        _rule("input_tokens", "image", 1_000_000, "1.80"),
    ),
    "doubao-seed-tts-2.0": (_rule("characters", "", 10_000, "3.00"),),
    "doubao-seedasr-2.0": (_rule("audio_second", "", 3_600, "0.80"),),
    "doubao-seed-audio-1.0": (_rule("audio_second", "", 60, "1.00"),),
}


def _tiered_text(
    input_prices: tuple[str, ...], cached_prices: tuple[str, ...], output_prices: tuple[str, ...]
) -> tuple[tuple[str, str, int, Decimal], ...]:
    dimensions = ("tokens:0-32000", "tokens:32001-128000", "tokens:128001-256000")
    rows: list[tuple[str, str, int, Decimal]] = []
    for dimension, input_price, cached_price, output_price in zip(
        dimensions, input_prices, cached_prices, output_prices, strict=True
    ):
        rows.extend((
            _rule("input_tokens", dimension, 1_000_000, input_price),
            _rule("cached_input_tokens", dimension, 1_000_000, cached_price),
            _rule("output_tokens", dimension, 1_000_000, output_price),
        ))
    return tuple(rows)


OFFICIAL_VOLCENGINE_RATES["doubao-seed-2.0-pro"] = _tiered_text(
    ("3.20", "4.80", "9.60"), ("0.64", "0.96", "1.92"), ("16.00", "24.00", "48.00")
)
OFFICIAL_VOLCENGINE_RATES["doubao-seed-2.0-code"] = OFFICIAL_VOLCENGINE_RATES[
    "doubao-seed-2.0-pro"
]
OFFICIAL_VOLCENGINE_RATES["doubao-seed-2.0-lite"] = _tiered_text(
    ("0.60", "0.90", "1.80"), ("0.12", "0.18", "0.36"), ("3.60", "5.40", "10.80")
)
OFFICIAL_VOLCENGINE_RATES["doubao-seed-2.0-mini"] = _tiered_text(
    ("0.20", "0.40", "0.80"), ("0.04", "0.08", "0.16"), ("2.00", "4.00", "8.00")
)
OFFICIAL_VOLCENGINE_RATES["doubao-seed-character"] = (
    _rule("input_tokens", "tokens:0-32000", 1_000_000, "0.80"),
    _rule("cached_input_tokens", "tokens:0-32000", 1_000_000, "0.16"),
    _rule("output_tokens", "tokens:0-32000", 1_000_000, "2.00"),
    _rule("input_tokens", "tokens:32001-128000", 1_000_000, "1.20"),
    _rule("cached_input_tokens", "tokens:32001-128000", 1_000_000, "0.16"),
    _rule("output_tokens", "tokens:32001-128000", 1_000_000, "6.00"),
)


def _video_rules(prices: dict[str, tuple[str, str]]) -> tuple[tuple[str, str, int, Decimal], ...]:
    rows: list[tuple[str, str, int, Decimal]] = []
    for resolution, (without_video, with_video) in prices.items():
        rows.append(_rule("output_tokens", f"{resolution}:no_video", 1_000_000, without_video))
        rows.append(_rule("output_tokens", f"{resolution}:video", 1_000_000, with_video))
    return tuple(rows)


# Prices effective on 2026-09-10.  The 1080p Seedance 2.5 promotion ends
# 2026-09-17 14:00 (UTC+8); Fast/Mini promotions end 2026-10-07 14:00.
OFFICIAL_VOLCENGINE_RATES["doubao-seedance-2.5"] = _video_rules({
    "480p": ("70.00", "42.00"),
    "720p": ("70.00", "42.00"),
    "1080p": ("55.44", "33.12"),
})
OFFICIAL_VOLCENGINE_RATES["doubao-seedance-2.0"] = _video_rules({
    "480p": ("46.00", "28.00"),
    "720p": ("46.00", "28.00"),
    "1080p": ("51.00", "31.00"),
})
OFFICIAL_VOLCENGINE_RATES["doubao-seedance-2.0-fast"] = _video_rules({
    "480p": ("27.75", "16.50"),
    "720p": ("27.75", "16.50"),
})
OFFICIAL_VOLCENGINE_RATES["doubao-seedance-2.0-mini"] = _video_rules({
    "480p": ("9.20", "5.60"),
    "720p": ("9.20", "5.60"),
})
