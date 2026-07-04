# Emotional Awareness Engine — v3.0.0

> **🌌 July 2026:** Cosmo fine-tuned emotion model + Strategy Pattern + Event-Driven Daemon
> Premium version: [Gumroad $25](https://beckvs.gumroad.com/l/gkgec)

---

<!-- Emotional Awareness Engine README -->
<p align="center">
  <strong>🧠 Emotional Awareness Engine</strong><br>
  <em>Genuine Emotional Intelligence for AI Agents</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-293%20passing-brightgreen.svg" alt="Tests Passing">
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
  ┌──────────────┐           ┌──────────────────────┐                 │
  │ EventStore   │◀──────────│ DIMF scoring          │◀────────────────┘
  │ (JSON)       │           │ TBC compression       │
  └──────────────┘           └──────────────────────┘
```

---

## Changelog

### v3.0.0 — July 2026

**🌌 Cosmo — Fine-Tuned Emotion Model (Premium)**

The headline feature: a fine-tuned pysentimiento model trained on 18,464 examples of neutral Spanish text. Cosmo improves emotion detection for indirect expressions, mixed emotions, and subtle sadness that keyword matching misses.

| Emotion | F1 Score | Example |
|---------|----------|---------|
| joy | 94.3% | "¡Estoy muy feliz por el resultado!" |
| sadness | 91.8% | "No es que no me importe, simplemente no sé qué hacer" |
| disgust | 93.5% | — |
| fear | 87.0% | "Si me llegara a pasar eso, me estresaría" |
| anger | 49.7% | "Otra vez el mismo error, ya basta" |

**Accuracy:** 85.5% | **Macro F1:** 75.0%

**New Features:**
- 🎯 **Strategy Pattern** — 3 interchangeable detectors: KeywordDetector (fast), PysentimientoDetector (ML), HybridDetector (recommended, combines both)
- 🔄 **Cosmo Daemon** — Event-driven daemon that monitors state.db in real-time, replaces cron jobs for instant emotion detection
- 🔧 **Config module** — Centralized configuration (timezone, thresholds, rate limits)
- 🧹 **Neutral Spanish** — All keywords and templates in neutral Spanish (no regional slang)

**Bug Fixes:**
- Sarcasm detection: "genial, todo falló" now correctly detects frustration
- Timezone-aware quiet hours (respects user timezone, not server)
- Dedup includes timestamp (events with same description but different time are preserved)
- System message filtering expanded (filters Hermes internal notifications)
- Removed duplicate keywords in MOOD_KEYWORDS

**Tests:** 293 passing (145 new + 148 existing)

---

### v2.1.0 — July 2026

- 🗑️ System messages no longer detected as user achievements
- 📉 Mood intensity: 0.20 → 0.80 (density-based formula)
- 🛡️ Anti-spam: 3 unanswered → silence. 7 days → final message.
- 💾 Event Store: structured events with scoring
- 🧠 Auto-awareness: engine reads chat history to know what it said
- ⏱️ Adaptive rate limiting: 12h → 4h → 2h

---

### v2.0 — June 2026

- Initial public release
- Keyword-based mood detection
- Conversation analysis from Hermes state.db
- Pattern recognition (active hours, communication cadence)
- Significant event tracking
- Smart check-in decisions with quiet hours

---

## Premium vs Free

| Feature | Free (GitHub) | Premium (Gumroad $25) |
|---------|--------------|----------------------|
| Keyword mood detection | ✅ | ✅ |
| Event Store + DIMF + TBC | ✅ | ✅ |
| Anti-spam + rate limiting | ✅ | ✅ |
| Conversation analysis | ✅ | ✅ |
| **Cosmo model (fine-tuned)** | ❌ | ✅ |
| **Strategy Pattern (3 detectors)** | ❌ | ✅ |
| **Event-driven daemon** | ❌ | ✅ |
| **Systemd integration** | ❌ | ✅ |
| **293 tests** | Basic | Full suite |
| **Home Assistant integration** | ❌ | ✅ |

---

## Quick Start

```bash
# Install dependencies
pip install pysentimiento transformers torch psutil

# Run the daemon (event-driven)
python daemon.py --interval 15

# Or run as systemd service
sudo cp cosmo-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cosmo-watcher

# Run tests
python -m pytest test_*.py -v
```

## License

MIT License — see [LICENSE](LICENSE) for details.

**[Get Premium — $25](https://beckvs.gumroad.com/l/gkgec)**
