"""
emotional_state.py — Gestiona el archivo de estado emocional en ~/.hermes/emotional-state.json
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
    "check_in_history": [],
    "spam_protection": {
        "consecutive_unanswered": 0,
        "last_beck_message": 0,
        "final_message_sent": False
    }
}


def load_state() -> dict:
    """Carga el estado emocional desde el archivo JSON. Si no existe, crea uno por defecto."""
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
    """Guarda el estado emocional al archivo JSON."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def update_mood(state: dict, mood: str, intensity: float) -> dict:
    """Actualiza el mood actual y calcula la tendencia."""
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
                  f"Cambio de {previous_mood} a {mood}",
                  mood=mood)

    return state


def add_event(state: dict, event_type: str, description: str,
              mood: str = "", topic: str = "") -> None:
    """Agrega un evento significativo al historial."""
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
    """Retorna el estado actual de los check-ins."""
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
    """Determina si se debe hacer un check-in y de qué tipo."""
    status = get_check_in_status(state)
    rules = state.get("check_in_rules", DEFAULT_STATE["check_in_rules"])
    bad_moods = {"stressed", "frustrated", "tired"}

    # Never in quiet hours
    if status["in_quiet_hours"]:
        return {"should": False, "reason": "horario silencioso"}

    # Minimum time between check-ins
    min_hours = rules.get("min_hours_between", 12)
    if status["hours_since_last_check_in"] < min_hours:
        return {"should": False, "reason": "check-in reciente"}

    # High priority: bad mood + 8+ hours
    if status["last_mood"] in bad_moods and status["hours_since_last_interaction"] >= 8:
        return {"should": True, "type": "high_priority", "reason": "mood negativo hace 8+ horas"}

    # Escalation: 48+ hours silence
    escalation_hours = rules.get("escalation_hours", 48)
    if status["hours_since_last_interaction"] >= escalation_hours:
        return {"should": True, "type": "escalation", "reason": "48+ horas sin interacción"}

    # Normal check-in: 24+ hours
    max_silence = rules.get("max_hours_silence", 24)
    if status["hours_since_last_interaction"] >= max_silence:
        return {"should": True, "type": "normal", "reason": "24+ horas sin interacción"}

    return {"should": False, "reason": "no necesario"}
