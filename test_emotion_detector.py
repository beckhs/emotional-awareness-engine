"""
test_emotion_detector.py — Tests for the 3 emotion detectors:
  - KeywordDetector: backward-compatible keyword detection
  - PysentimientoDetector: ML-based detection (lazy-loaded)
  - HybridDetector: best of both worlds

Tests cover: sarcasm, negation, Peruvian slang, mixed emotions,
irony detection, fallback logic.
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from emotion_detector import (
    EmotionDetector, KeywordDetector, PysentimientoDetector,
    HybridDetector, EmotionResult, ConversationMoodResult,
)


# ═══════════════════════════════════════════════════
# KeywordDetector Tests
# ═══════════════════════════════════════════════════

class TestKeywordDetector(unittest.TestCase):
    """Tests for the keyword-based detector (backward compatibility)."""

    def setUp(self):
        self.detector = KeywordDetector()

    def test_happy_detection(self):
        """Detects happy mood from positive keywords."""
        result = self.detector.detect_text("Genial, funcionó perfecto")
        self.assertEqual(result.mood, "happy")
        self.assertGreater(result.intensity, 0)
        self.assertEqual(result.source, "keyword")

    def test_stressed_detection(self):
        """Detects stressed mood from stress keywords."""
        result = self.detector.detect_text("No puedo más, estoy agotado y estresado")
        self.assertEqual(result.mood, "stressed")
        self.assertGreater(result.intensity, 0)

    def test_frustrated_detection(self):
        """Detects frustrated mood."""
        result = self.detector.detect_text("Otra vez el mismo error, no funciona")
        self.assertEqual(result.mood, "frustrated")

    def test_neutral_empty_text(self):
        """Empty text returns neutral."""
        result = self.detector.detect_text("")
        self.assertEqual(result.mood, "neutral")
        self.assertEqual(result.intensity, 0.0)

    def test_neutral_no_keywords(self):
        """Text without emotional keywords returns neutral."""
        result = self.detector.detect_text("El servidor tiene 16GB de RAM")
        self.assertEqual(result.mood, "neutral")

    def test_neutral_spanish_fantastico(self):
        """Test neutral Spanish 'increíble' → happy."""
        result = self.detector.detect_text("Qué increíble quedó todo")
        self.assertEqual(result.mood, "happy")

    def test_neutral_spanish_feliz(self):
        """Test neutral Spanish 'feliz' → happy."""
        result = self.detector.detect_text("Estoy muy feliz con el resultado")
        self.assertEqual(result.mood, "happy")

    def test_sarcasm_false_positive(self):
        """v3.0: keyword detector now prefers negative mood on tie.
        'genial, todo falló' → frustrated (not happy) because negative
        moods win on tie count."""
        result = self.detector.detect_text("Genial, todo falló")
        self.assertEqual(result.mood, "frustrated")
        self.assertEqual(result.source, "keyword")

    def test_conversation_mood(self):
        """KeywordDetector.detect_conversation aggregates moods."""
        messages = [
            {"role": "user", "content": "Estoy estresado con el proyecto"},
            {"role": "assistant", "content": "Entiendo"},
            {"role": "user", "content": "No puedo más, estoy agotado"},
        ]
        result = self.detector.detect_conversation(messages, recency_weighted=False)
        self.assertIn(result.mood, ["stressed", "tired"])
        self.assertGreater(result.intensity, 0)


# ═══════════════════════════════════════════════════
# PysentimientoDetector Tests
# ═══════════════════════════════════════════════════

class _MockPrediction:
    """Mock pysentimiento prediction result."""
    def __init__(self, output, probas):
        self.output = output
        self.probas = probas


class TestPysentimientoDetector(unittest.TestCase):
    """Tests for pysentimiento detector with mocked models."""

    def _make_detector_with_mocks(self, emotion_out, emotion_probas,
                                   sentiment_out, sentiment_probas,
                                   irony_out):
        """Create a PysentimientoDetector with mocked analyzers."""
        detector = PysentimientoDetector()
        detector._loaded = True
        detector._emotion_analyzer = MagicMock()
        detector._emotion_analyzer.predict.return_value = _MockPrediction(
            emotion_out, emotion_probas
        )
        detector._sentiment_analyzer = MagicMock()
        detector._sentiment_analyzer.predict.return_value = _MockPrediction(
            sentiment_out, sentiment_probas
        )
        detector._irony_analyzer = MagicMock()
        detector._irony_analyzer.predict.return_value = _MockPrediction(
            irony_out, {'irony': 0.8, 'not_irony': 0.2}
        )
        return detector

    def test_joy_maps_to_happy(self):
        """pysentimiento 'joy' → engine 'happy'."""
        detector = self._make_detector_with_mocks(
            'joy', {'joy': 0.9, 'sadness': 0.05, 'anger': 0.02,
                     'surprise': 0.01, 'fear': 0.01, 'disgust': 0.005, 'others': 0.005},
            'POS', {'POS': 0.9, 'NEU': 0.05, 'NEG': 0.05},
            'not_irony'
        )
        result = detector.detect_text("¡Qué bakan quedó el proyecto!")
        self.assertEqual(result.mood, "happy")
        self.assertEqual(result.source, "pysentimiento")
        self.assertFalse(result.is_ironic)

    def test_sadness_maps_to_sad(self):
        """pysentimiento 'sadness' → engine 'sad'."""
        detector = self._make_detector_with_mocks(
            'sadness', {'joy': 0.05, 'sadness': 0.85, 'anger': 0.03,
                         'surprise': 0.02, 'fear': 0.02, 'disgust': 0.01, 'others': 0.02},
            'NEG', {'POS': 0.05, 'NEU': 0.1, 'NEG': 0.85},
            'not_irony'
        )
        result = detector.detect_text("No estoy bien")
        self.assertEqual(result.mood, "sad")

    def test_anger_maps_to_frustrated(self):
        """pysentimiento 'anger' → engine 'frustrated'."""
        detector = self._make_detector_with_mocks(
            'anger', {'joy': 0.02, 'sadness': 0.05, 'anger': 0.85,
                      'surprise': 0.02, 'fear': 0.02, 'disgust': 0.02, 'others': 0.02},
            'NEG', {'POS': 0.02, 'NEU': 0.08, 'NEG': 0.9},
            'not_irony'
        )
        result = detector.detect_text("Maldita sea, esto no funciona")
        self.assertEqual(result.mood, "frustrated")

    def test_irony_overrides_to_frustrated(self):
        """Irony + NEG sentiment → override mood to 'frustrated'."""
        detector = self._make_detector_with_mocks(
            'joy', {'joy': 0.7, 'sadness': 0.1, 'anger': 0.05,
                     'surprise': 0.05, 'fear': 0.03, 'disgust': 0.04, 'others': 0.03},
            'NEG', {'POS': 0.1, 'NEU': 0.2, 'NEG': 0.7},
            'irony'
        )
        result = detector.detect_text("Genial, todo falló")
        self.assertEqual(result.mood, "frustrated")
        self.assertTrue(result.is_ironic)

    def test_fear_maps_to_anxious(self):
        """pysentimiento 'fear' → engine 'anxious'."""
        detector = self._make_detector_with_mocks(
            'fear', {'joy': 0.02, 'sadness': 0.1, 'anger': 0.05,
                     'surprise': 0.03, 'fear': 0.75, 'disgust': 0.02, 'others': 0.03},
            'NEG', {'POS': 0.05, 'NEU': 0.15, 'NEG': 0.8},
            'not_irony'
        )
        result = detector.detect_text("Tengo miedo de que falle")
        self.assertEqual(result.mood, "anxious")

    def test_disgust_maps_to_frustrated(self):
        """pysentimiento 'disgust' → engine 'frustrated'."""
        detector = self._make_detector_with_mocks(
            'disgust', {'joy': 0.02, 'sadness': 0.05, 'anger': 0.1,
                        'surprise': 0.02, 'fear': 0.02, 'disgust': 0.75, 'others': 0.04},
            'NEG', {'POS': 0.02, 'NEU': 0.08, 'NEG': 0.9},
            'not_irony'
        )
        result = detector.detect_text("Qué asco, esto es basura")
        self.assertEqual(result.mood, "frustrated")

    def test_others_maps_to_neutral(self):
        """pysentimiento 'others' → engine 'neutral'."""
        detector = self._make_detector_with_mocks(
            'others', {'joy': 0.1, 'sadness': 0.1, 'anger': 0.1,
                       'surprise': 0.1, 'fear': 0.1, 'disgust': 0.1, 'others': 0.4},
            'NEU', {'POS': 0.2, 'NEU': 0.6, 'NEG': 0.2},
            'not_irony'
        )
        result = detector.detect_text("El servidor tiene 16GB de RAM")
        self.assertEqual(result.mood, "neutral")

    def test_empty_text_returns_neutral(self):
        """Empty text returns neutral without loading models."""
        detector = PysentimientoDetector()
        result = detector.detect_text("")
        self.assertEqual(result.mood, "neutral")
        self.assertFalse(detector._loaded)  # models should NOT be loaded


# ═══════════════════════════════════════════════════
# HybridDetector Tests
# ═══════════════════════════════════════════════════

class TestHybridDetector(unittest.TestCase):
    """Tests for the hybrid detector combining keywords + pysentimiento."""

    def _make_hybrid_with_psy_mocks(self, emotion_out, emotion_probas,
                                     sentiment_out, sentiment_probas,
                                     irony_out):
        """Create a HybridDetector with mocked pysentimiento."""
        detector = HybridDetector()
        detector.psy_detector._loaded = True
        detector.psy_detector._emotion_analyzer = MagicMock()
        detector.psy_detector._emotion_analyzer.predict.return_value = _MockPrediction(
            emotion_out, emotion_probas
        )
        detector.psy_detector._sentiment_analyzer = MagicMock()
        detector.psy_detector._sentiment_analyzer.predict.return_value = _MockPrediction(
            sentiment_out, sentiment_probas
        )
        detector.psy_detector._irony_analyzer = MagicMock()
        detector.psy_detector._irony_analyzer.predict.return_value = _MockPrediction(
            irony_out, {'irony': 0.8, 'not_irony': 0.2}
        )
        return detector

    def test_sarcasm_genial_todo_fallo(self):
        """Sarcasm: 'genial, todo falló' → frustrated (not happy).

        This is F1 — the critical sarcasm bug fix. Keywords would detect 'genial'
        as happy, but pysentimiento detects irony + NEG → frustrated.
        """
        detector = self._make_hybrid_with_psy_mocks(
            'joy', {'joy': 0.7, 'sadness': 0.1, 'anger': 0.05,
                     'surprise': 0.05, 'fear': 0.03, 'disgust': 0.04, 'others': 0.03},
            'NEG', {'POS': 0.1, 'NEU': 0.2, 'NEG': 0.7},
            'irony'
        )
        result = detector.detect_text("Genial, todo falló")
        self.assertEqual(result.mood, "frustrated",
                         "F1: Sarcasm 'genial, todo falló' should be frustrated, not happy")
        self.assertTrue(result.is_ironic)
        self.assertEqual(result.source, "hybrid")

    def test_negation_no_estoy_bien(self):
        """Negation: 'no estoy bien' → sad (not neutral).

        Keywords don't have 'no estoy bien', but pysentimiento detects sadness.
        """
        detector = self._make_hybrid_with_psy_mocks(
            'sadness', {'joy': 0.05, 'sadness': 0.85, 'anger': 0.03,
                         'surprise': 0.02, 'fear': 0.02, 'disgust': 0.01, 'others': 0.02},
            'NEG', {'POS': 0.05, 'NEU': 0.1, 'NEG': 0.85},
            'not_irony'
        )
        result = detector.detect_text("No estoy bien")
        self.assertEqual(result.mood, "sad",
                         "Negation 'no estoy bien' should detect sadness")

    def test_peruvian_slang_uses_keywords(self):
        """Peruvian slang 'chévere' → happy (keyword detection, no pysentimiento needed)."""
        detector = HybridDetector()
        # Don't need to mock pysentimiento — keywords handle slang
        result = detector.detect_text("Qué chévere")
        self.assertEqual(result.mood, "happy")
        self.assertEqual(result.source, "hybrid")

    def test_mixed_emotions_agotado_pero_feliz(self):
        """Mixed: 'agotado pero feliz' — keyword detects both tired + happy.
        The keyword detector picks the one with most matches."""
        detector = HybridDetector()
        result = detector.detect_text("Estoy agotado pero feliz")
        # Keywords: agotado→tired, feliz→happy. Both have 1 match.
        # The result should be one of them (whichever comes first in Counter)
        self.assertIn(result.mood, ["tired", "happy"],
                      "Mixed emotions should detect either tired or happy")

    def test_irony_detection(self):
        """Irony: pysentimiento detects ironic 'perfecto, todo salió mal'."""
        detector = self._make_hybrid_with_psy_mocks(
            'joy', {'joy': 0.6, 'sadness': 0.15, 'anger': 0.1,
                     'surprise': 0.05, 'fear': 0.03, 'disgust': 0.04, 'others': 0.03},
            'NEG', {'POS': 0.1, 'NEU': 0.15, 'NEG': 0.75},
            'irony'
        )
        result = detector.detect_text("Perfecto, todo salió mal, un desastre total")
        self.assertEqual(result.mood, "frustrated")
        self.assertTrue(result.is_ironic)

    def test_fallback_to_keywords_when_no_sarcasm(self):
        """When no sarcasm indicators, falls back to keyword detection."""
        detector = HybridDetector()
        # 'No puedo más, estoy estresado' — no sarcasm, keywords handle it
        result = detector.detect_text("No puedo más, estoy estresado")
        self.assertEqual(result.mood, "stressed")
        self.assertEqual(result.source, "hybrid")

    def test_hybrid_fallback_on_psy_failure(self):
        """When pysentimiento fails, falls back to keywords."""
        detector = HybridDetector()
        # Force pysentimiento to fail
        detector.psy_detector._loaded = True
        detector.psy_detector._emotion_analyzer = MagicMock()
        detector.psy_detector._emotion_analyzer.predict.side_effect = RuntimeError("model error")

        # 'Genial, todo falló' triggers sarcasm path → pysentimiento fails → falls back
        result = detector.detect_text("Genial, todo falló")
        # Should still get some result (from keyword fallback or neutral)
        self.assertIsInstance(result, EmotionResult)

    def test_empty_text(self):
        """Empty text returns neutral."""
        detector = HybridDetector()
        result = detector.detect_text("")
        self.assertEqual(result.mood, "neutral")


# ═══════════════════════════════════════════════════
# EmotionResult / ConversationMoodResult Tests
# ═══════════════════════════════════════════════════

class TestDataClasses(unittest.TestCase):

    def test_emotion_result_defaults(self):
        """EmotionResult has correct defaults."""
        r = EmotionResult()
        self.assertEqual(r.mood, "neutral")
        self.assertEqual(r.intensity, 0.0)
        self.assertEqual(r.confidence, 0.0)
        self.assertFalse(r.is_ironic)
        self.assertEqual(r.source, "keyword")

    def test_emotion_result_clamps_intensity(self):
        """EmotionResult clamps intensity to [0, 1]."""
        r = EmotionResult(mood="happy", intensity=1.5)
        self.assertEqual(r.intensity, 1.0)
        r2 = EmotionResult(mood="happy", intensity=-0.5)
        self.assertEqual(r2.intensity, 0.0)

    def test_conversation_mood_result_defaults(self):
        """ConversationMoodResult has correct defaults."""
        r = ConversationMoodResult()
        self.assertEqual(r.mood, "neutral")
        self.assertEqual(r.intensity, 0.0)
        self.assertEqual(r.scores, {})


# ═══════════════════════════════════════════════════
# Strategy Pattern / ABC Tests
# ═══════════════════════════════════════════════════

class TestStrategyPattern(unittest.TestCase):

    def test_keyword_detector_is_emotion_detector(self):
        """KeywordDetector is an EmotionDetector."""
        self.assertIsInstance(KeywordDetector(), EmotionDetector)

    def test_pysentimiento_detector_is_emotion_detector(self):
        """PysentimientoDetector is an EmotionDetector."""
        self.assertIsInstance(PysentimientoDetector(), EmotionDetector)

    def test_hybrid_detector_is_emotion_detector(self):
        """HybridDetector is an EmotionDetector."""
        self.assertIsInstance(HybridDetector(), EmotionDetector)

    def test_all_detectors_have_detect_text(self):
        """All detectors implement detect_text."""
        for cls in [KeywordDetector, PysentimientoDetector, HybridDetector]:
            self.assertTrue(hasattr(cls, 'detect_text'))

    def test_all_detectors_have_detect_conversation(self):
        """All detectors implement detect_conversation."""
        for cls in [KeywordDetector, PysentimientoDetector, HybridDetector]:
            self.assertTrue(hasattr(cls, 'detect_conversation'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
