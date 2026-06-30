# Configuration

The Emotional Awareness Engine is configured through the emotional state file
at `~/.hermes/emotional-state.json`. The engine uses sensible defaults — you
only need to customize if you want to change behavior.

## State File Location

Default: `~/.hermes/emotional-state.json`

The file is created automatically on first run with default values. You can
edit it directly or use the Python API.

## Check-In Rules

These control when the engine recommends a check-in:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_hours_between` | 12 | Minimum hours between any two check-ins |
| `max_hours_silence` | 24 | Hours of silence before a normal check-in |
| `escalation_hours` | 48 | Hours of silence before escalating |
| `quiet_hours_start` | 23 | Hour when quiet period begins (24h format) |
| `quiet_hours_end` | 7 | Hour when quiet period ends (24h format) |

Example — more aggressive check-ins:

```json
{
  "check_in_rules": {
    "min_hours_between": 8,
    "max_hours_silence": 16,
    "escalation_hours": 36,
    "quiet_hours_start": 22,
    "quiet_hours_end": 8
  }
}
```

Example — more conservative (less frequent):

```json
{
  "check_in_rules": {
    "min_hours_between": 24,
    "max_hours_silence": 48,
    "escalation_hours": 72,
    "quiet_hours_start": 21,
    "quiet_hours_end": 9
  }
}
```

## Mood Keywords

Mood detection is keyword-based. The default keywords are defined in
`conversation_analyzer.py` in the `MOOD_KEYWORDS` dictionary. You can
customize them:

```python
# In conversation_analyzer.py
MOOD_KEYWORDS = {
    "stressed": ["can't do this", "overwhelmed", "deadline", ...],
    "happy": ["awesome", "it worked", "perfect", ...],
    "tired": ["exhausted", "can't sleep", "drained", ...],
    "frustrated": ["not working", "error", "bug", ...],
    "excited": ["incredible", "wow", "let's go", ...],
}
```

To add a new mood category, add a new key to the dictionary with appropriate
keywords. The analysis pipeline will automatically pick it up.

## Analysis Window

The default analysis window is 48 hours. To change it:

```python
from outreach_engine_basic import evaluate_emotional_state
# The default is 48 hours, but you can modify get_recent_sessions()
from conversation_analyzer import get_recent_sessions
sessions = get_recent_sessions(hours=24)  # Last 24 hours only
```

## State Schema

The full JSON Schema for the state file is in `state_schema.json`. This
defines all valid fields, types, and constraints.

## Environment Variables

The engine doesn't use environment variables for configuration. All settings
are in the state file or the source code.

## Premium Configuration

The premium version adds additional configuration options:

- Rate limiting policies (per-channel, per-user)
- Multi-channel delivery settings
- Message generation model selection
- Self-improving pipeline tuning
- Custom personality profiles

See the [premium documentation](https://gumroad.com/l/emotional-awareness-engine)
for details.
