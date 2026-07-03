"""
Event Store for the Emotional Memory System.

Stores emotional events in a JSON file, with deduplication and query methods.
Pure Python, no external dependencies.
"""

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional


class EventStore:
    """Reads/writes emotional events to a JSON file."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            filepath = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "events.json"
            )
        self.filepath = filepath
        self._events: list[dict] = []
        self._dedup_index: dict[str, int] = {}  # hash -> index in _events
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self):
        """Load events from the JSON file, or start fresh if it doesn't exist."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    content = f.read().strip()
                    self._events = json.loads(content) if content else []
            except (json.JSONDecodeError, ValueError):
                self._events = []
        else:
            self._events = []
        self._rebuild_index()

    def _save(self):
        """Persist events to the JSON file."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self._events, f, indent=2, ensure_ascii=False)

    def _rebuild_index(self):
        """Rebuild the deduplication index from current events."""
        self._dedup_index = {}
        for i, event in enumerate(self._events):
            desc_hash = self._description_hash(
                event.get('description', ''),
                event.get('timestamp', ''),
            )
            self._dedup_index[desc_hash] = i

    @staticmethod
    def _description_hash(description: str, timestamp: str = '') -> str:
        """Hash description + timestamp for dedup. Full description, not truncated."""
        key = f'{description}|{timestamp}'
        return hashlib.md5(key.encode('utf-8')).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_event(
        self,
        event_type: str,
        description: str,
        score: float = 0.0,
        topic: str = "",
        mood: str = "",
    ) -> dict:
        """
        Add a new emotional event.

        The *score* parameter is treated as intensity; the stored score is
        computed as ``intensity * 0.4`` (MVP simple formula).

        Deduplicates by MD5 hash of description + timestamp.
        If a duplicate is found the existing event is returned unchanged.
        """
        # Build timestamp first so we can include it in the hash
        from datetime import datetime, timezone
        ts_str = datetime.now(timezone.utc).isoformat().replace('+00:00', '') + 'Z'

        desc_hash = self._description_hash(description, ts_str)

        # Check for duplicate (same description within same second)
        if desc_hash in self._dedup_index:
            return self._events[self._dedup_index[desc_hash]]

        # Build new event
        event = {
            'id': str(uuid.uuid4()),
            'timestamp': ts_str,
            "type": event_type,
            "description": description,
            "score": round(score * 0.4, 4),  # MVP formula: intensity * 0.4
            "topic": topic,
            "mood": mood,
            "importance": self.get_importance_level({"score": round(score * 0.4, 4)}),
        }

        self._events.append(event)
        self._dedup_index[desc_hash] = len(self._events) - 1
        self._save()
        return event

    def get_recent_events(self, limit: int = 5) -> list[dict]:
        """Return the most recent events, sorted by timestamp descending."""
        sorted_events = sorted(
            self._events, key=lambda e: e.get("timestamp", ""), reverse=True
        )
        return sorted_events[:limit]

    def get_events_for_date(self, date_str: str) -> list[dict]:
        """
        Return all events that occurred on the given date.

        *date_str* should be in ISO date format, e.g. ``"2026-07-02"``.
        """
        return [
            e
            for e in self._events
            if e.get("timestamp", "").startswith(date_str)
        ]

    def get_top_events(self, limit: int = 10) -> list[dict]:
        """Return events sorted by score descending (highest intensity first)."""
        sorted_events = sorted(
            self._events, key=lambda e: e.get("score", 0.0), reverse=True
        )
        return sorted_events[:limit]

    # ------------------------------------------------------------------
    # DIMF – Dynamic Importance Memory Filter
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_timestamp(ts: str) -> float:
        """Parse an ISO timestamp string to a Unix epoch float."""
        # Strip trailing 'Z' for fromisoformat compatibility
        clean = ts.rstrip("Z")
        return datetime.fromisoformat(clean).timestamp()

    def compute_dimf_score(self, event: dict, now: float = None) -> float:
        """Compute a DIMF importance score for *event*.

        Components:
        - decay: half-life of 7 days
        - intensity: stored score / 0.4
        - multiplicity: ×1.5 per sibling with same topic within 24 h (cap ×2.25)
        """
        if now is None:
            now = time.time()

        ts = event.get("timestamp", "")
        if not ts:
            return 0.01

        try:
            event_epoch = self._parse_timestamp(ts)
        except (ValueError, TypeError):
            return 0.01

        age_days = max((now - event_epoch) / 86400.0, 0.0)
        decay = 0.5 ** (age_days / 7.0)

        stored_score = event.get("score", 0.0)
        intensity = stored_score / 0.4 if 0.4 else 0.0

        # Multiplicity: count siblings with same topic within ±24 h
        topic = event.get("topic", "")
        multiplicity = 1.0
        if topic:
            sibling_count = 0
            for other in self._events:
                if other is event:
                    continue
                if other.get("topic", "") != topic:
                    continue
                try:
                    other_epoch = self._parse_timestamp(other.get("timestamp", ""))
                except (ValueError, TypeError):
                    continue
                if abs(other_epoch - event_epoch) <= 86400.0:
                    sibling_count += 1
            # Each sibling adds ×1.5, capped at ×2.25 total
            for _ in range(sibling_count):
                multiplicity *= 1.5
                if multiplicity >= 2.25:
                    multiplicity = 2.25
                    break

        raw = intensity * decay * multiplicity * 0.4
        return max(0.01, min(raw, 1.0))

    @staticmethod
    def get_importance_level(event: dict) -> str:
        """Return 'alta', 'media', or 'baja' based on stored score."""
        score = event.get("score", 0.0)
        if score > 0.6:
            return "alta"
        elif score > 0.3:
            return "media"
        else:
            return "baja"

    def prune_old_events(self, days: int = 30, keep_top: int = 10):
        """Remove events older than *days*, but always preserve the global top-*keep_top* by score."""
        if not self._events:
            return

        cutoff = time.time() - days * 86400.0

        # Identify top-N events globally (by score) to always keep
        ranked = sorted(self._events, key=lambda e: e.get("score", 0.0), reverse=True)
        protected = {id(e) for e in ranked[:keep_top]}

        pruned = []
        for event in self._events:
            if id(event) in protected:
                pruned.append(event)
                continue
            try:
                epoch = self._parse_timestamp(event.get("timestamp", ""))
            except (ValueError, TypeError):
                pruned.append(event)  # keep if we can't parse
                continue
            if epoch >= cutoff:
                pruned.append(event)

        self._events = pruned
        self._rebuild_index()
        self._save()

    def get_checkin_context(self) -> dict:
        """Return a context dict suitable for a daily check-in prompt."""
        recent = self.get_recent_events(5)
        top = self.get_top_events(3)

        # Yesterday summary: top-5 events whose date is yesterday
        from datetime import timezone as _tz
        yesterday = (datetime.now(_tz.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday_events = [
            e for e in self._events
            if e.get("timestamp", "").startswith(yesterday)
        ]
        yesterday_top = sorted(
            yesterday_events, key=lambda e: e.get("score", 0.0), reverse=True
        )[:5]
        yesterday_summary = " | ".join(
            e.get("description", "") for e in yesterday_top
        ) if yesterday_top else ""

        # Importance counts
        counts = {"alta": 0, "media": 0, "baja": 0}
        for e in self._events:
            level = e.get("importance", self.get_importance_level(e))
            if level in counts:
                counts[level] += 1

        return {
            "recent": recent,
            "top": top,
            "yesterday_summary": yesterday_summary,
            "importance_counts": counts,
        }

    def __len__(self) -> int:
        return len(self._events)

    def clear(self):
        """Remove all events (useful for testing)."""
        self._events = []
        self._dedup_index = {}
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
