"""Known supplier token counts, without inventing missing totals or details."""
import math
from typing import Any


def token_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    return int(value) if 0 <= value <= 2**63 - 1 else None


def token_summary(input_tokens: Any, output_tokens: Any, total_tokens: Any) -> tuple[int | None, bool]:
    incoming, outgoing, total = map(token_count, (input_tokens, output_tokens, total_tokens))
    if total is not None:
        return total, True
    if incoming is None and outgoing is None:
        return None, False
    return (incoming or 0) + (outgoing or 0), incoming is not None and outgoing is not None


# SQL equivalents for aggregation over historical rows, without changing the
# original NULL fields, frozen bills, or re-reading large response JSON blobs.
_TOTAL = "(typeof(total_tokens)='integer' AND total_tokens>=0)"
_INPUT = "(typeof(input_tokens)='integer' AND input_tokens>=0)"
_OUTPUT = "(typeof(output_tokens)='integer' AND output_tokens>=0)"
KNOWN_TOKENS_SQL = f"""CASE WHEN {_TOTAL} THEN total_tokens
    WHEN {_INPUT} OR {_OUTPUT} THEN
        (CASE WHEN {_INPUT} THEN input_tokens ELSE 0 END) +
        (CASE WHEN {_OUTPUT} THEN output_tokens ELSE 0 END)
    ELSE NULL END"""
COMPLETE_TOKENS_SQL = f"({_TOTAL} OR ({_INPUT} AND {_OUTPUT}))"
