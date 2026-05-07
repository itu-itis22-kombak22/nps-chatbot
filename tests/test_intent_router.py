from __future__ import annotations

from unittest.mock import patch

from chatbot import intent_router as ir
from tests.support import TraceTestCase, traced_llm_responses


def llm_payload(message_type, target_mode="none", confidence=0.9, slots=None, **extra):
    payload = {
        "message_type": message_type,
        "target_mode": target_mode,
        "confidence": confidence,
        "slots": {
            "date_expression": None,
            "metric": None,
            "category": None,
            "subcategory": None,
            "segment": None,
            "nps_min": None,
            "nps_max": None,
            "emotion": None,
            "comment_type": None,
            "output_type": None,
            "limit": None,
            "customer_id": None,
        },
        "requires_confirmation": False,
        "assistant_message": None,
        "_source": "test",
    }
    if slots:
        payload["slots"].update(slots)
    payload.update(extra)
    return payload


def output_snapshot(output: ir.RouterOutput) -> dict:
    return {
        "message_type": output.message_type,
        "target_mode": output.target_mode,
        "action": output.action,
        "complete": output.complete,
        "missing_slots": output.missing_slots,
        "slots": output.slots,
        "structured_query": None if output.structured_query is None else {
            "analysis_type": output.structured_query.analysis_type,
            "date_range": output.structured_query.date_range,
            "filters": output.structured_query.filters,
            "output": output.structured_query.output,
        },
    }


class DateNormalizationTests(TraceTestCase):
    def test_month_year_variants_normalize_to_full_month(self):
        """Hard date parser cases: suffixes, reversed order, leap-year February."""
        cases = ["subat 2024", "2024 subat", "subattan 2024", "subat ayinda 2024"]
        for raw in cases:
            with self.subTest(raw=raw):
                date_range, period = ir._normalize_date_expression(raw)
                self.trace("DATE_NORMALIZE", {"raw": raw, "date_range": date_range, "period": period})
                self.assertEqual(date_range["start"], "2024-02-01")
                self.assertEqual(date_range["end"], "2024-02-29")
                self.assertEqual(date_range["grain"], "month")
                self.assertIn("ay", period)

    def test_relative_ranges_are_based_on_supplied_today(self):
        """Relative date expressions should be deterministic when today is injected."""
        today = ir.date(2026, 5, 7)

        date_range, period = ir._normalize_date_expression("son 1 ay", today=today)
        self.trace("DATE_NORMALIZE", {"raw": "son 1 ay", "today": today.isoformat(), "date_range": date_range, "period": period})
        self.assertEqual(date_range["start"], "2026-04-07")
        self.assertEqual(date_range["end"], "2026-05-07")

        week_range, week_period = ir._normalize_date_expression("gecen hafta", today=today)
        self.trace("DATE_NORMALIZE", {"raw": "gecen hafta", "today": today.isoformat(), "date_range": week_range, "period": week_period})
        self.assertEqual(week_range["start"], "2026-04-27")
        self.assertEqual(week_range["end"], "2026-05-03")


class RouterValidationTests(TraceTestCase):
    def validate(self, payload):
        self.trace("LLM_JSON", payload)
        output = ir._validate_and_complete(payload)
        self.trace("ROUTER_OUTPUT", output_snapshot(output))
        return output

    def test_summary_with_date_is_ready_to_run(self):
        """Minimum viable summary query: target mode plus date."""
        output = self.validate(
            llm_payload("analytics", "summary", slots={"date_expression": "subat 2024"})
        )
        self.assertTrue(output.complete)
        self.assertEqual(output.action, "run_query")
        self.assertEqual(output.missing_slots, [])
        self.assertEqual(output.structured_query.date_range["start"], "2024-02-01")

    def test_summary_without_date_asks_detail(self):
        """Summary is not allowed to run without a date range."""
        output = self.validate(llm_payload("analytics", "summary"))
        self.assertFalse(output.complete)
        self.assertEqual(output.action, "ask_detail")
        self.assertEqual(output.missing_slots, ["date_range"])

    def test_month_without_year_asks_for_year(self):
        """Month-only date should ask for the missing year instead of guessing."""
        output = self.validate(
            llm_payload("analytics", "summary", slots={"date_expression": "subat"})
        )
        self.assertFalse(output.complete)
        self.assertEqual(output.missing_slots, ["date_year"])

    def test_low_confidence_forces_target_mode_clarification(self):
        """Even if slots look valid, low confidence should not run the query."""
        output = self.validate(
            llm_payload(
                "analytics",
                "summary",
                confidence=0.2,
                slots={"date_expression": "subat 2024"},
            )
        )
        self.assertFalse(output.complete)
        self.assertIn("target_mode", output.missing_slots)

    def test_example_requires_filter_and_date(self):
        """Example queries should not run on a vague global corpus request."""
        no_filter = self.validate(
            llm_payload("analytics", "example", slots={"date_expression": "subat 2024"})
        )
        self.assertFalse(no_filter.complete)
        self.assertEqual(no_filter.missing_slots, ["filter"])

        no_date = self.validate(
            llm_payload("analytics", "example", slots={"category": "mobil bankacilik"})
        )
        self.assertFalse(no_date.complete)
        self.assertIn("date_range", no_date.missing_slots)

    def test_nps_range_maps_to_detractor_segment(self):
        """NPS 0-6 is deterministically converted to Detractor."""
        output = self.validate(
            llm_payload(
                "analytics",
                "summary",
                slots={"date_expression": "subat 2024", "nps_min": 0, "nps_max": 6},
            )
        )
        filters = output.structured_query.filters
        self.assertEqual(filters["nps_segment"], "Detractor")
        self.assertEqual(filters["nps_min"], 0)
        self.assertEqual(filters["nps_max"], 6)

    def test_non_analytics_is_answer_action(self):
        """Small talk/help/out-of-scope never becomes a data query."""
        output = self.validate(llm_payload("small_talk", assistant_message="Merhaba"))
        self.assertTrue(output.complete)
        self.assertEqual(output.action, "answer")
        self.assertEqual(output.target_mode, "none")


class RouterMemoryFlowTests(TraceTestCase):
    def test_collects_missing_date_in_detail_then_runs_example(self):
        """Multi-turn: first turn has filter but no date; second turn supplies only date."""
        responses = [
            llm_payload(
                "analytics",
                "example",
                slots={"category": "mobil bankacilik", "comment_type": "sikayet", "limit": 3},
            ),
            llm_payload(
                "analytics",
                "none",
                slots={"date_expression": "subat 2024"},
            ),
        ]

        with patch.object(ir, "_llm_extract", side_effect=traced_llm_responses(self, responses)):
            router = ir.IntentRouter()
            first = self.trace_turn(router, "mobil bankacilik sikayetlerinden 3 yorum getir")
            second = self.trace_turn(router, "subat 2024")

        self.assertEqual(first.mode, "detail")
        self.assertEqual(second.mode, "example")
        self.assertTrue(second.needs_data)
        self.assertEqual(second.params["date_start"], "2024-02-01")
        self.assertEqual(second.params["date_end"], "2024-02-29")
        self.assertIn("Mobil", second.params["category"])
        self.assertEqual(second.params["limit"], 3)

    def test_followup_inherits_previous_mode_category_limit_and_year(self):
        """Multi-turn memory: 'subattan da getir' inherits mode/category/type/limit and previous year."""
        responses = [
            llm_payload(
                "analytics",
                "example",
                slots={
                    "date_expression": "ocak 2024",
                    "category": "mobil bankacilik",
                    "comment_type": "sikayet",
                    "limit": 3,
                },
            ),
            llm_payload(
                "ambiguous",
                "none",
                confidence=0.4,
                slots={"date_expression": "subat"},
                assistant_message="Hangi analizi istiyorsunuz?",
            ),
        ]

        with patch.object(ir, "_llm_extract", side_effect=traced_llm_responses(self, responses)):
            router = ir.IntentRouter()
            first = self.trace_turn(router, "ocak 2024 mobil bankacilik 3 sikayet yorumu getir")
            router.conv.state = ir.State.DIRECT
            second = self.trace_turn(router, "subattan da getir")

        self.assertEqual(first.mode, "example")
        self.assertEqual(second.mode, "example")
        self.assertTrue(second.needs_data)
        self.assertEqual(second.params["date_start"], "2024-02-01")
        self.assertEqual(second.params["date_end"], "2024-02-29")
        self.assertEqual(second.params["limit"], 3)
        self.assertIn("Mobil", second.params["category"])

    def test_user_changes_category_but_keeps_previous_date_and_mode(self):
        """Follow-up: user changes only category; router should keep date and target mode from memory."""
        responses = [
            llm_payload(
                "analytics",
                "topic",
                slots={"date_expression": "mart 2024", "category": "mobil bankacilik", "comment_type": "sikayet"},
            ),
            llm_payload(
                "ambiguous",
                "none",
                confidence=0.5,
                slots={"category": "atm"},
            ),
        ]

        with patch.object(ir, "_llm_extract", side_effect=traced_llm_responses(self, responses)):
            router = ir.IntentRouter()
            first = self.trace_turn(router, "mart 2024 mobil bankacilik sikayet analizi")
            router.conv.state = ir.State.DIRECT
            second = self.trace_turn(router, "atm icin de ayni analiz")

        self.assertEqual(first.mode, "topic")
        self.assertEqual(second.mode, "topic")
        self.assertEqual(second.params["date_start"], "2024-03-01")
        self.assertEqual(second.params["date_end"], "2024-03-31")
        self.assertEqual(second.params["category"], "ATM")
        self.assertEqual(second.params["comment_type"], first.params["comment_type"])

    def test_reset_clears_memory_so_elliptic_followup_cannot_run(self):
        """After reset, an elliptic message like 'subattan da getir' should not inherit old query memory."""
        responses = [
            llm_payload(
                "analytics",
                "example",
                slots={"date_expression": "ocak 2024", "category": "mobil bankacilik"},
            ),
            llm_payload(
                "ambiguous",
                "none",
                confidence=0.4,
                slots={"date_expression": "subat"},
                assistant_message="Hangi analizi istiyorsunuz?",
            ),
        ]

        with patch.object(ir, "_llm_extract", side_effect=traced_llm_responses(self, responses)):
            router = ir.IntentRouter()
            first = self.trace_turn(router, "ocak 2024 mobil bankacilik yorumlari")
            router.reset()
            second = self.trace_turn(router, "subattan da getir")

        self.assertEqual(first.mode, "example")
        self.assertEqual(second.mode, "nonsense")
        self.assertFalse(second.needs_data)
        self.assertEqual(router.current_state, ir.State.DIRECT)

    def test_detail_state_allows_one_bad_answer_then_resets_on_second(self):
        """DETAIL tolerance: one bad clarification answer is allowed, second one resets the flow."""
        responses = [
            llm_payload("analytics", "summary"),
            llm_payload("ambiguous", "none", confidence=0.2, assistant_message="Net degil."),
            llm_payload("ambiguous", "none", confidence=0.2, assistant_message="Hala net degil."),
        ]

        with patch.object(ir, "_llm_extract", side_effect=traced_llm_responses(self, responses)):
            router = ir.IntentRouter()
            start = self.trace_turn(router, "nps ozet")
            first_bad = self.trace_turn(router, "bilmiyorum")
            second_bad = self.trace_turn(router, "hala bilmiyorum")

        self.assertEqual(start.mode, "detail")
        self.assertEqual(first_bad.mode, "detail")
        self.assertEqual(second_bad.mode, "nonsense")
        self.assertEqual(router.current_state, ir.State.DIRECT)

    def test_confirmation_acceptance_runs_pending_query(self):
        """Confirmation state: 'tamam' should execute the pending structured query."""
        router = ir.IntentRouter()
        router.conv.state = ir.State.DETAIL
        router.conv.pending_mode = "summary"
        router.conv.pending_params = {"date_start": "2024-02-01"}
        router.conv.last_structured_query = {"analysis_type": "summary"}

        result = self.trace_turn(router, "tamam")

        self.assertEqual(result.mode, "summary")
        self.assertTrue(result.needs_data)
        self.assertEqual(router.current_state, ir.State.RESPONSE)


if __name__ == "__main__":
    import unittest

    unittest.main()
