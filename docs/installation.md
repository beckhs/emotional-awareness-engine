# Installation

## Requirements

- **Python 3.11+** (uses standard library only — no pip dependencies)
- **Hermes Agent** (for full integration; the engine can also run standalone)
- **Linux or macOS** (Windows may work but is untested)

## Quick Install

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/emotional-awareness-engine.git
cd emotional-awareness-engine

# Run the tests to verify everything works
python3 -m unittest test_engine.py -v

# Run a one-time analysis
python3 outreach_engine_basic.py
```

That's it. No `pip install`, no virtual environments, no dependency conflicts.

## Integration with Hermes Agent

To use the engine as a Hermes skill or cron job:

1. Copy the Python files to your Hermes skills directory:
   ```bash
   cp emotional_state.py conversation_analyzer.py outreach_engine_basic.py \
      ~/.hermes/skills/emotional-engine/
   ```

2. Add a cron job to run the analysis periodically:
   ```bash
   # Example: run emotional analysis every 6 hours
   hermes cron add "Run emotional analysis" --schedule "0 */6 * * *"
   ```

3. The engine will read conversation data from `~/.hermes/state.db` and write
   emotional state to `~/.hermes/emotional-state.json`.

## Verifying the Installation

```bash
# Run the test suite
python3 -m unittest test_engine.py -v

# Expected output: all tests passing
# ...
# Ran 15 tests in 0.0XXs
# OK
```

## File Structure

```
emotional-awareness-engine/
├── emotional_state.py          # State management (load, save, mood updates)
├── conversation_analyzer.py    # Mood detection and pattern analysis
├── outreach_engine_basic.py    # Basic analysis engine (free tier)
├── test_engine.py              # Test suite
├── state_schema.json           # JSON Schema for the state file
├── requirements.txt            # Dependencies (none)
├── docs/
│   ├── installation.md         # This file
│   ├── configuration.md        # Configuration options
│   └── how-it-works.md         # Architecture deep-dive
└── README.md
```

## Upgrading to Premium

The open-source version provides full analysis capabilities. For proactive
outreach, message generation, and delivery features, see the
[premium version](https://gumroad.com/l/emotional-awareness-engine).
