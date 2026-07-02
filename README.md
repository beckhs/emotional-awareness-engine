# Emotional Awareness Engine — v2.1.0

> **🆕 July 2026:** Bug fixes + Anti-Spam + Event Store + Auto-Awareness
> Premium version: [Gumroad $25](https://beckvs.gumroad.com/l/gkgec)

### What's New in v2.1.0
- 🗑️ System messages no longer detected as user achievements
- 📉 Mood intensity: 0.20 → 0.80 (density-based formula)
- 🛡️ Anti-spam: 3 unanswered → silence. 7 days → final message.
- 💾 Event Store: structured events with scoring
- 🧠 Auto-awareness: engine reads chat history to know what it said
- ⏱️ Adaptive rate limiting: 12h → 4h → 2h

---
<!-- Emotional Awareness Engine README -->
<p align="center">
  <strong>🧠 Emotional Awareness Engine</strong><br>
  <em>Genuine Emotional Intelligence for AI Agents</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-23%20passing-brightgreen.svg" alt="Tests Passing">
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
git clone https://github.com/beckhs/emotional-awareness-engine.git
cd emotional-awareness-engine

# Verify (no dependencies to install)
python3 -m unittest test_engine.py -v

# Run a one-time analysis
python3 outreach_engine.py
```

## Premium Version

Get the full Emotional Intelligence Suite with research paper, marketing materials, and advanced features:

👉 **[Gumroad — $25 USD](https://beckvs.gumroad.com/l/gkgec)**

Includes: academic paper (18 references), landing page, social media templates, tutorial, HA/Watch4 integration.

## License

MIT — Free for personal and commercial use.
