import unittest
from unittest.mock import Mock

from src.dispatch_input import load_dispatch_documents
from src.parser_payload import (
    documents_are_source_only,
    has_synthesis_signals,
    is_source_only_parsed_data,
)
from src.report_models import DispatchBatch
from src.synthesizer import Synthesizer
from src.throughline_input_builder import ThroughlineInputBuilder


class ParserPayloadTests(unittest.TestCase):
    def test_substrate_payload_is_source_only(self):
        self.assertTrue(
            is_source_only_parsed_data(
                {
                    "full_text": "Deutsche Bank note",
                    "identity": {"source": "Deutsche Bank"},
                    "parse": {"backend": "docling"},
                }
            )
        )

    def test_empty_theme_lists_are_source_only(self):
        self.assertTrue(is_source_only_parsed_data({"themes": [], "trades": []}))

    def test_legacy_extraction_is_not_source_only(self):
        self.assertFalse(
            is_source_only_parsed_data(
                {"themes": [{"label": "term premium"}], "trades": []}
            )
        )

    def test_all_source_only_documents_fail_closed(self):
        documents = [
            {"parsed_data": {"identity": {}, "parse": {}}},
            {"parsed_data": {"full_text": "x"}},
        ]
        self.assertTrue(documents_are_source_only(documents))

    def test_mixed_legacy_and_source_only_is_not_all_source_only(self):
        documents = [
            {"parsed_data": {"identity": {}, "parse": {}}},
            {"parsed_data": {"themes": [{"label": "term premium"}]}},
        ]
        self.assertFalse(documents_are_source_only(documents))

    def test_empty_document_list_is_not_source_only(self):
        self.assertFalse(documents_are_source_only([]))


class SynthesisSignalTests(unittest.TestCase):
    def test_themes_count_as_signals(self):
        self.assertTrue(has_synthesis_signals({"themes": [{"label": "x"}]}))

    def test_assertions_count_without_themes(self):
        self.assertTrue(
            has_synthesis_signals({"themes": [], "assertions": [{"summary_text": "x"}]})
        )

    def test_empty_payload_has_no_signals(self):
        self.assertFalse(has_synthesis_signals({"themes": [], "trades": []}))


class ThroughlineSourceOnlyTests(unittest.TestCase):
    def test_source_only_rows_do_not_emit_themes_or_trades(self):
        payload = ThroughlineInputBuilder().build_from_legacy_documents(
            [
                {
                    "id": 79,
                    "document_name": "DB Q3 update",
                    "source": "Deutsche Bank",
                    "source_date": "2026-09-03",
                    "parsed_data": {
                        "full_text": "flows",
                        "identity": {"source": "Deutsche Bank"},
                        "parse": {"backend": "docling"},
                    },
                }
            ]
        )
        self.assertEqual(payload["themes"], [])
        self.assertEqual(payload["trades"], [])
        self.assertEqual(payload["document_count"], 1)
        self.assertEqual(payload["sources"], ["Deutsche Bank"])


class SynthesizerSkipTests(unittest.TestCase):
    def test_source_only_legacy_rows_skip_before_llm(self):
        synthesizer = Synthesizer()
        synthesizer._synthesize_monolithic = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("LLM should not run")
        )
        result = synthesizer.synthesize(
            [
                {
                    "id": 79,
                    "source": "Deutsche Bank",
                    "document_name": "DB Q3 update",
                    "parsed_data": {
                        "identity": {"source": "Deutsche Bank"},
                        "parse": {"backend": "docling"},
                        "full_text": "flows",
                    },
                }
            ]
        )
        self.assertIsNone(result)

    def test_assertion_only_batch_reaches_synthesis(self):
        synthesizer = Synthesizer(use_skill_pipeline=False)
        called = {}

        def fake_monolithic(input_data, document_count):
            called["assertions"] = input_data["assertions"]
            called["document_count"] = document_count
            return None

        synthesizer._synthesize_monolithic = fake_monolithic
        batch = DispatchBatch.from_dict(
            {
                "batch_key": "2026-09-03:source-only",
                "documents": [
                    {
                        "research_id": 79,
                        "document_name": "DB Q3 update",
                        "source": "Deutsche Bank",
                        "assertions": [
                            {
                                "summary_text": "Private buyers still absorb supply.",
                                "assertion_type": "claim",
                            }
                        ],
                    }
                ],
            }
        )
        synthesizer.synthesize(batch)
        self.assertEqual(called["document_count"], 1)
        self.assertEqual(
            called["assertions"][0]["summary_text"],
            "Private buyers still absorb supply.",
        )


class ParserModeLoadTests(unittest.TestCase):
    def test_parser_mode_fail_closes_on_source_only_rows(self):
        db_client = Mock()
        db_client.query_analysis.return_value = [
            {
                "id": 79,
                "parsed_data": {"identity": {}, "parse": {}, "full_text": "x"},
            }
        ]
        with self.assertRaisesRegex(ValueError, "DISPATCH_INPUT_MODE=analyst"):
            load_dispatch_documents(
                input_mode="parser",
                analyst_batch_path="",
                db_client=db_client,
            )

    def test_parser_mode_still_loads_legacy_extraction_rows(self):
        db_client = Mock()
        rows = [
            {
                "id": 1,
                "parsed_data": {"themes": [{"label": "term premium"}]},
            }
        ]
        db_client.query_analysis.return_value = rows
        data, batch, source_type = load_dispatch_documents(
            input_mode="parser",
            analyst_batch_path="",
            db_client=db_client,
        )
        self.assertEqual(data, rows)
        self.assertIsNone(batch)
        self.assertEqual(source_type, "parsed_research")


if __name__ == "__main__":
    unittest.main()
