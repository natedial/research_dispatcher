"""Select dispatcher input from parser rows or an analyst batch."""

from __future__ import annotations

from src.analyst_client import AnalystBatchClient
from src.parser_payload import (
    SOURCE_ONLY_PARSER_MODE_ERROR,
    documents_are_source_only,
)


def load_dispatch_documents(
    *,
    input_mode: str,
    analyst_batch_path: str,
    db_client,
) -> tuple[list[dict], object | None, str]:
    """Load dispatcher input from the explicitly selected source."""
    if input_mode == "parser":
        data = db_client.query_analysis()
        if documents_are_source_only(data):
            raise ValueError(SOURCE_ONLY_PARSER_MODE_ERROR)
        return data, None, "parsed_research"
    if input_mode == "analyst":
        dispatch_batch = AnalystBatchClient(analyst_batch_path).load_batch()
        return dispatch_batch.to_legacy_records(), dispatch_batch, "analyst_batch"
    raise ValueError("DISPATCH_INPUT_MODE must be one of: parser, analyst")
