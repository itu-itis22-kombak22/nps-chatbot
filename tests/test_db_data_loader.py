from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from chatbot import data_loader as dl
from tests.support import TraceTestCase


def db_result() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "INPUT_AS_OF_DATE": ["2024-02-05"],
            "FIRST_MAIN_CATEGORY": ["Mobil Bankacilik"],
            "NPS_SCORE": [3],
        }
    )


class OracleDataLoaderTests(TraceTestCase):
    def test_load_raw_oracle_builds_sql_with_exact_date_and_filters(self):
        """DB query: exact dates and filters are converted to Oracle SQL."""
        captured = {}

        def fake_query(sql: str) -> pd.DataFrame:
            captured["sql"] = sql
            return db_result()

        query = {
            "period": "aylik",
            "category": "Mobil Bankacilik",
            "segment": "Detractor",
            "emotion": "Kizgin",
            "comment_type": "Sikayet",
            "nps_min": 0,
            "nps_max": 6,
            "date_start": "2024-02-01",
            "date_end": "2024-02-29",
        }
        self.trace("DB_QUERY", query)

        with patch.object(dl, "ORACLE_TABLE", "NPS_TABLE"), patch.object(dl, "_query_oracle", side_effect=fake_query):
            result = dl._load_raw_oracle(**query)

        self.trace("GENERATED_SQL", captured["sql"])
        self.trace("DB_RESULT", result.to_dict("records"))
        sql = captured["sql"]
        self.assertIn("SELECT * FROM NPS_TABLE WHERE", sql)
        self.assertIn("INPUT_AS_OF_DATE >= DATE '2024-02-01'", sql)
        self.assertIn("INPUT_AS_OF_DATE < DATE '2024-02-29' + 1", sql)
        self.assertIn("UPPER(FIRST_MAIN_CATEGORY) = UPPER('Mobil Bankacilik')", sql)
        self.assertIn("UPPER(EMOTION) = UPPER('Kizgin')", sql)
        self.assertIn("UPPER(COMMENT_TYPE) = UPPER('Sikayet')", sql)
        self.assertIn("NPS_SCORE >= 0", sql)
        self.assertIn("NPS_SCORE <= 6", sql)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["INPUT_AS_OF_DATE"]))

    def test_load_raw_oracle_uses_relative_period_only_without_exact_dates(self):
        """DB query: relative period is used only when exact dates are absent."""
        captured = {}

        def fake_query(sql: str) -> pd.DataFrame:
            captured["sql"] = sql
            return db_result()

        query = {
            "period": "haftalik",
            "category": None,
            "segment": None,
            "emotion": None,
            "comment_type": None,
            "nps_min": None,
            "nps_max": None,
            "date_start": None,
            "date_end": None,
        }
        self.trace("DB_QUERY", query)

        with patch.object(dl, "ORACLE_TABLE", "NPS_TABLE"), patch.object(dl, "_query_oracle", side_effect=fake_query):
            dl._load_raw_oracle(**query)

        self.trace("GENERATED_SQL", captured["sql"])
        self.assertIn("INPUT_AS_OF_DATE >= SYSDATE - 7", captured["sql"])

    def test_get_raw_routes_to_oracle_when_use_db_true(self):
        """Runtime data path: USE_DB=true delegates to the Oracle loader."""
        query = {"period": "aylik", "date_start": "2024-02-01", "date_end": "2024-02-29"}
        self.trace("GET_RAW_QUERY", query)
        with patch.object(dl, "USE_DB", True), patch.object(dl, "_load_raw_oracle", return_value=db_result()) as oracle:
            result = dl.get_raw(**query)

        self.trace("DB_RESULT", result.to_dict("records"))
        oracle.assert_called_once()
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
