# How It Works

## Architecture Overview

The Emotional Awareness Engine is a pipeline that analyzes conversation data
to detect emotional states, communication patterns, and significant events.

```
┌─────────────────────────────────────────────────────────────┐
│                    Analysis Pipeline                        │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  SQLite   │───▶│  Conversation │───▶│  Emotional State │  │
│  │  state.db │    │  Analyzer     │    │  Manager         │  │
│  └──────────┘    └──────────────┘    └──────────────────┘  │
│       │               │                      │             │
│       │               ▼                      ▼             │
│       │         ┌──────────────┐    ┌──────────────────┐  │
│       │         │  Pattern      │    │  Check-In        │  │
│       │         │  Detection    │    │  Decision Logic  │  │
│       │         └──────────────┘    └──────────────────┘  │
│       │               │                      │             │
│       │               ▼                      ▼             │
│       │         ┌──────────────┐    ┌──────────────────┐  │
│       └────────▶│  Significant  │    │  emotional-      │  │
│                 │  Event Log    │    │  state.json      │  │
│                 └──────────────┘    └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Stages

### 1. Conversation Retrieval

The engine reads recent conversations from Hermes Agent's `state.db` SQLite
database. It queries sessions and their messages from the last 48 hours
(configurable).

```python
sessions = get_recent_sessions(hours=48)
```

### 2. Mood Detection

User messages are analyzed using keyword matching against predefined mood
categories:

- **stressed** — pressure, overwhelm, burnout indicators
- **happy** — achievement, satisfaction, positive events
- **tired** — sleep deprivation, exhaustion, low energy
- **frustrated** — failures, bugs, repeated problems
- **excited** — breakthroughs, impressive results, enthusiasm

The dominant mood is determined by keyword frequency, and intensity is
calculated as a ratio of keyword hits to total user messages.

### 3. Pattern Detection

The engine identifies communication patterns:

- **Active hours** — when the user typically messages
- **Message length** — average length (short = terse/stressed, long = engaged)
- **Common topics** — frequently discussed subjects
- **Response pattern** — quick, normal, or slow messaging cadence

### 4. Significant Event Detection

Events are flagged when specific patterns are detected:

| Event Type | Trigger |
|------------|---------|
| `mood_shift` | Mood changes between conversations |
| `stress_spike` | 2+ stress/frustration keywords in one message |
| `achievement` | Happiness or excitement detected |
| `late_night` | Activity between 1 AM and 5 AM |

### 5. Check-In Decision Logic

The decision engine evaluates whether a check-in is warranted based on:

```
Quiet hours? → NO
Recent check-in (< 12h)? → NO
Bad mood + 8h silence? → YES (high_priority)
48h+ silence? → YES (escalation)
24h+ silence? → YES (normal)
Otherwise → NO
```

### 6. State Persistence

All analysis results are persisted to `~/.hermes/emotional-state.json`:

- Current mood and intensity
- Mood trend (improving/stable/declining)
- Communication patterns
- Significant event history (last 50)
- Check-in history (last 30)

## What's Different in the Premium Version

The open-source version runs the full analysis pipeline but stops at the
decision stage. The premium version continues with:

1. **Message Generation** — Uses an LLM to generate context-aware check-in
   messages that reference the detected mood, topic, and events.

2. **Quality Validation** — Rejects messages that contain generic AI patterns
   ("I understand how you feel", "How can I help?", etc.)

3. **Smart Fallbacks** — When LLM generation fails, provides pre-written
   messages that vary by time-of-day and mood context.

4. **Delivery** — Sends validated messages through Hermes gateway to
   Telegram, Discord, or other channels.

5. **Self-Improving Pipeline** — Logs message quality metrics and adjusts
   generation parameters over time.

6. **Rate Limiting** — Configurable per-channel and per-user rate limits
   with daily caps and cooldown periods.

## Design Decisions

**Why keyword-based instead of ML?**
Zero dependencies. Works on any Python 3.11+ environment with no GPU, no API
keys, no network calls. The analysis is deterministic and auditable.

**Why SQLite?**
It reads from Hermes Agent's existing `state.db` — no additional storage
needed. The engine is read-only with respect to the conversation database.

**Why JSON for state?**
Human-readable, easy to inspect and modify, works well with version control
for tracking emotional patterns over time.
