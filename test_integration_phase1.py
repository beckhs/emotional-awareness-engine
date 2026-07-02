"""
test_integration_phase1.py — Phase 1 full pipeline integration test.

Covers:
  1. Mock conversations → analyze mood
  2. Store events in EventStore
  3. Trigger check-in → verify message references real events
  4. Verify anti-spam kicks in at 3 unanswered

This test exercises the complete Phase 1 flow without needing a real
Hermes state database, using mocked time and state.
"""
import sys
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from emotional_state import (
    DEFAULT_STATE, load_state, save_state, update_mood, add_event,
    should_check_in, get_check_in_status
)
from conversation_analyzer import (
    extract_emotional_keywords, analyze_conversation_mood,
    detect_significant_events, detect_communication_patterns
)
from event_store import EventStore
from outreach_engine import (
    _validate_message, _fallback_message, _extract_topic,
    _apply_rate_limiting, _check_anti_spam, _update_spam_state,
    _hours_since
)


class TestPhase1Integration(unittest.TestCase):
    """Full pipeline test: mock conversations → mood → events → check-in → anti-spam."""

    def setUp(self):
        """Create fresh EventStore and base state for each test."""
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.store = EventStore(filepath=self.tmp.name)

        self.state = DEFAULT_STATE.copy()
        self.state["spam_protection"] = {
            "consecutive_unanswered": 0,
            "last_beck_message": 0,
            "final_message_sent": False,
        }
        self.state["check_in_history"] = []

    def tearDown(self):
        """Cleanup temp files."""
        self.store.clear()
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    # ─── Helper: create mock conversation messages ──────────────────────

    def _mock_messages(self, texts, base_ts=None):
        """Create mock user messages with timestamps."""
        if base_ts is None:
            base_ts = time.time()
        messages = []
        for i, text in enumerate(texts):
            messages.append({
                "role": "user",
                "content": text,
                "timestamp": base_ts + (i * 60),  # 1 minute apart
            })
        return messages

    # ─── Step 1: Mood analysis from mock conversations ─────────────────

    def test_analyze_happy_conversation(self):
        """Happy conversation → mood='happy', intensity > 0."""
        msgs = self._mock_messages([
            "¡Genial! ¡Todo funcionó perfecto!",
            "Qué bien, logré terminar el deploy",
            "Excelente resultado, estoy súper contento",
        ])
        result = analyze_conversation_mood(msgs)
        self.assertEqual(result["mood"], "happy")
        self.assertGreater(result["intensity"], 0)
        self.assertIn("happy", result["scores"])

    def test_analyze_frustrated_conversation(self):
        """Frustrated conversation → mood='frustrated'."""
        msgs = self._mock_messages([
            "Otra vez el mismo error, no funciona",
            "Maldita sea, es un bug otra vez",
            "Estoy harto de esto, ya basta",
        ])
        result = analyze_conversation_mood(msgs)
        self.assertEqual(result["mood"], "frustrated")
        self.assertIn("frustrated", result["scores"])

    # ─── Step 2: Events stored in EventStore with scores ────────────────

    def test_store_emotional_events(self):
        """Significant events are stored in EventStore with scores."""
        ev1 = self.store.add_event(
            event_type="stress_spike",
            description="Multiple stress indicators: no puedo, estresado",
            score=0.8,
            mood="stressed",
        )
        ev2 = self.store.add_event(
            event_type="achievement",
            description="Deploy successful after 3 hours",
            score=0.9,
            mood="happy",
        )

        self.assertEqual(len(self.store), 2)
        self.assertAlmostEqual(ev1["score"], 0.8 * 0.4, places=4)
        self.assertAlmostEqual(ev2["score"], 0.9 * 0.4, places=4)

        # Verify recent events order
        recent = self.store.get_recent_events(limit=5)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["type"], "achievement")  # most recent

    # ─── Step 3: Check-in message references real events ────────────────

    def test_fallback_references_event_descriptions(self):
        """Fallback message with events references actual event descriptions."""
        self.store.add_event(
            event_type="stress_spike",
            description="Deploy de Proxmox falló a las 3 AM",
            score=0.9,
            mood="stressed",
        )
        self.store.add_event(
            event_type="achievement",
            description="Arreglé el engine finalmente",
            score=0.7,
            mood="happy",
        )

        events = self.store.get_recent_events(limit=5)

        # Generate fallback message with events
        msg = _fallback_message("stressed", "Proxmox", "declining", 12, events=events)

        # Should reference the top (most recent) event description
        # get_recent_events returns most recent first
        top_desc = events[0]["description"]
        self.assertIn(top_desc, msg,
                      f"Message '{msg}' should contain top event '{top_desc}'")
        self.assertGreater(len(msg), 20)

    def test_fallback_without_events_degrades_gracefully(self):
        """Fallback without EventStore events uses topic-based messages."""
        msg = _fallback_message("stressed", "Proxmox", "declining", 12, events=None)
        self.assertIn("Proxmox", msg)
        self.assertGreater(len(msg), 20)

    # ─── Step 4: Check-in triggering logic ──────────────────────────────

    def test_should_check_in_after_24h_silence(self):
        """After 25h silence with neutral mood → should check in (normal)."""
        self.state["last_interaction"]["mood"] = "neutral"
        self.state["last_interaction"]["timestamp"] = time.time() - (25 * 3600)

        with patch("emotional_state.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.strftime.return_value = "14"  # 2 PM
            result = should_check_in(self.state)

        self.assertTrue(result["should"])
        self.assertEqual(result["type"], "normal")

    def test_should_check_in_high_priority_bad_mood(self):
        """Bad mood + 8h+ silence → high priority check-in."""
        self.state["last_interaction"]["mood"] = "stressed"
        self.state["last_interaction"]["timestamp"] = time.time() - (9 * 3600)

        with patch("emotional_state.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.strftime.return_value = "14"
            result = should_check_in(self.state)

        self.assertTrue(result["should"])
        self.assertEqual(result["type"], "high_priority")

    # ─── Step 5: Anti-spam mechanism ────────────────────────────────────

    def test_anti_spam_blocks_at_3_unanswered(self):
        """3 consecutive unanswered check-ins → anti-spam blocks."""
        self.state["spam_protection"]["consecutive_unanswered"] = 3

        should_block, reason = _check_anti_spam(self.state)
        self.assertTrue(should_block)
        self.assertEqual(reason, "anti-spam: 3 check-ins sin respuesta")

    def test_anti_spam_counter_increments_correctly(self):
        """Each unanswered cycle increments counter; Beck messaging resets it."""
        spam = self.state["spam_protection"]

        # Simulate 3 unanswered check-ins
        for expected in range(1, 4):
            _update_spam_state(self.state, beck_messaged_today=False)
            self.assertEqual(spam["consecutive_unanswered"], expected)

        # At 3, anti-spam should block
        should_block, reason = _check_anti_spam(self.state)
        self.assertTrue(should_block, f"Should block at 3, got reason={reason}")

        # Beck messages → reset
        _update_spam_state(self.state, beck_messaged_today=True)
        self.assertEqual(spam["consecutive_unanswered"], 0)
        self.assertFalse(spam["final_message_sent"])

    def test_anti_spam_permanent_silence_after_final(self):
        """After final message sent + 3 unanswered → permanent silence."""
        spam = self.state["spam_protection"]
        spam["consecutive_unanswered"] = 3
        spam["final_message_sent"] = True

        should_block, reason = _check_anti_spam(self.state)
        self.assertTrue(should_block)
        self.assertEqual(reason, "anti-spam: silencio permanente")

    def test_anti_spam_7day_final_message(self):
        """7+ days without Beck → allows one final message."""
        spam = self.state["spam_protection"]
        spam["last_beck_message"] = time.time() - (9 * 86400)

        should_block, reason = _check_anti_spam(self.state)
        self.assertFalse(should_block)
        self.assertEqual(reason, "final_message")
        self.assertTrue(spam["final_message_sent"])  # flag set

    # ─── Step 6: Full end-to-end pipeline (mocked) ──────────────────────

    def test_full_pipeline_simulated(self):
        """Simulate full pipeline: messages → mood → events → check-in decision."""
        # 1. Mock conversations
        msgs = self._mock_messages([
            "Estoy estresado con el deploy, no puedo más",
            "Otra vez error, no funciona esta cosa",
            "¡Pero al final logré arreglarlo! ¡Genial!",
        ])

        # 2. Analyze mood
        mood = analyze_conversation_mood(msgs)
        self.assertIn(mood["mood"], ["stressed", "frustrated", "happy", "excited"])

        # 3. Detect events
        events = detect_significant_events(msgs)
        self.assertTrue(len(events) > 0, "Should detect at least one event")

        # 4. Store in EventStore
        for event in events:
            self.store.add_event(
                event_type=event["type"],
                description=event["description"],
                score=mood["intensity"],
                mood=event.get("mood", ""),
                topic=event.get("topic", ""),
            )
        self.assertGreater(len(self.store), 0)

        # 5. Update state
        update_mood(self.state, mood["mood"], mood["intensity"])
        self.assertEqual(self.state["current_mood"], mood["mood"])

        # 6. Simulate 25h silence → should trigger check-in
        self.state["last_interaction"]["timestamp"] = time.time() - (25 * 3600)
        self.state["last_interaction"]["mood"] = mood["mood"]

        with patch("emotional_state.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.strftime.return_value = "14"
            decision = should_check_in(self.state)

        self.assertTrue(decision["should"], f"Should trigger check-in: {decision}")

        # 7. Generate message referencing real events
        store_events = self.store.get_recent_events(limit=3)
        msg = _fallback_message(mood["mood"], "deploy", mood["mood"], 25,
                                events=store_events)
        self.assertGreater(len(msg), 20)
        self.assertTrue(
            any(e["description"][:30] in msg for e in store_events) or
            "deploy" in msg.lower(),
            f"Message should reference events or topic: {msg}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
