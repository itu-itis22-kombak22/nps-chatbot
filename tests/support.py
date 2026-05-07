from __future__ import annotations

import pprint
import unittest


class TraceTestCase(unittest.TestCase):
    """Small unittest base that prints behavior-oriented traces to the terminal."""

    def setUp(self):
        super().setUp()
        print(f"\n\n=== {self.__class__.__name__}.{self._testMethodName} ===")
        if self.shortDescription():
            print(f"SCENARIO: {self.shortDescription()}")

    def trace(self, label: str, value):
        print(f"{label}: {pprint.pformat(value, width=140, sort_dicts=False)}")

    def trace_turn(self, router, user_text: str):
        print(f"USER> {user_text}")
        result = router.process(user_text)
        self.trace(
            "ROUTER_RESULT",
            {
                "mode": result.mode,
                "needs_data": result.needs_data,
                "response": result.response,
                "params": result.params,
                "structured_query": result.structured_query,
            },
        )
        self.trace(
            "ROUTER_STATE",
            {
                "state": router.current_state.name,
                "pending_mode": router.conv.pending_mode,
                "context": router.conv.context,
                "last_structured_query": router.conv.last_structured_query,
            },
        )
        return result


def traced_llm_responses(testcase: TraceTestCase, responses: list[dict]):
    """Return a side_effect function for intent_router._llm_extract."""

    queue = list(responses)

    def side_effect(text: str, conversation_context=None):
        testcase.trace("LLM_INPUT", {"text": text, "conversation_context": conversation_context})
        if not queue:
            raise AssertionError("No mock LLM response left for this turn")
        payload = queue.pop(0)
        testcase.trace("LLM_JSON", payload)
        return payload

    return side_effect
