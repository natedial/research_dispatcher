import unittest

from src.formatter import ReportFormatter
from src.synthesizer import Synthesizer
from src.throughline_input_builder import ThroughlineInputBuilder
from src.trade_curation import (
    assign_trade_ids,
    build_trade_catalog,
    collect_curated_trades,
    match_trade_id_by_text,
    resolve_through_line_trade_references,
)


class TradeCurationTests(unittest.TestCase):
    def test_assign_trade_ids_is_stable_and_sequential(self):
        trades = [{"text": "Pay 5y"}, {"text": "Long 2s10s"}]
        assign_trade_ids(trades)
        self.assertEqual(trades[0]["trade_id"], "t1")
        self.assertEqual(trades[1]["trade_id"], "t2")

    def test_resolve_through_line_trade_references_uses_parser_text(self):
        catalog = build_trade_catalog(
            [
                {
                    "trade_id": "t1",
                    "text": "Pay 5y rates",
                    "exposure": "Pay 5y rates",
                    "rationale": "Sticky inflation risk",
                    "conviction": "high",
                    "source": "Goldman Sachs",
                    "document": "Rates Daily",
                },
                {
                    "trade_id": "t2",
                    "text": "Long Brent on Libya outage",
                    "exposure": "Long Brent on Libya outage",
                    "rationale": "OPEC supply risk",
                    "conviction": "high",
                    "source": "Goldman Sachs",
                    "document": "Rates Daily",
                },
            ]
        )
        through_line = {
            "lead": "Curve steepeners remain attractive.",
            "supporting_trade_ids": ["t1"],
        }

        resolve_through_line_trade_references(through_line, catalog)

        self.assertEqual(through_line["supporting_trade_ids"], ["t1"])
        self.assertEqual(through_line["supporting_trades"], ["Pay 5y rates"])
        self.assertEqual(through_line["supporting_trade_refs"][0]["rationale"], "Sticky inflation risk")

    def test_invalid_trade_ids_are_dropped(self):
        catalog = build_trade_catalog(
            [{"trade_id": "t1", "text": "Pay 5y rates", "exposure": "Pay 5y rates"}]
        )
        through_line = {"supporting_trade_ids": ["t99"]}
        resolve_through_line_trade_references(through_line, catalog)
        self.assertEqual(through_line["supporting_trade_ids"], [])
        self.assertEqual(through_line["supporting_trades"], [])

    def test_text_fallback_matches_verbatim_parser_trade(self):
        catalog = build_trade_catalog(
            [{"trade_id": "t1", "text": "Pay 5y rates", "exposure": "Pay 5y rates"}]
        )
        through_line = {"supporting_trades": ["Pay 5y rates"]}
        resolve_through_line_trade_references(through_line, catalog)
        self.assertEqual(through_line["supporting_trade_ids"], ["t1"])

    def test_collect_curated_trades_dedupes_across_through_lines(self):
        through_lines = [
            {
                "lead": "Front-end bias lower",
                "supporting_trade_refs": [
                    {
                        "trade_id": "t1",
                        "text": "Receive 2y",
                        "exposure": "Receive 2y",
                        "conviction": "high",
                        "source": "JPM",
                        "document": "Desk Note",
                    }
                ],
            },
            {
                "lead": "Payrolls risk",
                "supporting_trade_refs": [
                    {
                        "trade_id": "t1",
                        "text": "Receive 2y",
                        "exposure": "Receive 2y",
                        "conviction": "high",
                        "source": "JPM",
                        "document": "Desk Note",
                    },
                    {
                        "trade_id": "t2",
                        "text": "5s30s steepeners",
                        "exposure": "5s30s steepeners",
                        "conviction": "high",
                        "source": "Barclays",
                        "document": "Weekly",
                    },
                ],
            },
        ]

        curated = collect_curated_trades(through_lines)
        self.assertEqual([trade["trade_id"] for trade in curated], ["t1", "t2"])
        self.assertEqual(curated[0]["text"], "Receive 2y")

    def test_match_trade_id_by_text_requires_exact_normalized_match(self):
        catalog = build_trade_catalog(
            [{"trade_id": "t1", "text": "Pay 5y rates", "exposure": "Pay 5y rates"}]
        )
        self.assertEqual(match_trade_id_by_text("Pay 5y rates", catalog), "t1")
        self.assertEqual(match_trade_id_by_text("Invented trade", catalog), "")


class ThroughlineInputBuilderTradeIdTests(unittest.TestCase):
    def test_build_from_legacy_documents_assigns_trade_ids(self):
        payload = ThroughlineInputBuilder().build_from_legacy_documents(
            [
                {
                    "document_name": "Rates Daily",
                    "source": "Goldman Sachs",
                    "source_date": "2026-03-30",
                    "parsed_data": {
                        "trades": [
                            {
                                "exposure": "Pay 5y rates",
                                "conviction": "High",
                                "rationale": "Inflation risk",
                                "trigger_levels": {"entry": "4.10"},
                            }
                        ]
                    },
                }
            ]
        )
        self.assertEqual(payload["trades"][0]["trade_id"], "t1")
        self.assertEqual(payload["trades"][0]["rationale"], "Inflation risk")
        self.assertEqual(payload["trades"][0]["trigger_levels"], {"entry": "4.10"})


class SynthesizerTradeResolutionTests(unittest.TestCase):
    def test_normalize_through_lines_resolves_trade_ids(self):
        synthesizer = Synthesizer(
            anthropic_api_key=None,
            openai_api_key=None,
            deepinfra_api_key=None,
            openrouter_api_key=None,
        )
        through_lines = [
            {
                "lead": "Curve steepeners remain attractive.",
                "supporting_trade_ids": ["t1"],
                "supporting_trades": [],
            }
        ]
        input_data = {
            "trades": [
                {
                    "trade_id": "t1",
                    "text": "5s30s steepeners",
                    "exposure": "5s30s steepeners",
                    "rationale": "Carry remains attractive.",
                    "source": "Barclays",
                    "document": "Weekly",
                }
            ]
        }

        synthesizer._normalize_through_lines(through_lines, input_data=input_data)

        self.assertEqual(through_lines[0]["supporting_trades"], ["5s30s steepeners"])
        self.assertEqual(through_lines[0]["supporting_trade_refs"][0]["rationale"], "Carry remains attractive.")


class FormatterCuratedTradeTests(unittest.TestCase):
    def test_build_curated_trades_from_synthesis_filters_conviction(self):
        formatter = ReportFormatter()
        through_lines = [
            {
                "lead": "Rates trade",
                "supporting_trade_refs": [
                    {
                        "trade_id": "t1",
                        "text": "Pay 5y",
                        "exposure": "Pay 5y",
                        "conviction": "high",
                        "source": "GS",
                        "document": "Note",
                    },
                    {
                        "trade_id": "t2",
                        "text": "Long Brent",
                        "exposure": "Long Brent",
                        "conviction": "medium",
                        "source": "GS",
                        "document": "Note",
                    },
                ],
            }
        ]

        curated = formatter.build_curated_trades_from_synthesis(
            through_lines,
            conviction_filter="high",
        )
        self.assertEqual(len(curated), 1)
        self.assertEqual(curated[0]["trade_id"], "t1")


if __name__ == "__main__":
    unittest.main()
