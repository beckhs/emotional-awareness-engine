"""
conversation_analyzer.py — Analyzes recent conversations from ~/.hermes/state.db
Detects emotions, patterns, and significant events using keyword-based analysis.
"""
import sqlite3
import time
import re
from pathlib import Path
from collections import Counter

DB_PATH = Path.home() / ".hermes" / "state.db"

# Mood keyword definitions (English)
MOOD_KEYWORDS = {
    "stressed": [
        "can't do this", "impossible", "giving up", "overwhelmed", "exhausted",
        "stressed", "can't take it", "so stressed", "feeling bad", "burned out",
        "falling apart", "can't handle", "pressure", "deadline", "breaking down",
        "at my limit", "too much", "drowning"
    ],
    "happy": [
        "awesome", "perfect", "it worked", "nailed it", "well done",
        "excellent", "great news", "amazing", "fantastic", "brilliant",
        "love it", "super", "congratulations", "cheerful", "stoked"
    ],
    "tired": [
        "tired", "exhausted", "can't sleep", "sleepy", "worn out",
        "no energy", "drained", "fatigued", "drowsy", "sluggish",
        "up all night", "burned out", "spent"
    ],
    "frustrated": [
        "again", "not working", "error", "broken", "bug",
        "damn it", "so annoying", "useless", "garbage", "waste of time",
        "frustrated", "fed up", "enough", "keeps failing", "hate this"
    ],
    "excited": [
        "incredible", "wow", "unbelievable", "mind-blowing", "insane",
        "this is wild", "impressive", "cool", "sick", "incredible",
        "astonishing", "fantastic", "genius", "let's go", "hell yeah"
    ]
}


def get_recent_sessions(hours: int = 48) -> list[dict]:
    """Get recent sessions with their messages from state.db."""
    cutoff = time.time() - (hours * 3600)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id as session_id, s.started_at, s.title, s.source
        FROM sessions s
        WHERE s.started_at >= ? AND s.archived = 0
        ORDER BY s.started_at DESC
    """, (cutoff,))
    sessions = [dict(row) for row in cursor.fetchall()]

    for session in sessions:
        cursor.execute("""
            SELECT role, content, timestamp
            FROM messages
            WHERE session_id = ? AND active = 1 AND content IS NOT NULL
            ORDER BY timestamp ASC
        """, (session["session_id"],))
        session["messages"] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return sessions


def extract_emotional_keywords(text: str) -> dict[str, list[str]]:
    """Extract emotional keywords from text. Returns dict mapping mood -> found keywords."""
    if not text:
        return {}
    text_lower = text.lower()
    found = {}
    for mood, keywords in MOOD_KEYWORDS.items():
        matches = [kw for kw in keywords if kw in text_lower]
        if matches:
            found[mood] = matches
    return found


def analyze_conversation_mood(messages: list[dict]) -> dict:
    """Analyze the overall mood of a conversation based on keyword frequency."""
    mood_scores = Counter()
    total_user_msgs = 0

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not content:
            continue
        total_user_msgs += 1
        keywords = extract_emotional_keywords(content)
        for mood, matches in keywords.items():
            mood_scores[mood] += len(matches)

    if not mood_scores:
        return {"mood": "neutral", "intensity": 0.0, "scores": {}}

    dominant_mood = mood_scores.most_common(1)[0][0]
    max_score = mood_scores.most_common(1)[0][1]
    intensity = min(1.0, max_score / max(total_user_msgs, 1))

    return {
        "mood": dominant_mood,
        "intensity": round(intensity, 2),
        "scores": dict(mood_scores)
    }


def detect_significant_events(messages: list[dict]) -> list[dict]:
    """Detect significant events in a conversation."""
    events = []
    seen_late_night = set()
    bad_moods = {"stressed", "frustrated", "tired"}

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not content:
            continue

        keywords = extract_emotional_keywords(content)

        # Detect late night activity (deduplicate by hour)
        ts = msg.get("timestamp", 0)
        if ts:
            hour = int(time.strftime("%H", time.localtime(ts)))
            if hour >= 1 and hour <= 5:
                # Only add one late_night event per hour
                hour_key = f"late_night_{hour}_{int(ts // 3600)}"
                if hour_key not in seen_late_night:
                    seen_late_night.add(hour_key)
                    events.append({
                        "timestamp": ts,
                        "type": "late_night",
                        "description": f"Activity at {hour}:00",
                        "mood": "tired"
                    })

        # Detect stress/frustration spikes
        for mood in bad_moods:
            if mood in keywords and len(keywords[mood]) >= 2:
                events.append({
                    "timestamp": ts,
                    "type": "stress_spike",
                    "description": f"Multiple {mood} indicators: {', '.join(keywords[mood])}",
                    "mood": mood
                })

        # Detect achievements
        if "happy" in keywords or "excited" in keywords:
            events.append({
                "timestamp": ts,
                "type": "achievement",
                "description": f"Achievement detected: {content[:80]}",
                "mood": keywords.get("happy", keywords.get("excited", []))[0] if keywords.get("happy") or keywords.get("excited") else "happy"
            })

    return events


def detect_communication_patterns(messages: list[dict]) -> dict:
    """Detect communication patterns: active hours, message length, topics."""
    user_messages = [m for m in messages if m.get("role") == "user" and m.get("content")]

    if not user_messages:
        return {
            "active_hours": {"start": 8, "end": 23},
            "avg_message_length": 0,
            "common_topics": [],
            "response_pattern": "normal"
        }

    # Active hours
    hours = []
    lengths = []
    for msg in user_messages:
        ts = msg.get("timestamp", 0)
        if ts:
            hours.append(int(time.strftime("%H", time.localtime(ts))))
        content = msg.get("content", "")
        lengths.append(len(content))

    # Topic extraction (simple: find common long words)
    all_text = " ".join(m.get("content", "") for m in user_messages).lower()
    words = re.findall(r'\b[a-záéíóúñ]{5,}\b', all_text)
    stopwords = {"about", "would", "could", "should", "their", "there", "where",
                 "which", "these", "those", "after", "being", "other", "every",
                 "through", "under", "again", "doing", "hello", "thanks", "great"}
    topic_words = [w for w in words if w not in stopwords]
    common_topics = [w for w, _ in Counter(topic_words).most_common(5)]

    active_start = min(hours) if hours else 8
    active_end = max(hours) if hours else 23
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    # Response pattern (simplified: based on message count)
    msg_count = len(user_messages)
    if msg_count > 20:
        pattern = "quick"
    elif msg_count > 5:
        pattern = "normal"
    else:
        pattern = "slow"

    return {
        "active_hours": {"start": active_start, "end": active_end},
        "avg_message_length": round(avg_length, 1),
        "common_topics": common_topics,
        "response_pattern": pattern
    }
