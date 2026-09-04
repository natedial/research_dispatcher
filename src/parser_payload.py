"""Helpers for parser-owned `parsed_data` after the parse-and-store cut.

`research_parser` no longer writes `parsed_data.themes` or `parsed_data.trades`.
New rows look like `{full_text, identity, parse}`. Downstream synthesis must
not treat those empty lists as a usable through-line substrate.

Legacy rows may still carry `{metadata, themes, trades}`.
"""

from __future__ import annotations

from typing import Any

_SYNTHESIS_SIGNAL_KEYS = (
    "themes",
    "trades",
    "assertions",
    "talking_points",
    "trading_opportunities",
    "short_time_horizon_insights",
)

SOURCE_ONLY_PARSER_MODE_ERROR = (
    "Parser rows have no themes or trades. research_parser is source-only now; "
    "do not read parsed_data.themes / parsed_data.trades. Export an analyst "
    "dispatch batch and set DISPATCH_INPUT_MODE=analyst with ANALYST_BATCH_PATH."
)


def is_source_only_parsed_data(parsed_data: Any) -> bool:
    """True when a parsed_research blob has no usable theme/trade extraction."""
    if not isinstance(parsed_data, dict) or not parsed_data:
        return True
    themes = parsed_data.get("themes")
    trades = parsed_data.get("trades")
    has_themes = isinstance(themes, list) and any(isinstance(item, dict) for item in themes)
    has_trades = isinstance(trades, list) and any(isinstance(item, dict) for item in trades)
    return not (has_themes or has_trades)


def documents_are_source_only(documents: list[dict[str, Any]]) -> bool:
    """True when every loaded parser row is source-only.

    Empty lists are not source-only: the caller already treats "no documents"
    as a successful no-op.
    """
    if not documents:
        return False
    return all(is_source_only_parsed_data(doc.get("parsed_data")) for doc in documents)


def has_synthesis_signals(payload: dict[str, Any]) -> bool:
    """True when Stage 1 has any through-line substrate, not just themes."""
    for key in _SYNTHESIS_SIGNAL_KEYS:
        value = payload.get(key) or []
        if isinstance(value, list) and value:
            return True
    return False
