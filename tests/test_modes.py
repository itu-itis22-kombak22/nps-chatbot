from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from chatbot.modes import example, summary, topic
from tests.support import TraceTestCase


def mode_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "INPUT_AS_OF_DATE": "2024-02-01",
                "FIRST_MAIN_CATEGORY": "Mobil Bankacilik",
                "FIRST_SUBCATEGORY": "Hiz",
                "NPS_SCORE": 0,
                "EMOTION": "Kizgin",
                "COMMENT_TYPE": "Sikayet",
                "TEXT": "Mobil cok yavas.",
            },
            {
                "INPUT_AS_OF_DATE": "2024-02-02",
                "FIRST_MAIN_CATEGORY": "Mobil Bankacilik",
                "FIRST_SUBCATEGORY": "Fonksiyon",
                "NPS_SCORE": 7,
                "EMOTION": "Endiseli",
                "COMMENT_TYPE": "Talep/Oneri",
                "TEXT": "Mobil gelistirilebilir.",
            },
            {
                "INPUT_AS_OF_DATE": "2024-02-03",
                "FIRST_MAIN_CATEGORY": "Mobil Bankacilik",
                "FIRST_SUBCATEGORY": "Hiz",
                "NPS_SCORE": 10,
                "EMOTION": "Mutlu",
                "COMMENT_TYPE": "Memnuniyet",
                "TEXT": "Mobil iyi.",
            },
        ]
    )


class ExampleModeTests(TraceTestCase):
    def test_example_passes_exact_filters_and_uses_date_label(self):
        """Example mode query: exact filters reach data loader and response shows requested date."""
        captured = {}

        def fake_get_raw(**kwargs):
            captured.update(kwargs)
            return mode_rows()

        params = {
            "category": "Mobil Bankacilik",
            "date_start": "2024-02-01",
            "date_end": "2024-02-29",
            "date_label": "subat 2024",
            "nps_min": 0,
            "nps_max": 6,
            "limit": 2,
        }
        self.trace("MODE_PARAMS", params)
        with patch.object(example, "get_raw", side_effect=fake_get_raw):
            response = example.respond(params)

        self.trace("DATA_LOADER_KWARGS", captured)
        self.trace("MODE_RESPONSE", response)
        self.assertEqual(captured["date_start"], "2024-02-01")
        self.assertEqual(captured["date_end"], "2024-02-29")
        self.assertEqual(captured["nps_min"], 0)
        self.assertIn("subat 2024", response)
        self.assertIn("Ornek Yorumlar", response)

    def test_example_empty_dataset_returns_no_match_message(self):
        """Example mode empty result: user gets a no-match response."""
        params = {"category": "ATM"}
        self.trace("MODE_PARAMS", params)
        with patch.object(example, "get_raw", return_value=pd.DataFrame()):
            response = example.respond(params)
        self.trace("MODE_RESPONSE", response)
        self.assertIn("bulunamadi", response)

    def test_example_limit_is_capped_at_max_limit(self):
        """Example mode hard edge: user asks for too many comments, mode caps the limit."""
        rows = pd.concat([mode_rows()] * 10, ignore_index=True)
        params = {"limit": 999}
        self.trace("MODE_PARAMS", params)
        with patch.object(example, "get_raw", return_value=rows):
            response = example.respond(params)
        self.trace("MODE_RESPONSE_FIRST_LINES", response.splitlines()[:8])
        example_lines = [line for line in response.splitlines() if line.startswith("**") and ".**" in line]
        self.assertLessEqual(len(example_lines), example.MAX_LIMIT)


class SummaryModeTests(TraceTestCase):
    def test_summary_with_exact_date_bypasses_prepared_summary_and_falls_back_to_stats(self):
        """Summary mode query: exact date/filter queries compute raw stats instead of using prepared summaries."""
        params = {
            "period": "aylik",
            "date_start": "2024-02-01",
            "date_end": "2024-02-29",
            "date_label": "subat 2024",
        }
        self.trace("MODE_PARAMS", params)
        with patch.object(summary, "get_raw", return_value=mode_rows()) as get_raw, \
                patch.object(summary, "get_ozetler", side_effect=AssertionError("prepared summary should not be used")), \
                patch.object(summary, "chat", side_effect=RuntimeError("llm down")):
            response = summary.respond(params)

        self.trace("MODE_RESPONSE", response)
        get_raw.assert_called_once()
        self.assertIn("subat 2024 NPS Ozeti", response)
        self.assertIn("Toplam yorum", response)

    def test_summary_empty_filtered_data_returns_no_data_message(self):
        """Summary mode empty result: exact date outside data range is reported clearly."""
        params = {"date_start": "2026-01-01", "date_label": "ocak 2026"}
        self.trace("MODE_PARAMS", params)
        with patch.object(summary, "get_raw", return_value=pd.DataFrame()):
            response = summary.respond(params)
        self.trace("MODE_RESPONSE", response)
        self.assertIn("veri bulunamadi", response)


class TopicModeTests(TraceTestCase):
    def test_topic_passes_filters_and_falls_back_when_llm_fails(self):
        """Topic mode query: filters reach data loader and stats fallback remains readable."""
        captured = {}

        def fake_get_raw(**kwargs):
            captured.update(kwargs)
            return mode_rows()

        params = {
            "category": "Mobil Bankacilik",
            "comment_type": "Sikayet",
            "date_start": "2024-02-01",
            "date_end": "2024-02-29",
            "date_label": "subat 2024",
        }
        self.trace("MODE_PARAMS", params)
        with patch.object(topic, "get_raw", side_effect=fake_get_raw), \
                patch.object(topic, "chat", side_effect=RuntimeError("llm down")):
            response = topic.respond(params)

        self.trace("DATA_LOADER_KWARGS", captured)
        self.trace("MODE_RESPONSE", response)
        self.assertEqual(captured["category"], "Mobil Bankacilik")
        self.assertEqual(captured["comment_type"], "Sikayet")
        self.assertEqual(captured["date_start"], "2024-02-01")
        self.assertIn("Mobil Bankacilik / Sikayet Analizi", response)
        self.assertIn("subat 2024", response)

    def test_topic_empty_data_is_still_reported_in_fallback(self):
        """Topic mode empty result: fallback text explicitly says there is not enough data."""
        empty = mode_rows().iloc[0:0]
        params = {"category": "Kartlar", "date_label": "mart 2024"}
        self.trace("MODE_PARAMS", params)
        with patch.object(topic, "get_raw", return_value=empty), \
                patch.object(topic, "chat", side_effect=RuntimeError("llm down")):
            response = topic.respond(params)
        self.trace("MODE_RESPONSE", response)
        self.assertIn("yeterli veri yok", response)


if __name__ == "__main__":
    import unittest

    unittest.main()
