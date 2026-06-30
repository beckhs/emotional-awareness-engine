"""
emotional_state.py — Manages the emotional state file at ~/.hermes/emotional-state.json

Provides load/save, mood updates with trend calculation, significant event tracking,
and check-in decision logic.
"""
import json
import os
import time
from pathlib import Path

STATE_PATH = Path.home() / ".hermes" / "emotional-state.json"

DEFAULT_STATE = {
    "current_mood": "unknown",
    "mood_intensity": 0.0,
    "trend": "unknown",
    "patterns": {
        "stress_days": [],
        "active_hours": {"start": 8, "end": 23},
        "avg_message_length": 0,
        "common_topics": [],
        "response_pattern": "normal"
    },
    "significant_events": [],
    "last_interaction": {
        "timestamp": 0,
        "mood": "unknown",
        "topic": "",
        "duration": 0
    },
    "check_in_rules": {
        "min_hours_between": 12,
        "max_hours_silence": 24,
        "escalation_hours": 48,
        "quiet_hours_start": 23,
        "quiet_hours_end": 7
    },
    "check_in_history": []
}


def load_state() -> dict:
    """Load emotional state from JSON file. Creates default if missing."""
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Merge with defaults to handle missing keys
            for key, val in DEFAULT_STATE.items():
                if key not in state:
                    state[key] = val
            return state
        except (json.JSONDecodeError, OSError):
            return DEFAULT_STATE.copy()
    return DEFAULT_STATE.copy()


def save_state(state: dict) -> None:
    """Save emotional state to JSON file."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def update_mood(state: dict, mood: str, intensity: float) -> dict:
    """Update current mood and calculate trend."""
    previous_mood = state.get("current_mood", "unknown")
    state["current_mood"] = mood
    state["mood_intensity"] = max(0.0, min(1.0, intensity))

    # Calculate trend
    bad_moods = {"stressed", "frustrated", "tired"}
    good_moods = {"happy", "excited"}

    if previous_mood in bad_moods and mood in good_moods:
        state["trend"] = "improving"
    elif previous_mood in good_moods and mood in bad_moods:
        state["trend"] = "declining"
    elif mood == previous_mood:
        state["trend"] = "stable"
    else:
        state["trend"] = "stable"

    # Detect mood shift as significant event
    if previous_mood != mood and previous_mood != "unknown":
        add_event(state, "mood_shift",
                  f"Shift from {previous_mood} to {mood}",
                  mood=mood)

    return state


def add_event(state: dict, event_type: str, description: str,
              mood: str = "", topic: str = "") -> None:
    """Add a significant event to the history."""
    event = {
        "timestamp": time.time(),
        "type": event_type,
        "description": description
    }
    if mood:
        event["mood"] = mood
    if topic:
        event["topic"] = topic

    if "significant_events" not in state:
        state["significant_events"] = []

    state["significant_events"].append(event)
    # Keep only last 50 events
    if len(state["significant_events"]) > 50:
        state["significant_events"] = state["significant_events"][-50:]


def get_check_in_status(state: dict) -> dict:
    """Return the current check-in status."""
    now = time.time()
    history = state.get("check_in_history", [])
    rules = state.get("check_in_rules", DEFAULT_STATE["check_in_rules"])
    last_interaction = state.get("last_interaction", {})

    last_check_in_ts = 0
    if history:
        last_check_in_ts = max(h["timestamp"] for h in history)

    hours_since_last_check_in = (now - last_check_in_ts) / 3600 if last_check_in_ts > 0 else 999
    hours_since_interaction = (now - last_interaction.get("timestamp", 0)) / 3600 if last_interaction.get("timestamp", 0) > 0 else 999

    current_hour = int(time.strftime("%H"))
    quiet_start = rules.get("quiet_hours_start", 23)
    quiet_end = rules.get("quiet_hours_end", 7)

    in_quiet_hours = False
    if quiet_start > quiet_end:  # e.g., 23-7 wraps midnight
        in_quiet_hours = current_hour >= quiet_start or current_hour < quiet_end
    else:
        in_quiet_hours = quiet_start <= current_hour < quiet_end

    return {
        "hours_since_last_check_in": hours_since_last_check_in,
        "hours_since_last_interaction": hours_since_interaction,
        "in_quiet_hours": in_quiet_hours,
        "last_mood": last_interaction.get("mood", "unknown"),
        "last_topic": last_interaction.get("topic", ""),
        "total_check_ins_today": sum(
            1 for h in history
            if now - h["timestamp"] < 86400
        ),
        "last_check_in_type": history[-1]["type"] if history else None
    }


def should_check_in(state: dict) -> dict:
    """Determine whether a check-in should happen and what type."""
    status = get_check_in_status(state)
    rules = state.get("check_in_rules", DEFAULT_STATE["check_in_rules"])
    bad_moods = {"stressed", "frustrated", "tired"}

    # Never in quiet hours
    if status["in_quiet_hours"]:
        return {"should": False, "reason": "quiet hours"}

    # Minimum time between check-ins
    min_hours = rules.get("min_hours_between", 12)
    if status["hours_since_last_check_in"] < min_hours:
        return {"should": False, "reason": "recent check-in"}

    # High priority: bad mood + 8+ hours
    if status["last_mood"] in bad_moods and status["hours_since_last_interaction"] >= 8:
        return {"should": True, "type": "high_priority", "reason": "negative mood for 8+ hours"}

    # Escalation: 48+ hours silence
    escalation_hours = rules.get("escalation_hours", 48)
    if status["hours_since_last_interaction"] >= escalation_hours:
        return {"should": True, "type": "escalation", "reason": "48+ hours without interaction"}

    # Normal check-in: 24+ hours
    max_silence = rules.get("max_hours_silence", 24)
    if status["hours_since_last_interaction"] >= max_silence:
        return {"should": True, "type": "normal", "reason": "24+ hours without interaction"}

    return {"should": False, "reason": "not needed"}
