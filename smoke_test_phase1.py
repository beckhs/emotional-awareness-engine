#!/usr/bin/env python3
"""
smoke_test_phase1.py — Phase 1 Smoke Test: Simulates a full day.

Simulation flow:
  a) Beck sends 3 messages (happy, frustrated, achievement)
  b) Events are stored with scores
  c) Check-in fires and message references events
  d) Simulate 3 unanswered check-ins → verify anti-spam blocks
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from emotional_state import DEFAULT_STATE, update_mood, should_check_in
from conversation_analyzer import (
    extract_emotional_keywords, analyze_conversation_mood,
    detect_significant_events
)
from event_store import EventStore
from outreach_engine import (
    _fallback_message, _check_anti_spam, _update_spam_state,
    _validate_message
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")

print("=" * 70)
print("🔥 PHASE 1 SMOKE TEST — Simulating a full day with Beck")
print("=" * 70)

# ─── Setup ───────────────────────────────────────────────────────────

store = EventStore()
state = DEFAULT_STATE.copy()
state["spam_protection"] = {
    "consecutive_unanswered": 0,
    "last_beck_message": 0,
    "final_message_sent": False,
}
state["check_in_history"] = []
state["last_interaction"] = {
    "timestamp": time.time(),
    "mood": "unknown",
    "topic": "",
    "duration": 0,
}

now = time.time()

# ══════════════════════════════════════════════════════════════════════
# STEP A: Beck sends 3 messages (happy, frustrated, achievement)
# ══════════════════════════════════════════════════════════════════════

print("\n─── STEP A: Beck sends 3 messages ───")

beck_messages = [
    {
        "role": "user",
        "content": "¡Genial! ¡El deploy salió perfecto! Estoy súper contento con el resultado.",
        "timestamp": now - 3600  # 1 hour ago
    },
    {
        "role": "user",
        "content": "Otra vez el mismo bug, no funciona. Maldita sea, estoy harto de este error.",
        "timestamp": now - 2000  # 33 min ago
    },
    {
        "role": "user",
        "content": "¡Wow! ¡Al fin logré arreglarlo! Increíble, el engine ya funciona.",
        "timestamp": now - 1000  # 17 min ago
    },
]

for i, msg in enumerate(beck_messages):
    keywords = extract_emotional_keywords(msg["content"])
    print(f"  Message {i+1}: \"{msg['content'][:70]}...\"")
    print(f"    Keywords detected: {keywords if keywords else 'none'}")

# Analyze overall mood
mood_result = analyze_conversation_mood(beck_messages)
print(f"\n  Overall mood: {mood_result['mood']} (intensity: {mood_result['intensity']})")
check("Mood analysis returns valid mood",
      mood_result["mood"] in ["happy", "frustrated", "stressed", "excited", "neutral", "tired"])

# Update state
update_mood(state, mood_result["mood"], mood_result["intensity"])
check("State updated with mood", state["current_mood"] == mood_result["mood"])

# ══════════════════════════════════════════════════════════════════════
# STEP B: Events are stored with scores
# ══════════════════════════════════════════════════════════════════════

print("\n─── STEP B: Events stored in EventStore ───")

events = detect_significant_events(beck_messages)
print(f"  Detected {len(events)} significant events:")

stored_count = 0
for event in events:
    print(f"    • {event['type']}: {event['description']}")
    stored = store.add_event(
        event_type=event["type"],
        description=event["description"],
        score=mood_result["intensity"],
        mood=event.get("mood", ""),
        topic="engine deploy",
    )
    stored_count += 1
    check(f"Event '{event['type']}' stored with score={stored['score']}",
          stored["score"] > 0)

check("Events were stored in EventStore", len(store) > 0)
print(f"  Total events in store: {len(store)}")

# Verify top events
top_events = store.get_top_events(limit=3)
print(f"  Top events by score:")
for e in top_events:
    print(f"    • {e['type']}: {e['description'][:60]} (score: {e['score']})")

# ══════════════════════════════════════════════════════════════════════
# STEP C: Check-in fires and message references events
# ══════════════════════════════════════════════════════════════════════

print("\n─── STEP C: Check-in triggers with event-aware message ───")

# Simulate 25 hours of silence
state["last_interaction"]["mood"] = mood_result["mood"]
state["last_interaction"]["timestamp"] = now - (25 * 3600)

with patch("emotional_state.time") as mock_time:
    mock_time.time.return_value = now
    mock_time.strftime.return_value = "14"  # 2 PM
    decision = should_check_in(state)

print(f"  Check-in decision: {decision}")
check("Check-in triggers after 25h silence", decision["should"] is True)

# Generate message referencing real events
recent_events = store.get_recent_events(limit=5)
print(f"  Using {len(recent_events)} events for message generation:")
for e in recent_events:
    print(f"    • {e['description'][:70]}")

checkin_msg = _fallback_message(
    mood_result["mood"],
    "engine deploy",
    state.get("trend", "stable"),
    25,
    events=recent_events,
)

print(f"\n  Generated check-in message:")
print(f"  ┌─────────────────────────────────────────────────")
print(f"  │ {checkin_msg}")
print(f"  └─────────────────────────────────────────────────")

check("Message references real events or topic",
      any(e["description"][:30] in checkin_msg for e in recent_events) or
      "engine" in checkin_msg.lower() or "deploy" in checkin_msg.lower(),
      f"Message: {checkin_msg[:80]}")

check("Message passes validation", _validate_message(checkin_msg))
check("Message is not generic", "¿Cómo estás?" not in checkin_msg)

# ══════════════════════════════════════════════════════════════════════
# STEP D: Simulate 3 unanswered check-ins → verify anti-spam blocks
# ══════════════════════════════════════════════════════════════════════

print("\n─── STEP D: Anti-spam with 3 unanswered check-ins ───")

spam = state["spam_protection"]
print(f"  Initial state: consecutive_unanswered={spam['consecutive_unanswered']}")

# Simulate 3 unanswered check-in cycles
for i in range(1, 4):
    _update_spam_state(state, beck_messaged_today=False)
    print(f"  Cycle {i}: consecutive_unanswered = {spam['consecutive_unanswered']}")
    check(f"Counter incremented to {i}", spam["consecutive_unanswered"] == i)

# Check anti-spam
should_block, reason = _check_anti_spam(state)
print(f"\n  Anti-spam check at count {spam['consecutive_unanswered']}:")
print(f"    Blocked: {should_block}")
print(f"    Reason: {reason}")

check("Anti-spam blocks at 3 unanswered",
      should_block is True and "3 check-ins sin respuesta" in reason)

# Simulate Beck coming back — counter resets
print("\n  Simulating Beck returns and sends a message...")
_update_spam_state(state, beck_messaged_today=True)
print(f"  After Beck messages: consecutive_unanswered = {spam['consecutive_unanswered']}")

check("Counter resets when Beck messages",
      spam["consecutive_unanswered"] == 0)
check("final_message_sent is cleared",
      spam["final_message_sent"] is False)

# Now simulate 7+ days without Beck → final message scenario
print("\n  Simulating 9 days without Beck...")
spam["last_beck_message"] = now - (9 * 86400)

should_block, reason = _check_anti_spam(state)
print(f"  Anti-spam check: blocked={should_block}, reason={reason}")

check("7+ days triggers final_message allowance",
      should_block is False and reason == "final_message")
check("final_message_sent flag is set",
      spam["final_message_sent"] is True)

# After final message sent, 3+ unanswered → permanent silence
spam["consecutive_unanswered"] = 3
should_block, reason = _check_anti_spam(state)
print(f"  After final + 3 unanswered: blocked={should_block}, reason={reason}")

check("Permanent silence after final + 3 unanswered",
      should_block is True and "silencio permanente" in reason)

# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("SMOKE TEST RESULTS")
print("=" * 70)

total = PASS + FAIL
print(f"\n  Total checks: {total}")
print(f"  ✅ Passed: {PASS}")
print(f"  ❌ Failed: {FAIL}")
print(f"  Success rate: {PASS/total*100:.1f}%" if total > 0 else "  No tests run")
print("=" * 70)

# Cleanup
store.clear()

if FAIL > 0:
    print(f"\n⚠️  {FAIL} smoke test(s) FAILED!")
    sys.exit(1)
else:
    print("\n🔥 All smoke tests passed! Phase 1 pipeline is working.")
    sys.exit(0)
