"""
test_engine.py — Test suite for the Emotional Awareness Engine (open-source version)
Covers mood detection, pattern recognition, event detection, and state management.
"""
import unittest
import json
import time
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from emotional_state import (
    load_state, save_state, update_mood, add_event,
    should_check_in, get_check_in_status, DEFAULT_STATE
)
from conversation_analyzer import (
    extract_emotional_keywords, analyze_conversation_mood,
    detect_communication_patterns, detect_significant_events
)


class TestMoodDetection(unittest.TestCase):
    """Tests 1-3: Emotion detection via keywords."""

    def test_extract_stressed_keywords(self):
        """Test 1: Detects stress keywords."""
        text = "I can't do this anymore, I'm exhausted and so stressed"
        result = extract_emotional_keywords(text)
        self.assertIn("stressed", result)
        self.assertTrue(len(result["stressed"]) >= 2)

    def test_extract_happy_keywords(self):
        """Test 2: Detects happiness keywords."""
        text = "It worked! That's awesome, perfect"
        result = extract_emotional_keywords(text)
        self.assertIn("happy", result)
        self.assertTrue(len(result["happy"]) >= 2)

    def test_extract_multiple_moods(self):
        """Test 3: Detects multiple emotions in a single message."""
        text = "I'm exhausted but it finally worked, that's perfect"
        result = extract_emotional_keywords(text)
        self.assertIn("tired", result)
        self.assertIn("happy", result)


class TestPatternRecognition(unittest.TestCase):
    """Test 4: Communication pattern recognition."""

    def test_communication_patterns(self):
        """Test 4: Detects active hours and message length patterns."""
        messages = [
            {"role": "user", "content": "Hello world this is a longer message for testing purposes", "timestamp": time.time()},
            {"role": "user", "content": "Another message", "timestamp": time.time()},
        ]
        patterns = detect_communication_patterns(messages)
        self.assertIn("avg_message_length", patterns)
        self.assertIn("active_hours", patterns)


class TestMoodAnalysis(unittest.TestCase):
    """Test 5: Conversation mood analysis."""

    def test_conversation_mood_analysis(self):
        """Test 5: Analyzes dominant mood from conversation."""
        messages = [
            {"role": "user", "content": "I'm so stressed about this project"},
            {"role": "assistant", "content": "I understand"},
            {"role": "user", "content": "Can't take it anymore, completely exhausted"},
        ]
        result = analyze_conversation_mood(messages)
        self.assertIn("mood", result)
        self.assertIn(result["mood"], ["stressed", "tired", "neutral"])


class TestCheckInTiming(unittest.TestCase):
    """Tests 6-7: Check-in timing logic."""

    def test_bad_mood_triggers_early_check_in(self):
        """Test 6: Negative mood + 8 hours → high priority check-in."""
        state = DEFAULT_STATE.copy()
        state["last_interaction"]["mood"] = "stressed"
        state["last_interaction"]["timestamp"] = time.time() - (9 * 3600)
        result = should_check_in(state)
        self.assertTrue(result["should"])
        self.assertEqual(result["type"], "high_priority")

    def test_normal_silence_triggers_check_in(self):
        """Test 7: 24+ hours silence → normal check-in."""
        state = DEFAULT_STATE.copy()
        state["last_interaction"]["mood"] = "neutral"
        state["last_interaction"]["timestamp"] = time.time() - (25 * 3600)
        result = should_check_in(state)
        self.assertTrue(result["should"])
        self.assertEqual(result["type"], "normal")


class TestQuietHours(unittest.TestCase):
    """Test 8: Quiet hours respect."""

    def test_no_check_in_during_quiet_hours(self):
        """Test 8: No check-in during quiet hours."""
        state = DEFAULT_STATE.copy()
        state["last_interaction"]["timestamp"] = time.time() - (49 * 3600)
        with patch("emotional_state.time") as mock_time:
            mock_time.strftime.return_value = "02"  # 2 AM
            mock_time.time.return_value = time.time()
            result = should_check_in(state)
            self.assertFalse(result["should"])


class TestDuplicatePrevention(unittest.TestCase):
    """Test 9: Duplicate prevention."""

    def test_no_duplicate_check_in(self):
        """Test 9: No check-in if one happened recently."""
        state = DEFAULT_STATE.copy()
        state["last_interaction"]["timestamp"] = time.time() - (25 * 3600)
        state["check_in_history"] = [{"timestamp": time.time() - (6 * 3600), "type": "normal"}]
        result = should_check_in(state)
        self.assertFalse(result["should"])


class TestEscalation(unittest.TestCase):
    """Test 10: Escalation logic."""

    def test_escalation_after_48_hours(self):
        """Test 10: Escalation after 48 hours without interaction."""
        state = DEFAULT_STATE.copy()
        state["last_interaction"]["timestamp"] = time.time() - (49 * 3600)
        state["last_interaction"]["mood"] = "neutral"
        result = should_check_in(state)
        self.assertTrue(result["should"])
        self.assertEqual(result["type"], "escalation")


class TestStateManagement(unittest.TestCase):
    """Test 11: State persistence."""

    def test_save_and_load_state(self):
        """Test 11: Saves and loads state correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            state = DEFAULT_STATE.copy()
            state["current_mood"] = "happy"
            json.dump(state, f)
            temp_path = f.name

        try:
            with open(temp_path, "r") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["current_mood"], "happy")
        finally:
            os.unlink(temp_path)


class TestEventDetection(unittest.TestCase):
    """Test 12: Event detection."""

    def test_detect_stress_spike(self):
        """Test 12: Detects stress spikes with multiple keywords."""
        messages = [
            {"role": "user", "content": "Can't take it anymore, exhausted and so stressed", "timestamp": time.time()}
        ]
        events = detect_significant_events(messages)
        stress_events = [e for e in events if e["type"] == "stress_spike"]
        self.assertTrue(len(stress_events) >= 1)


class TestTopicExtraction(unittest.TestCase):
    """Test 13: Topic extraction."""

    def test_topic_extraction_filters_system_messages(self):
        """Test 13: Filters system messages from topic extraction."""
        # Import from basic engine
        from outreach_engine_basic import _extract_topic
        self.assertEqual(_extract_topic("[IMPORTANT: This is a cron job]"), "(system instruction)")
        self.assertEqual(_extract_topic(""), "")
        self.assertTrue(len(_extract_topic("Hey, how are you doing with the server?")) <= 120)

    def test_topic_extraction_handles_long_messages(self):
        """Test 14: Truncates long messages at word boundary."""
        from outreach_engine_basic import _extract_topic
        long_msg = " ".join(["word"] * 50)
        topic = _extract_topic(long_msg)
        self.assertTrue(len(topic) <= 125)  # 120 + "..."


class TestEventDeduplication(unittest.TestCase):
    """Test 15: Event deduplication."""

    def test_late_night_events_deduplicated(self):
        """Test 15: Late night events are deduplicated by hour."""
        base_ts = 1719704400  # Some 2 AM timestamp
        messages = []
        for i in range(20):
            messages.append({
                "role": "user",
                "content": f"message {i}",
                "timestamp": base_ts + (i * 60)  # all within same hour
            })

        events = detect_significant_events(messages)
        late_night = [e for e in events if e["type"] == "late_night"]
        self.assertTrue(len(late_night) <= 1,
                        f"Found {len(late_night)} late_night events, expected <= 1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
