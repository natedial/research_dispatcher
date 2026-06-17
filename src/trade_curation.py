"""Resolve synthesis trade references back to verbatim parsed-research trades."""

from __future__ import annotations

import re
from typing import Any

from .trade_normalization import normalize_trade_expression

_TRADE_ID_PATTERN = re.compile(r"^t(\d+)$", re.IGNORECASE)


def assign_trade_ids(trades: list[dict[str, Any]]) -> None:
    """Assign stable trade_id values (t1, t2, ...) to synthesis input trades."""
    counter = 1
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        if not str(trade.get("trade_id") or "").strip():
            trade["trade_id"] = f"t{counter}"
            counter += 1


def build_trade_catalog(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index synthesis trades by trade_id."""
    catalog: dict[str, dict[str, Any]] = {}
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        trade_id = normalize_trade_id(trade.get("trade_id"))
        if trade_id:
            catalog[trade_id] = trade
    return catalog


def normalize_trade_id(value: Any) -> str:
    """Normalize trade id variants like t1, T1, or trade_1 into canonical tN."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    match = _TRADE_ID_PATTERN.match(text)
    if match:
        return f"t{match.group(1)}"
    if text.startswith("trade_"):
        suffix = text.removeprefix("trade_")
        if suffix.isdigit():
            return f"t{suffix}"
    return ""


def coerce_supporting_trade_ids(value: Any, *, limit: int = 2) -> list[str]:
    """Normalize model output into canonical supporting_trade_ids."""
    if value is None:
        return []

    raw_items = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, dict):
            candidate = normalize_trade_id(
                item.get("trade_id") or item.get("id") or item.get("trade")
            )
        else:
            candidate = normalize_trade_id(item)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
        if len(normalized) >= limit:
            break
    return normalized


def match_trade_id_by_text(
    text: str,
    trade_catalog: dict[str, dict[str, Any]],
) -> str:
    """Best-effort fallback when a model returns free-text trade expressions."""
    normalized = normalize_trade_expression(text).lower()
    if not normalized:
        return ""

    for trade_id, trade in trade_catalog.items():
        candidates = [
            trade.get("text"),
            trade.get("exposure"),
        ]
        for candidate in candidates:
            trade_text = normalize_trade_expression(str(candidate or "")).lower()
            if trade_text and trade_text == normalized:
                return trade_id
    return ""


def resolve_through_line_trade_references(
    through_line: dict[str, Any],
    trade_catalog: dict[str, dict[str, Any]],
    *,
    max_trades: int = 2,
    allow_text_fallback: bool = True,
) -> None:
    """Resolve supporting_trade_ids to verbatim parser trades on a through-line."""
    trade_ids = coerce_supporting_trade_ids(
        through_line.get("supporting_trade_ids"),
        limit=max_trades,
    )

    if not trade_ids and allow_text_fallback:
        for text in through_line.get("supporting_trades") or []:
            matched = match_trade_id_by_text(str(text), trade_catalog)
            if matched and matched not in trade_ids:
                trade_ids.append(matched)
            if len(trade_ids) >= max_trades:
                break

    refs: list[dict[str, Any]] = []
    display_texts: list[str] = []
    for trade_id in trade_ids[:max_trades]:
        trade = trade_catalog.get(trade_id)
        if not trade:
            continue
        refs.append(dict(trade))
        display_text = normalize_trade_expression(
            trade.get("text") or trade.get("exposure") or ""
        )
        if display_text:
            display_texts.append(display_text)

    through_line["supporting_trade_ids"] = [ref["trade_id"] for ref in refs if ref.get("trade_id")]
    through_line["supporting_trade_refs"] = refs
    through_line["supporting_trades"] = display_texts


def trade_ref_to_report_entry(trade: dict[str, Any]) -> dict[str, Any]:
    """Convert a resolved trade reference into report-ready trade metadata."""
    conviction = trade.get("conviction", "N/A")
    if isinstance(conviction, str):
        conviction = conviction.strip().lower()
    else:
        conviction = "n/a"

    text = normalize_trade_expression(
        trade.get("text") or trade.get("exposure") or "N/A"
    ) or "N/A"

    return {
        "trade_id": trade.get("trade_id"),
        "text": text,
        "exposure": trade.get("exposure") or text,
        "rationale": trade.get("rationale", ""),
        "timeframe": trade.get("timeframe", "N/A"),
        "conviction": conviction,
        "trigger_levels": trade.get("trigger_levels"),
        "document": trade.get("document", "Unknown Document"),
        "source": trade.get("source", "Unknown Source"),
        "date": trade.get("source_date", ""),
    }


def collect_curated_trades(
    through_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union resolved trade refs across through-lines, preserving parser fidelity."""
    curated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for through_line in through_lines:
        if not isinstance(through_line, dict):
            continue
        lead = str(through_line.get("lead") or "").strip()
        refs = through_line.get("supporting_trade_refs") or []
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            trade_id = str(ref.get("trade_id") or "").strip()
            if trade_id:
                if trade_id in seen_ids:
                    continue
                seen_ids.add(trade_id)
            entry = trade_ref_to_report_entry(ref)
            if lead:
                entry["through_line_lead"] = lead
            curated.append(entry)

    return curated
