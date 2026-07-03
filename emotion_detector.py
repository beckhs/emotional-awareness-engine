"""
emotion_detector.py — Strategy pattern for emotion detection.

Provides three detector implementations:
  - KeywordDetector: fast keyword-based (backward compatible)
  - PysentimientoDetector: ML-based using pysentimiento (lazy-loaded)
  - HybridDetector: combines both for best accuracy

Emotion mapping (pysentimiento → engine vocabulary):
  joy→happy, sadness→sad, anger→frustrated, fear→anxious,
  surprise→surprised, disgust→frustrated, others→neutral
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger('emotional-engine')


# ── Data classes ───────────────────────────────────────────────────

@dataclass
class EmotionResult:
    """Result of detecting emotion in a single text."""
    mood: str = 'neutral'
    intensity: float = 0.0
    confidence: float = 0.0
    is_ironic: bool = False
    raw_emotion: Optional[str] = None      # pysentimiento raw output
    raw_sentiment: Optional[str] = None    # pysentimiento raw output
    source: str = 'keyword'                # 'keyword', 'pysentimiento', 'hybrid'

    def __post_init__(self):
        self.intensity = max(0.0, min(1.0, self.intensity))
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class ConversationMoodResult:
    """Result of analyzing mood across a conversation."""
    mood: str = 'neutral'
    intensity: float = 0.0
    confidence: float = 0.0
    scores: dict = field(default_factory=dict)
    source: str = 'keyword'
    is_ironic: bool = False


# ── Abstract base ──────────────────────────────────────────────────

class EmotionDetector(ABC):
    """Interface for emotion detection strategies."""

    @abstractmethod
    def detect_text(self, text: str) -> EmotionResult:
        """Detect emotion in a single piece of text."""
        ...

    def detect_conversation(self, messages: list[dict],
                            recency_weighted: bool = True) -> ConversationMoodResult:
        """Detect overall mood of a conversation (list of message dicts).

        Default implementation aggregates per-message results.
        Subclasses may override for efficiency.
        """
        from collections import Counter
        import time as _time

        mood_scores: Counter = Counter()
        total_user = 0
        msgs_with_emotion = 0
        now = _time.time()
        any_ironic = False

        for msg in messages:
            if msg.get('role') != 'user':
                continue
            content = msg.get('content', '')
            if not content or _is_system_msg(content):
                continue
            total_user += 1

            result = self.detect_text(content)
            if result.mood != 'neutral':
                msgs_with_emotion += 1
                weight = 1.0
                if recency_weighted:
                    ts = msg.get('timestamp', 0)
                    if ts and ts > 0:
                        age_h = max(0, (now - ts) / 3600)
                        weight = 0.5 ** (age_h / 12)
                mood_scores[result.mood] += result.intensity * weight
            if result.is_ironic:
                any_ironic = True

        if not mood_scores:
            return ConversationMoodResult(mood='neutral', intensity=0.0,
                                          source=self.__class__.__name__)

        dominant = mood_scores.most_common(1)[0]
        max_score = dominant[1]
        intensity = min(1.0, max_score / max(msgs_with_emotion, 1) * 0.4)

        return ConversationMoodResult(
            mood=dominant[0],
            intensity=round(intensity, 2),
            confidence=0.0,
            scores=dict(mood_scores),
            source=self.__class__.__name__,
            is_ironic=any_ironic,
        )


# ── Helper ─────────────────────────────────────────────────────────

_SYSTEM_PREFIXES = [
    '[IMPORTANT:', '[OUT-OF-BAND', '[ASYNC DELEGATION', 'Eres Ivi',
    'You are', 'Cronjob Response:', '[Replying to:',
]
_SYSTEM_CONTAINS = [
    'Cronjob Response', 'ASYNC DELEGATION BATCH COMPLETE',
    'The user has invoked', 'Read arxiv abstract',
    'extract autonomous', 'You are running as a scheduled cron',
    'DELIVER', 'hermes chat -q', 'tool_calls', 'function_call',
]


def _is_system_msg(content: str) -> bool:
    if not content:
        return True
    for p in _SYSTEM_PREFIXES:
        if content.startswith(p):
            return True
    for p in _SYSTEM_CONTAINS:
        if p in content:
            return True
    return False


# ── KeywordDetector ────────────────────────────────────────────────

class KeywordDetector(EmotionDetector):
    """Fast keyword-based detector. Reuses MOOD_KEYWORDS from conversation_analyzer."""

    def __init__(self):
        from conversation_analyzer import MOOD_KEYWORDS
        self._keywords = MOOD_KEYWORDS

    def detect_text(self, text: str) -> EmotionResult:
        if not text:
            return EmotionResult()
        text_lower = text.lower()
        found: dict[str, list[str]] = {}
        for mood, kws in self._keywords.items():
            matches = [kw for kw in kws if kw in text_lower]
            if matches:
                found[mood] = matches

        if not found:
            return EmotionResult()

        # Pick mood with most keyword matches.
        # On tie: prefer negative moods (safety — sarcasm often has positive
        # keywords with negative context, e.g. "genial, todo falló").
        NEGATIVE_MOODS = {'frustrated', 'sad', 'stressed', 'anxious'}
        best_mood = max(found, key=lambda m: (len(found[m]), m in NEGATIVE_MOODS))
        n_matches = len(found[best_mood])
        # Check for conflict: if positive and negative moods both matched,
        # flag as potentially sarcastic (confidence stays low)
        has_conflict = bool(set(found) & NEGATIVE_MOODS) and bool(set(found) - NEGATIVE_MOODS)
        intensity = min(1.0, n_matches * 0.25 + 0.15 * (n_matches - 1))
        return EmotionResult(
            mood=best_mood,
            intensity=round(intensity, 2),
            confidence=min(1.0, 0.3 + 0.15 * n_matches),
            source='keyword',
        )


# ── PysentimientoDetector ──────────────────────────────────────────

class PysentimientoDetector(EmotionDetector):
    """ML-based detector using pysentimiento. Lazy-loads models to save RAM.

    Loads Cosmo (fine-tuned) if available, falls back to pysentimiento vanilla.
    """

    # Cosmo model path (fine-tuned)
    COSMO_PATH = str(Path(__file__).parent / 'fine-tuning' / 'fine-tuned-model')

    def __init__(self):
        self._emotion_analyzer = None
        self._sentiment_analyzer = None
        self._irony_analyzer = None
        self._loaded = False
        self._model_name = None

    def _ensure_loaded(self):
        if self._loaded:
            return
        try:
            from pysentimiento import create_analyzer
            from pathlib import Path

            # Try Cosmo first
            if Path(self.COSMO_PATH).exists():
                log.info('Loading Cosmo (fine-tuned model)...')
                self._emotion_analyzer = create_analyzer(
                    task='emotion', lang='es', model_name=self.COSMO_PATH)
                self._model_name = 'cosmo'
            else:
                log.info('Cosmo not found, loading pysentimiento vanilla...')
                self._emotion_analyzer = create_analyzer(task='emotion', lang='es')
                self._model_name = 'pysentimiento'

            # Always use vanilla for sentiment and irony
            self._sentiment_analyzer = create_analyzer(task='sentiment', lang='es')
            self._irony_analyzer = create_analyzer(task='irony', lang='es')
            self._loaded = True
            log.info(f'Models loaded. Emotion model: {self._model_name}')
        except Exception as e:
            log.warning(f'Failed to load pysentimiento: {e}')
            self._loaded = False

    @staticmethod
    def _map_emotion(raw: str) -> str:
        from config import EMOTION_MAP
        return EMOTION_MAP.get(raw, 'neutral')

    def detect_text(self, text: str) -> EmotionResult:
        if not text or len(text.strip()) < 3:
            return EmotionResult(source='pysentimiento')

        self._ensure_loaded()
        if not self._loaded:
            return EmotionResult(source='pysentimiento')

        try:
            emo = self._emotion_analyzer.predict(text)
            sent = self._sentiment_analyzer.predict(text)
            iron = self._irony_analyzer.predict(text)

            raw_emotion = emo.output
            emotion_probs = dict(emo.probas)
            raw_sentiment = sent.output
            is_ironic = iron.output == 'irony'

            mood = self._map_emotion(raw_emotion)
            confidence = max(emotion_probs.values()) if emotion_probs else 0.0

            # Irony override: if ironic + negative sentiment → frustrated
            if is_ironic and raw_sentiment == 'NEG':
                mood = 'frustrated'
                confidence = max(confidence, 0.7)

            # Compute intensity from probability distribution
            top_prob = max(emotion_probs.values()) if emotion_probs else 0.0
            intensity = min(1.0, top_prob * 0.8 + 0.2)

            return EmotionResult(
                mood=mood,
                intensity=round(intensity, 2),
                confidence=round(confidence, 2),
                is_ironic=is_ironic,
                raw_emotion=raw_emotion,
                raw_sentiment=raw_sentiment,
                source='pysentimiento',
            )
        except Exception as e:
            log.warning(f'pysentimiento error: {e}')
            return EmotionResult(source='pysentimiento')


# ── HybridDetector ─────────────────────────────────────────────────

class HybridDetector(EmotionDetector):
    """Combines pysentimiento (for sarcasm/negation/low-confidence) with keywords.

    Strategy:
    - Always run keywords first (fast).
    - If keywords detect sarcasm indicators (positive keyword + negative context),
      use pysentimiento to verify.
    - If pysentimiento detects irony → override mood.
    - If keyword confidence is low → use pysentimiento result.
    - If pysentimiento confidence is high and keyword result is ambiguous → use pysentimiento.
    - Otherwise → use keyword result (faster, no RAM overhead).
    """

    def __init__(self):
        self.keyword_detector = KeywordDetector()
        self.psy_detector = PysentimientoDetector()

    def _has_sarcasm_indicators(self, text: str) -> bool:
        """Heuristics: positive+negative combo, or classic sarcastic phrases."""
        text_lower = text.lower()
        positive = ['genial', 'perfecto', 'excelente', 'qué bien',
                     'increíble', 'fantástico', 'super', 'wow',
                     'maravilla', 'hermoso', 'bonito', 'magnífico']
        negative = ['no funciona', 'falló', 'falla', 'error', 'otra vez',
                     'maldita', 'basura', 'mal', 'desastre', 'no sirve',
                     'inútil', 'no puedo', 'imposible', 'fallo', 'se cayó']

        has_pos = any(p in text_lower for p in positive)
        has_neg = any(n in text_lower for n in negative)

        # Case A: positive + negative combo → likely sarcasm
        if has_pos and has_neg:
            return True

        # Case B: classic sarcastic phrases (Spanish)
        sarcasm_phrases = ['ah sí claro', 'ah claro', 'sí claro',
                           'ah sí', 'qué maravilla', 'oh genial',
                           'ah perfecto', 'muy bien']
        if any(p in text_lower for p in sarcasm_phrases):
            return True

        return False

    def _has_negation_pattern(self, text: str) -> bool:
        """Detect negation patterns like 'no estoy bien', 'no me siento'."""
        text_lower = text.lower().strip()
        neg_patterns = ['no estoy', 'no me siento', 'no la estoy pasando',
                        'no me encuentro', 'no ando', 'no la paso']
        return any(p in text_lower for p in neg_patterns)

    def detect_text(self, text: str) -> EmotionResult:
        if not text:
            return EmotionResult(source='hybrid')

        kw_result = self.keyword_detector.detect_text(text)

        # Case 1: Sarcasm indicators → use pysentimiento to verify
        if self._has_sarcasm_indicators(text):
            psy_result = self.psy_detector.detect_text(text)
            if psy_result.is_ironic or psy_result.mood in ('frustrated', 'sad'):
                return EmotionResult(
                    mood=psy_result.mood if psy_result.mood != 'neutral' else 'frustrated',
                    intensity=max(psy_result.intensity, 0.5),
                    confidence=max(psy_result.confidence, 0.6),
                    is_ironic=True,
                    raw_emotion=psy_result.raw_emotion,
                    raw_sentiment=psy_result.raw_sentiment,
                    source='hybrid',
                )

        # Case 2: Negation patterns → use pysentimiento
        if self._has_negation_pattern(text):
            psy_result = self.psy_detector.detect_text(text)
            if psy_result.mood != 'neutral' and psy_result.confidence > 0.3:
                return EmotionResult(
                    mood=psy_result.mood,
                    intensity=psy_result.intensity,
                    confidence=psy_result.confidence,
                    is_ironic=psy_result.is_ironic,
                    raw_emotion=psy_result.raw_emotion,
                    raw_sentiment=psy_result.raw_sentiment,
                    source='hybrid',
                )

        # Case 3: Low keyword confidence → try pysentimiento
        # BUT: if pysentimiento returns "neutral" and keywords detected
        # something, keep keywords (e.g. Peruvian slang pysentimiento doesn't know)
        if kw_result.confidence < 0.5:
            psy_result = self.psy_detector.detect_text(text)
            if psy_result.confidence > kw_result.confidence and psy_result.mood != 'neutral':
                return EmotionResult(
                    mood=psy_result.mood,
                    intensity=psy_result.intensity,
                    confidence=psy_result.confidence,
                    is_ironic=psy_result.is_ironic,
                    raw_emotion=psy_result.raw_emotion,
                    raw_sentiment=psy_result.raw_sentiment,
                    source='hybrid',
                )

        # Default: use keyword result (fast, no RAM overhead)
        # BUT: if pysentimiento returned "neutral" with high confidence and
        # keywords detected something real, prefer keywords (e.g. Peruvian slang
        # like "chévere" that pysentimiento doesn't recognize).
        if kw_result.mood != 'neutral' and kw_result.confidence > 0.3:
            return EmotionResult(
                mood=kw_result.mood,
                intensity=kw_result.intensity,
                confidence=kw_result.confidence,
                source='hybrid',
            )

        return EmotionResult(
            mood=kw_result.mood,
            intensity=kw_result.intensity,
            confidence=kw_result.confidence,
            source='hybrid',
        )
