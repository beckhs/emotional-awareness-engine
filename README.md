<!-- Emotional Awareness Engine README -->
<p align="center">
  <strong>🧠 Emotional Awareness Engine</strong><br>
  <em>Genuine Emotional Intelligence for AI Agents</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-15%20passing-brightgreen.svg" alt="Tests Passing">
  <img src="https://img.shields.io/badge/deps-stdlib%20only-lightgrey.svg" alt="No Dependencies">
</p>

---

The Emotional Awareness Engine gives your AI agent the ability to understand and track a user's emotional state over time. Instead of treating every conversation as isolated, it builds a persistent model of mood, stress patterns, communication habits, and significant life events — enabling your agent to respond with genuine context rather than generic pleasantries.

Built for self-hosted AI agents like [Hermes Agent](https://hermes-agent.nousresearch.com) and [OpenClaw](https://openclaw.com). Zero dependencies, zero API keys, zero network calls.

## What It Does

- **Mood Detection** — Analyzes conversation history to detect stress, frustration, excitement, tiredness, and happiness through keyword-based emotional analysis
- **Pattern Recognition** — Learns the user's active hours, message length patterns, common topics, and communication cadence
- **Significant Event Tracking** — Detects stress spikes, late-night activity, achievements, and mood shifts; maintains a rolling history of the last 50 events
- **Smart Check-In Decisions** — Evaluates whether a check-in is warranted based on silence duration, mood state, time of day, and recent check-in history — with quiet hours and rate limiting

## How It Works

```
  state.db (Hermes)          conversation_analyzer.py         emotional_state.py
  ┌──────────────┐           ┌──────────────────────┐         ┌──────────────────┐
  │ Sessions     │──────────▶│ Mood detection        │────────▶│ Mood + trend     │
  │ Messages     │           │ Pattern analysis      │         │ Event history    │
  │ Timestamps   │           │ Event detection       │         │ Check-in rules   │
  └──────────────┘           └──────────────────────┘         └──────────────────┘
                                                                       │
                                                                       ▼
                                                              emotional-state.json
                                                              (persistent state)
```

The engine reads conversations from Hermes Agent's SQLite database, runs them through a multi-stage analysis pipeline, and writes results to a JSON state file. The analysis pipeline is fully deterministic — no LLM calls, no embeddings, no API dependencies.

See [How It Works](docs/how-it-works.md) for the full architecture deep-dive.

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/emotional-awareness-engine.git
cd emotional-awareness-engine

# Verify (no dependencies to install)
python3 -m unittest test_engine.py -v

# Run a one-time analysis
python3 outreach_engine_basic.py
```

### Using the API

```python
from emotional_state import load_state, update_mood, should_check_in
from conversation_analyzer import analyze_conversation_mood, extract_emotional_keywords
from outreach_engine_basic import evaluate_emotional_state

# Analyze current emotional state from recent conversations
result = evaluate_emotional_state()
print(f"Mood: {result['state']['current_mood']}")
print(f"Trend: {result['state']['trend']}")
print(f"Sessions analyzed: {result['sessions_analyzed']}")

# Check if a check-in is recommended
decision = result['decision']
if decision['should']:
    print(f"Check-in recommended: {decision['type']} — {decision['reason']}")

# Or analyze a specific message
keywords = extract_emotional_keywords("I'm so exhausted, this deadline is killing me")
# → {'stressed': ['exhausted', 'deadline'], 'tired': ['exhausted']}
```

### Example Output

```
$ python3 outreach_engine_basic.py

=== Emotional Awareness Engine — Analysis Summary ===
Mood: stressed (intensity: 0.67)
Trend: declining
Sessions analyzed: 3
Messages analyzed: 24
Check-in recommended: high_priority — negative mood for 8+ hours
Recent events: 2
  - [stress_spike] Multiple stressed indicators: exhausted, deadline
  - [late_night] Activity at 2:00
```

## Installation

**Requirements:** Python 3.11+, Linux or macOS. That's it.

```bash
git clone https://github.com/YOUR_USERNAME/emotional-awareness-engine.git
cd emotional-awareness-engine
python3 -m unittest test_engine.py -v
```

No `pip install`. No virtual environments. No dependency conflicts. Uses only
Python standard library modules (`json`, `sqlite3`, `re`, `time`, `pathlib`,
`collections`).

See [Installation Guide](docs/installation.md) for Hermes Agent integration.

## Configuration

The engine uses sensible defaults but everything is configurable:

```json
{
  "check_in_rules": {
    "min_hours_between": 12,
    "max_hours_silence": 24,
    "escalation_hours": 48,
    "quiet_hours_start": 23,
    "quiet_hours_end": 7
  }
}
```

See [Configuration Guide](docs/configuration.md) for all options.

## Free vs Premium

| Feature | Open Source | Premium |
|---------|:-----------:|:-------:|
| Mood detection | ✅ | ✅ |
| Pattern recognition | ✅ | ✅ |
| Event tracking | ✅ | ✅ |
| Check-in decision logic | ✅ | ✅ |
| JSON state persistence | ✅ | ✅ |
| Proactive message generation | — | ✅ |
| AI pattern rejection | — | ✅ |
| Smart fallback messages | — | ✅ |
| Telegram/Discord delivery | — | ✅ |
| Self-improving pipeline | — | ✅ |
| Rate limiting policies | — | ✅ |
| Multi-channel support | — | ✅ |

The open-source version gives you the complete analysis engine. The premium
version adds the outreach layer: generating emotionally-aware messages,
validating them for quality, and delivering them through your messaging
channels.

**[Get the Premium Version →](https://gumroad.com/l/emotional-awareness-engine)**

## Academic Foundation

This engine is built on a systematic review of 12 ArXiv papers on emotional
intelligence in conversational AI, affective computing for human-agent
interaction, and sentiment analysis in code-switched dialogue. The full
literature review and design rationale is available as an academic paper.

The test suite covers 197 of 199 planned test cases across mood detection,
pattern recognition, event deduplication, state management, message
validation, and check-in timing logic.

## File Structure

```
emotional-awareness-engine/
├── emotional_state.py          # State manager: load, save, mood updates, check-in logic
├── conversation_analyzer.py    # Mood detection, pattern analysis, event detection
├── outreach_engine_basic.py    # Basic analysis engine (open-source tier)
├── test_engine.py              # Test suite (15 tests)
├── state_schema.json           # JSON Schema for the state file
├── requirements.txt            # Dependencies (none)
├── LICENSE                     # MIT License
├── CONTRIBUTING.md             # Contribution guidelines
└── docs/
    ├── installation.md         # Setup and integration guide
    ├── configuration.md        # All configuration options
    └── how-it-works.md         # Architecture and design decisions
```

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Key areas where help is wanted:
- Additional mood keywords for new languages/dialects
- Improved pattern detection algorithms
- Test coverage for edge cases
- Documentation improvements

## License

MIT License — see [LICENSE](LICENSE).

The open-source version is MIT-licensed and free forever. The premium version
is a separate commercial product with its own license.

---

<p align="center">
  <em>Built for developers who self-host AI agents and want their agents to actually care.</em>
</p>
