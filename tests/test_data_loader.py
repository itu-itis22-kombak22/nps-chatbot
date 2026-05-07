from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from chatbot import data_loader as dl
from tests.support import TraceTestCase


def sample_raw() -> pd.DataFrame:
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
                "INPUT_AS_OF_DATE": "2024-02-29",
                "FIRST_MAIN_CATEGORY": "Mobil Bankacilik",
                "FIRST_SUBCATEGORY": "Fonksiyon",
                "NPS_SCORE": 7,
                "EMOTION": "Endiseli",
                "COMMENT_TYPE": "Sikayet",
                "TEXT": "Mobil hata verdi.",
            },
            {
                "INPUT_AS_OF_DATE": "2024-03-01",
                "FIRST_MAIN_CATEGORY": "ATM",
                "FIRST_SUBCATEGORY": "Para cekme",
                "NPS_SCORE": 10,
                "EMOTION": "Mutlu",
                "COMMENT_TYPE": "Memnuniyet",
                "TEXT": "ATM iyi.",
            },
            {
                "INPUT_AS_OF_DATE": "2024-03-10",
                "FIRST_MAIN_CATEGORY": "Mobil Bankacilik",
                "FIRST_SUBCATEGORY": "Kullanim",
                "NPS_SCORE": 9,
                "EMOTION": "Mutlu",
                "COMMENT_TYPE": "Talep/Oneri",
                "TEXT": "Mobil iyi.",
            },
        ]
    ).assign(INPUT_AS_OF_DATE=lambda df: pd.to_datetime(df["INPUT_AS_OF_DATE"]))


class DataLoaderFilterTests(TraceTestCase):
    def setUp(self):
        super().setUp()
        dl._load_raw_parquet.cache_clear()
        dl._load_ozetler.cache_clear()

    def test_exact_date_range_is_inclusive_of_end_day(self):
        """Data query: exact February range includes 2024-02-29."""
        filters = {
            "period": "aylik",
            "category": None,
            "segment": None,
            "emotion": None,
            "comment_type": None,
            "nps_min": None,
            "nps_max": None,
            "date_start": "2024-02-01",
            "date_end": "2024-02-29",
        }
        self.trace("DATA_QUERY", filters)
        df = dl._apply_filters(sample_raw(), **filters)
        self.trace("DATA_RESULT", df[["INPUT_AS_OF_DATE", "FIRST_MAIN_CATEGORY", "NPS_SCORE"]].to_dict("records"))
        self.assertEqual(len(df), 2)
        self.assertEqual(df["INPUT_AS_OF_DATE"].min().date().isoformat(), "2024-02-01")
        self.assertEqual(df["INPUT_AS_OF_DATE"].max().date().isoformat(), "2024-02-29")

    def test_exact_date_range_overrides_relative_period(self):
        """Data query: exact date range wins over relative period shortcuts."""
        filters = {
            "period": "gunluk",
            "category": None,
            "segment": None,
            "emotion": None,
            "comment_type": None,
            "nps_min": None,
            "nps_max": None,
            "date_start": "2024-02-01",
            "date_end": "2024-02-29",
        }
        self.trace("DATA_QUERY", filters)
        df = dl._apply_filters(sample_raw(), **filters)
        self.trace("DATA_RESULT_COUNT", len(df))
        self.assertEqual(len(df), 2)

    def test_category_segment_and_nps_filters_can_stack(self):
        """Data query: category + segment + emotion + type + NPS range stack together."""
        filters = {
            "period": None,
            "category": "Mobil Bankacilik",
            "segment": "Detractor",
            "emotion": "Kizgin",
            "comment_type": "Sikayet",
            "nps_min": 0,
            "nps_max": 6,
            "date_start": None,
            "date_end": None,
        }
        self.trace("DATA_QUERY", filters)
        df = dl._apply_filters(sample_raw(), **filters)
        self.trace("DATA_RESULT", df.to_dict("records"))
        self.assertEqual(len(df), 1)
        self.assertEqual(int(df.iloc[0]["NPS_SCORE"]), 0)

    def test_period_key_handles_turkish_and_ascii_spellings(self):
        """Period normalizer accepts Turkish-ish and ASCII spellings."""
        cases = ["aylik", "haftalik", "gunluk"]
        self.trace("PERIOD_KEYS", cases)
        self.assertEqual(dl._period_key("aylik"), "monthly")
        self.assertEqual(dl._period_key("haftalik"), "weekly")
        self.assertEqual(dl._period_key("gunluk"), "daily")

    def test_get_raw_uses_local_parquet_when_use_db_false(self):
        """Runtime data path: USE_DB=false routes to local parquet loader."""
        with patch.object(dl, "USE_DB", False), patch.object(dl, "_load_raw_parquet", return_value=sample_raw()):
            df = dl.get_raw(category="ATM")

        self.trace("DATA_RESULT", df.to_dict("records"))
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["FIRST_MAIN_CATEGORY"], "ATM")

    def test_get_ozetler_renames_known_columns_and_sorts_descending(self):
        """Prepared summaries: CSV columns are normalized and newest summary comes first."""
        csv_df = pd.DataFrame(
            {
                "Ozet Cesidi": ["Aylik Konu Ozeti", "Aylik Konu Ozeti"],
                "Tarih": ["2024-01-01", "2024-02-01"],
                "Ozet": ["Eski", "Yeni"],
            }
        )
        with patch("pandas.read_csv", return_value=csv_df):
            dl._load_ozetler.cache_clear()
            result = dl.get_ozetler(ozet_cesidi="Aylik Konu Ozeti")

        self.trace("OZETLER_RESULT", result.to_dict("records"))
        self.assertEqual(list(result.columns), ["OZET_CESIDI", "TARIH", "OZET"])
        self.assertEqual(result.iloc[0]["OZET"], "Yeni")


if __name__ == "__main__":
    import unittest

    unittest.main()
