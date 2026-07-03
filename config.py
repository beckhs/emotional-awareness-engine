"""
config.py — Centralized configuration for Emotional Awareness Engine v3.0.
All settings in one place for easy tuning.
"""
from pathlib import Path

# ── User timezone ──────────────────────────────────────────────────
USER_TZ = 'America/Lima'

# ── pysentimiento settings ─────────────────────────────────────────
PYSNTIMENTO_VENV = Path(__file__).parent / '.venv'
PYSNTIMENTO_LANG = 'es'

# ── Detection thresholds ───────────────────────────────────────────
# Minimum pysentimiento confidence to trust its result over keywords
PSY_CONFIDENCE_THRESHOLD = 0.55

# If pysentimiento confidence is below this, always fall back to keywords
PSY_LOW_CONFIDENCE = 0.40

# Keyword match threshold: minimum keyword matches to consider a mood
KEYWORD_MIN_MATCHES = 1

# ── Rate limit settings (seconds) ──────────────────────────────────
RATE_LIMIT_NORMAL = 12 * 3600      # 12 hours (normal mood)
RATE_LIMIT_CONCERNED = 4 * 3600    # 4 hours (stressed/frustrated/tired)
RATE_LIMIT_CRISIS = 2 * 3600       # 2 hours (escalation)

# Maximum check-ins per day
MAX_DAILY_CHECKINS = 3
MAX_DAILY_CONCERNED = 5

# ── Quiet hours (in USER_TZ) ───────────────────────────────────────
# No check-ins during these hours (24h format, local time)
QUIET_HOURS_START = 23   # 11 PM Peru
QUIET_HOURS_END = 7      # 7 AM Peru

# ── Morning check-in ───────────────────────────────────────────────
# Hour in USER_TZ when the daily morning check-in happens
MORNING_CHECKIN_HOUR = 9  # 9 AM Peru

# ── Emotion mapping: pysentimiento → engine vocabulary ─────────────
EMOTION_MAP = {
    'joy': 'happy',
    'sadness': 'sad',
    'anger': 'frustrated',
    'fear': 'anxious',
    'surprise': 'surprised',
    'disgust': 'frustrated',
    'others': 'neutral',
}

# ── Misc ───────────────────────────────────────────────────────────
HERMES_COOLDOWN = 300  # 5 minutes between hermes calls
LOCK_FILE = Path('/tmp/emotional-engine.lock')
