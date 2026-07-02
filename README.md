# Emotional Awareness Engine

Open-source emotional intelligence for AI agents. Free version of the Emotional Intelligence Suite.

## v2.1.0 — Bug Fixes & Anti-Spam (July 2026)

### Bugs Fixed
- 🗑️ System messages no longer detected as user achievements
- 📉 Mood intensity improved: 0.20 → 0.80 (density-based formula)
- 🔄 Lock file prevents concurrent engine runs
- 🧹 Clean emotional state — no false data

### New Features
- 🛡️ Anti-spam: 3 unanswered check-ins → silence. 7 days → final message.
- 💾 Event Store: structured event storage with scoring (`event_store.py`)
- 💬 Contextual fallbacks: messages reference real events even when LLM is down
- 🧠 Auto-awareness: engine reads chat history to know what it already said
- ⏱️ Adaptive rate limiting: 12h normal → 4h stressed → 2h crisis

## Quick Start
```bash
python3 outreach_engine.py
```

## License
MIT — Free for personal and commercial use.
Premium version with full paper + marketing materials: [Gumroad](https://beckvs.gumroad.com/l/gkgec)
