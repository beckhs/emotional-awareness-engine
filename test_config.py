"""
test_config.py — Tests de configuración centralizada para v3.0.

Tests basados en el consenso del debate:
- USER_TZ = America/Lima
- Thresholds válidos
- Paths existentes
- Feature flags

ADAPTED to match actual config.py implementation.
"""
import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as engine_config
from emotional_state import DEFAULT_STATE, STATE_PATH
from conversation_analyzer import DB_PATH


# ─────────────────────────────────────────────────────────────────────────────
# Config module tests (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigModule(unittest.TestCase):
    """Tests for centralized config.py module."""

    def test_user_timezone(self):
        """USER_TZ should be America/Lima (Peru timezone)."""
        self.assertEqual(engine_config.USER_TZ, "America/Lima",
            "USER_TZ must be America/Lima (Peru)")

    def test_psych_confidence_threshold(self):
        """PSY_CONFIDENCE_THRESHOLD should be between 0 and 1."""
        self.assertGreater(engine_config.PSY_CONFIDENCE_THRESHOLD, 0)
        self.assertLess(engine_config.PSY_CONFIDENCE_THRESHOLD, 1)

    def test_psy_low_confidence(self):
        """PSY_LOW_CONFIDENCE should be less than PSY_CONFIDENCE_THRESHOLD."""
        self.assertLess(engine_config.PSY_LOW_CONFIDENCE,
                        engine_config.PSY_CONFIDENCE_THRESHOLD)

    def test_keyword_min_matches(self):
        """KEYWORD_MIN_MATCHES should be at least 1."""
        self.assertGreaterEqual(engine_config.KEYWORD_MIN_MATCHES, 1)

    def test_rate_limits_positive(self):
        """Rate limits should be positive."""
        self.assertGreater(engine_config.RATE_LIMIT_NORMAL, 0)
        self.assertGreater(engine_config.RATE_LIMIT_CONCERNED, 0)
        self.assertGreater(engine_config.RATE_LIMIT_CRISIS, 0)

    def test_rate_limits_ordering(self):
        """Rate limits: normal > concerned > crisis."""
        self.assertGreater(engine_config.RATE_LIMIT_NORMAL,
                           engine_config.RATE_LIMIT_CONCERNED)
        self.assertGreater(engine_config.RATE_LIMIT_CONCERNED,
                           engine_config.RATE_LIMIT_CRISIS)

    def test_max_daily_checkins(self):
        """MAX_DAILY_CHECKINS should be positive integer."""
        self.assertGreater(engine_config.MAX_DAILY_CHECKINS, 0)
        self.assertIsInstance(engine_config.MAX_DAILY_CHECKINS, int)

    def test_max_daily_concerned(self):
        """MAX_DAILY_CONCERNED should be >= MAX_DAILY_CHECKINS."""
        self.assertGreaterEqual(engine_config.MAX_DAILY_CONCERNED,
                                engine_config.MAX_DAILY_CHECKINS)

    def test_quiet_hours_range(self):
        """Quiet hours should be valid (0-23)."""
        self.assertGreaterEqual(engine_config.QUIET_HOURS_START, 0)
        self.assertLess(engine_config.QUIET_HOURS_START, 24)
        self.assertGreaterEqual(engine_config.QUIET_HOURS_END, 0)
        self.assertLess(engine_config.QUIET_HOURS_END, 24)

    def test_quiet_hours_peru_sleep(self):
        """Quiet hours should be 11 PM to 7 AM Peru time."""
        self.assertEqual(engine_config.QUIET_HOURS_START, 23,
            "Quiet hours start should be 11 PM Peru")
        self.assertEqual(engine_config.QUIET_HOURS_END, 7,
            "Quiet hours end should be 7 AM Peru")

    def test_morning_checkin_hour(self):
        """MORNING_CHECKIN_HOUR should be 9 AM Peru time."""
        self.assertEqual(engine_config.MORNING_CHECKIN_HOUR, 9,
            "Morning check-in should be at 9 AM Peru")

    def test_emotion_map_structure(self):
        """EMOTION_MAP maps pysentimiento emotions to engine vocabulary."""
        self.assertIn("joy", engine_config.EMOTION_MAP)
        self.assertIn("sadness", engine_config.EMOTION_MAP)
        self.assertIn("anger", engine_config.EMOTION_MAP)
        self.assertIn("others", engine_config.EMOTION_MAP)

    def test_emotion_map_values(self):
        """EMOTION_MAP maps to expected engine moods."""
        self.assertEqual(engine_config.EMOTION_MAP["joy"], "happy")
        self.assertEqual(engine_config.EMOTION_MAP["sadness"], "sad")
        self.assertEqual(engine_config.EMOTION_MAP["anger"], "frustrated")
        self.assertEqual(engine_config.EMOTION_MAP["others"], "neutral")

    def test_hermes_cooldown(self):
        """HERMES_COOLDOWN should be positive (seconds)."""
        self.assertGreater(engine_config.HERMES_COOLDOWN, 0)

    def test_lock_file_path(self):
        """LOCK_FILE should be a Path."""
        self.assertIsInstance(engine_config.LOCK_FILE, Path)

    def test_pysentimiento_lang(self):
        """PYSNTIMENTO_LANG should be 'es'."""
        self.assertEqual(engine_config.PYSNTIMENTO_LANG, "es")


# ─────────────────────────────────────────────────────────────────────────────
# v2.1 Config verification (existing paths and defaults)
# ─────────────────────────────────────────────────────────────────────────────

class TestExistingConfig(unittest.TestCase):
    """Tests for existing v2.1 configuration that must remain valid."""

    def test_state_path_is_hermes_dir(self):
        """STATE_PATH should be in ~/.hermes/."""
        self.assertIn(".hermes", str(STATE_PATH))

    def test_default_state_has_check_in_rules(self):
        """DEFAULT_STATE must have check_in_rules."""
        self.assertIn("check_in_rules", DEFAULT_STATE)

    def test_db_path_is_hermes_dir(self):
        """DB_PATH should be in ~/.hermes/."""
        self.assertIn(".hermes", str(DB_PATH))

    def test_mood_keywords_cover_5_moods(self):
        """MOOD_KEYWORDS should cover at least 5 mood categories."""
        from conversation_analyzer import MOOD_KEYWORDS
        self.assertGreaterEqual(len(MOOD_KEYWORDS), 5)
        expected_moods = {"stressed", "happy", "tired", "frustrated", "excited"}
        self.assertTrue(expected_moods.issubset(set(MOOD_KEYWORDS.keys())))

    def test_emotional_state_defaults(self):
        """DEFAULT_STATE should have all required keys."""
        required_keys = [
            "current_mood", "mood_intensity", "trend",
            "patterns", "significant_events", "last_interaction",
            "check_in_rules", "check_in_history", "spam_protection"
        ]
        for key in required_keys:
            self.assertIn(key, DEFAULT_STATE, f"DEFAULT_STATE missing key: {key}")


# ─────────────────────────────────────────────────────────────────────────────
# Timezone tests (F3 from debate)
# ─────────────────────────────────────────────────────────────────────────────

class TestTimezoneConfiguration(unittest.TestCase):
    """Tests for Peru timezone configuration (F3 from debate)."""

    def test_morning_checkin_is_9am_peru(self):
        """Morning check-in should be at 9 AM Peru time."""
        self.assertEqual(engine_config.MORNING_CHECKIN_HOUR, 9,
            "Morning check-in at 9 AM Peru (local time)")

    def test_quiet_hours_correspond_to_sleep(self):
        """Quiet hours 23-7 correspond to Peru sleeping hours."""
        # 11 PM to 7 AM is a reasonable sleep window
        self.assertEqual(engine_config.QUIET_HOURS_START, 23)
        self.assertEqual(engine_config.QUIET_HOURS_END, 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
