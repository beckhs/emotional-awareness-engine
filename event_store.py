"""
Event Store for the Emotional Memory System.

Stores emotional events in a JSON file, with deduplication and query methods.
Pure Python, no external dependencies.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime
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
            desc_hash = self._description_hash(event.get("description", ""))
            self._dedup_index[desc_hash] = i

    @staticmethod
    def _description_hash(description: str) -> str:
        """Hash the first 80 characters of a description for dedup."""
        truncated = description[:80]
        return hashlib.md5(truncated.encode("utf-8")).hexdigest()

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

        Deduplicates by MD5 hash of the first 80 characters of ``description``.
        If a duplicate is found the existing event is returned unchanged.
        """
        desc_hash = self._description_hash(description)

        # Check for duplicate
        if desc_hash in self._dedup_index:
            return self._events[self._dedup_index[desc_hash]]

        # Build new event
        event = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": event_type,
            "description": description,
            "score": round(score * 0.4, 4),  # MVP formula: intensity * 0.4
            "topic": topic,
            "mood": mood,
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

    def __len__(self) -> int:
        return len(self._events)

    def clear(self):
        """Remove all events (useful for testing)."""
        self._events = []
        self._dedup_index = {}
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
