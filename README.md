# Emotional Awareness Engine — v3.0.0

> **🌌 July 2026:** Cosmo (fine-tuned emotion model) + Strategy Pattern + Event-Driven Daemon
> Premium version: [Gumroad $25](https://beckvs.gumroad.com/l/gkgec)

### What's New in v3.0.0
- 🌌 **Cosmo**: Fine-tuned pysentimiento model for emotion detection (85.5% accuracy)
- 🎯 **Strategy Pattern**: 3 detectors — KeywordDetector, PysentimientoDetector, HybridDetector
- 🔄 **Event-Driven Daemon**: Replaces cron jobs with real-time message monitoring
- 🧹 **Neutral Spanish**: All keywords and templates in neutral Spanish (no regional slang)
- 🔧 **Bug Fixes**: Sarcasm detection, timezone-aware quiet hours, dedup with timestamps
- 📊 **293 Tests**: Comprehensive test suite (daemon + engine + regression)

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

## Architecture v3.0

```
┌─────────────────────────────────────────────────────────────┐
│                    TRIGGER LAYER                             │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Cron     │  │ Cosmo Daemon │  │ Manual CLI           │   │
│  │ (2h)     │  │ (event)      │  │ (debug)              │   │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────────────┘   │
│       └───────────────┴────────┬────────┘                    │
│                                │                             │
└────────────────────────────────┼─────────────────────────────┘
                                 │
┌────────────────────────────────┼─────────────────────────────┐
│                    ANALYSIS LAYER                             │
│                                │                             │
│   ┌────────────────────────────▼───────────────────────┐    │
│   │           EmotionDetector (Strategy Pattern)        │    │
│   │                                                     │    │
│   │  ┌─────────────────┐  ┌─────────────────────────┐  │    │
│   │  │ KeywordDetector  │  │ PysentimientoDetector   │  │    │
│   │  │ (fast, fallback) │  │ (Cosmo fine-tuned)      │  │    │
│   │  └─────────────────┘  └─────────────────────────┘  │    │
│   │  ┌──────────────────────────────────────────────┐  │    │
│   │  │ HybridDetector (recommended — best of both)   │  │    │
│   │  └──────────────────────────────────────────────┘  │    │
│   └─────────────────────────────────────────────────────┘    │
│                                                               │
│   ┌───────────────────┐  ┌─────────────────────────────┐    │
│   │ conversation_     │  │ EventDetector               │    │
│   │ analyzer v3.0     │  │ (regex + emotion scoring)   │    │
│   └───────────────────┘  └─────────────────────────────┘    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────┼─────────────────────────────┐
│                    PERSISTENCE LAYER                          │
│   ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │
│   │ EventStore│  │ DIMF      │  │ TBC      │  │ emotional│  │
│   │ (JSON)   │  │ Filter    │  │ (comp)   │  │ _state   │  │
│   └──────────┘  └───────────┘  └──────────┘  └──────────┘  │
└───────────────────────────────────────────────────────────────┘
```

## Components

| Component | File | Description |
|-----------|------|-------------|
| **EmotionDetector** | `emotion_detector.py` | Strategy Pattern with 3 detector implementations |
| **HybridDetector** | `emotion_detector.py` | Combines pysentimiento (sarcasm/negation) with keywords (fast) |
| **Cosmo Daemon** | `daemon.py` | Event-driven daemon, monitors state.db in real-time |
| **Conversation Analyzer** | `conversation_analyzer.py` | Analyzes conversations, detects events and mood |
| **DIMF** | `dimf.py` | Dynamic Importance Memory Filter (Decay × Intensity × Multiplicity) |
| **TBC** | `tbc.py` | Temporal Binary Compression for old events |
| **Event Store** | `event_store.py` | JSON-based event storage with deduplication |
| **Emotional State** | `emotional_state.py` | Persistent mood state with rate limiting |
| **Outreach Engine** | `outreach_engine.py` | Main orchestrator (legacy, replaced by daemon) |
| **Config** | `config.py` | Centralized configuration |

## Quick Start

```bash
# Install dependencies
pip install pysentimiento transformers torch psutil

# Run the daemon (event-driven)
python daemon.py --interval 15

# Or run the daemon as a systemd service
sudo cp cosmo-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cosmo-watcher

# Run tests
python -m pytest test_*.py -v
```

## Cosmo — Fine-Tuned Emotion Model

Cosmo is a fine-tuned pysentimiento model trained on 18,464 examples of neutral Spanish text. It improves emotion detection for indirect expressions, mixed emotions, and subtle sadness.

**Performance:**
| Emotion | F1 Score |
|---------|----------|
| joy | 94.3% |
| sadness | 91.8% |
| disgust | 93.5% |
| fear | 87.0% |
| others | 63.4% |
| anger | 49.7% |
| surprise | 45.5% |

**Accuracy:** 85.5% | **Macro F1:** 75.0%

To use Cosmo, place the fine-tuned model in `fine-tuning/fine-tuned-model/` and the HybridDetector will automatically load it.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Premium Version

The full Emotional Intelligence Suite includes:
- Cosmo fine-tuned model (416MB)
- Full daemon with systemd integration
- Complete test suite (293 tests)
- Research papers and architecture docs
- Home Assistant integration

**[Get it on Gumroad — $25](https://beckvs.gumroad.com/l/gkgec)**
