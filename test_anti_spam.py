"""
test_anti_spam.py — Tests for anti-spam protection in outreach_engine.py
"""
import unittest
import time
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from emotional_state import DEFAULT_STATE
from outreach_engine import _check_anti_spam, _update_spam_state


class TestAntiSpam(unittest.TestCase):
    """Tests for anti-spam logic."""

    def _make_state(self, consecutive=0, last_beck=0, final=False):
        """Helper to create a state with specific spam_protection values."""
        state = DEFAULT_STATE.copy()
        state["spam_protection"] = {
            "consecutive_unanswered": consecutive,
            "last_beck_message": last_beck,
            "final_message_sent": final,
        }
        return state

    def test_block_at_3_unanswered(self):
        """At 3 consecutive unanswered check-ins, should block with correct message."""
        state = self._make_state(consecutive=3, final=False)
        should_block, reason = _check_anti_spam(state)
        self.assertTrue(should_block)
        self.assertEqual(reason, "anti-spam: 3 check-ins sin respuesta")

    def test_reset_on_beck_message(self):
        """When Beck messages, counters reset to zero and final_message_sent is cleared."""
        state = self._make_state(consecutive=5, last_beck=time.time() - 999999, final=True)
        _update_spam_state(state, beck_messaged_today=True)
        spam = state["spam_protection"]
        self.assertEqual(spam["consecutive_unanswered"], 0)
        self.assertFalse(spam["final_message_sent"])
        # last_beck_message should be updated to "now"
        self.assertAlmostEqual(spam["last_beck_message"], time.time(), delta=2)

    def test_7day_final_message(self):
        """When last_beck_message > 7 days ago and no final sent, should allow and set final_message_sent."""
        nine_days_ago = time.time() - (9 * 86400)
        state = self._make_state(consecutive=2, last_beck=nine_days_ago, final=False)
        should_block, reason = _check_anti_spam(state)
        self.assertFalse(should_block)
        self.assertEqual(reason, "final_message")
        self.assertTrue(state["spam_protection"]["final_message_sent"])

    def test_permanent_silence_after_final(self):
        """After final_message_sent, 3+ unanswered should trigger permanent silence."""
        state = self._make_state(consecutive=3, final=True)
        should_block, reason = _check_anti_spam(state)
        self.assertTrue(should_block)
        self.assertEqual(reason, "anti-spam: silencio permanente")

    def test_counter_integrity(self):
        """Verify counter increments correctly over multiple check-in cycles."""
        state = self._make_state(consecutive=0)

        # Simulate 3 check-ins without Beck responding
        for expected in range(1, 4):
            _update_spam_state(state, beck_messaged_today=False)
            self.assertEqual(
                state["spam_protection"]["consecutive_unanswered"], expected,
                f"Expected {expected} unanswered, got {state['spam_protection']['consecutive_unanswered']}"
            )

        # Block should activate at 3
        should_block, reason = _check_anti_spam(state)
        self.assertTrue(should_block)

        # Beck messages → reset
        _update_spam_state(state, beck_messaged_today=True)
        self.assertEqual(state["spam_protection"]["consecutive_unanswered"], 0)

        # Send one more check-in → counter goes to 1
        _update_spam_state(state, beck_messaged_today=False)
        self.assertEqual(state["spam_protection"]["consecutive_unanswered"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
