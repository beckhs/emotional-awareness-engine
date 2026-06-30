"""
outreach_engine_basic.py — Basic emotional analysis engine (open-source version).

This is the free tier of the Emotional Awareness Engine. It provides:
  - Conversation mood analysis
  - Communication pattern detection
  - Significant event detection
  - Check-in decision logic (read-only, does NOT send messages)

The premium version adds:
  - Proactive message generation with emotional context
  - Smart fallback messages that avoid AI-sounding patterns
  - Message validation (rejects generic/robotic output)
  - Automatic Telegram/Discord delivery via Hermes gateway
  - Self-improving pipeline that learns from message quality
  - Rate limiting with configurable policies
  - Multi-channel support

Premium: https://gumroad.com/l/emotional-awareness-engine
"""
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from emotional_state import (
    load_state, save_state, update_mood, add_event,
    should_check_in, get_check_in_status
)
from conversation_analyzer import (
    get_recent_sessions, analyze_conversation_mood,
    detect_significant_events, detect_communication_patterns
)


def evaluate_emotional_state() -> dict:
    """
    Evaluate current emotional state based on recent conversations.
    Returns analysis results WITHOUT sending any messages.

    This is the core analysis function available in the free version.
    The premium version extends this with proactive outreach.
    """
    state = load_state()

    # Analyze recent conversations
    sessions = get_recent_sessions(hours=48)
    all_messages = []
    for session in sessions:
        all_messages.extend(session.get("messages", []))

    if all_messages:
        mood_analysis = analyze_conversation_mood(all_messages)
        patterns = detect_communication_patterns(all_messages)
        events = detect_significant_events(all_messages)

        # Update state with latest analysis
        update_mood(state, mood_analysis["mood"], mood_analysis["intensity"])
        state["patterns"] = patterns

        # Update last interaction
        user_msgs = [m for m in all_messages if m.get("role") == "user"]
        if user_msgs:
            last_msg = max(user_msgs, key=lambda m: m.get("timestamp", 0))
            state["last_interaction"]["timestamp"] = last_msg.get("timestamp", 0)
            state["last_interaction"]["mood"] = mood_analysis["mood"]
            state["last_interaction"]["topic"] = _extract_topic(last_msg.get("content", ""))

        # Add significant events (deduplicated)
        existing_descs = {e.get("description", "") for e in state.get("significant_events", [])}
        for event in events:
            if event["description"] not in existing_descs:
                add_event(state, event["type"], event["description"],
                          mood=event.get("mood", ""), topic=event.get("topic", ""))

    # Check if a check-in is warranted (informational only)
    decision = should_check_in(state)
    save_state(state)

    return {
        "decision": decision,
        "state": state,
        "sessions_analyzed": len(sessions),
        "messages_analyzed": len(all_messages)
    }


def _extract_topic(content: str) -> str:
    """Extract the main topic from a message intelligently."""
    if not content:
        return ""

    content = content.strip()
    for prefix in ["[IMPORTANT:", "[OUT-OF-BAND", "You are", "Eres"]:
        if content.startswith(prefix):
            return "(system instruction)"

    if len(content) < 10:
        return content

    skip_patterns = ["hello", "hi", "hey", "good morning", "good evening"]
    first_word = content.split()[0].lower().rstrip(".,!?;:") if content.split() else ""
    if first_word in skip_patterns and len(content.split()) > 3:
        content = " ".join(content.split()[1:])

    if len(content) > 120:
        words = content[:120].split()
        content = " ".join(words[:-1]) + "..."

    return content.strip()


def get_analysis_summary() -> str:
    """
    Get a human-readable summary of the current emotional state.
    Useful for logging or displaying in dashboards.
    """
    result = evaluate_emotional_state()
    state = result["state"]

    lines = [
        "=== Emotional Awareness Engine — Analysis Summary ===",
        f"Mood: {state.get('current_mood', 'unknown')} "
        f"(intensity: {state.get('mood_intensity', 0):.2f})",
        f"Trend: {state.get('trend', 'unknown')}",
        f"Sessions analyzed: {result['sessions_analyzed']}",
        f"Messages analyzed: {result['messages_analyzed']}",
    ]

    decision = result["decision"]
    if decision.get("should"):
        lines.append(f"Check-in recommended: {decision.get('type', 'unknown')} "
                     f"— {decision.get('reason', '')}")
    else:
        lines.append(f"Check-in not needed: {decision.get('reason', '')}")

    events = state.get("significant_events", [])
    if events:
        lines.append(f"Recent events: {len(events)}")
        for event in events[-3:]:
            lines.append(f"  - [{event.get('type')}] {event.get('description', '')[:60]}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(get_analysis_summary())
