"""
Unit tests for the Event Store module.
"""

import os
import json
import tempfile
import unittest
from event_store import EventStore


class TestEventStore(unittest.TestCase):
    """Verify core EventStore functionality."""

    def setUp(self):
        """Create a fresh EventStore pointed at a temporary file."""
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.store = EventStore(filepath=self.tmp.name)

    def tearDown(self):
        """Clean up the temporary file."""
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    # ------------------------------------------------------------------
    # Test 1: Create
    # ------------------------------------------------------------------

    def test_create_event(self):
        """Adding an event stores it with the correct schema fields and returns it."""
        event = self.store.add_event(
            event_type="joy",
            description="User expressed happiness about the weather",
            score=0.9,
            topic="weather",
            mood="happy",
        )

        # Check return value schema
        self.assertIn("id", event)
        self.assertIn("timestamp", event)
        self.assertEqual(event["type"], "joy")
        self.assertEqual(event["description"], "User expressed happiness about the weather")
        # Stored score = intensity (0.9) * 0.4 = 0.36
        self.assertAlmostEqual(event["score"], 0.36, places=4)
        self.assertEqual(event["topic"], "weather")
        self.assertEqual(event["mood"], "happy")

        # Check internal storage
        self.assertEqual(len(self.store), 1)

        # Verify persistence — reload from file
        store2 = EventStore(filepath=self.tmp.name)
        self.assertEqual(len(store2), 1)
        reloaded = store2.get_recent_events(limit=1)[0]
        self.assertEqual(reloaded["id"], event["id"])
        self.assertAlmostEqual(reloaded["score"], 0.36, places=4)

    # ------------------------------------------------------------------
    # Test 2: Deduplication
    # ------------------------------------------------------------------

    def test_deduplication(self):
        """Adding the same description (first 80 chars) returns the original event."""
        desc = "A" * 100  # 100-character description, first 80 used for dedup

        e1 = self.store.add_event(
            event_type="sadness",
            description=desc,
            score=0.5,
        )

        # Second call — same first 80 chars but different score/type
        e2 = self.store.add_event(
            event_type="anger",       # different type
            description=desc,         # same first 80 chars
            score=0.9,                # different score
        )

        # Should return the original event, unchanged
        self.assertEqual(e2["id"], e1["id"])
        self.assertEqual(e2["type"], "sadness")  # original type preserved
        self.assertAlmostEqual(e2["score"], 0.2, places=4)  # original score (0.5*0.4)

        # Only one event in the store
        self.assertEqual(len(self.store), 1)

    # ------------------------------------------------------------------
    # Test 3: get_recent_events
    # ------------------------------------------------------------------

    def test_get_recent_events(self):
        """get_recent_events returns events sorted by timestamp descending."""
        self.store.add_event("neutral", "First event", score=0.3)
        self.store.add_event("neutral", "Second event", score=0.4)
        self.store.add_event("neutral", "Third event", score=0.5)

        recent = self.store.get_recent_events(limit=2)
        self.assertEqual(len(recent), 2)

        # Third event should be most recent (last added)
        self.assertEqual(recent[0]["description"], "Third event")
        self.assertEqual(recent[1]["description"], "Second event")

        # Default limit of 5
        all_recent = self.store.get_recent_events()
        self.assertEqual(len(all_recent), 3)

    # ------------------------------------------------------------------
    # Test 4: Score calculation (intensity * 0.4)
    # ------------------------------------------------------------------

    def test_score_calculation(self):
        """Stored score = intensity * 0.4 for various inputs."""
        test_cases = [
            (1.0, 0.4),
            (0.5, 0.2),
            (0.0, 0.0),
            (0.75, 0.3),
            (0.99, 0.396),
        ]

        for intensity, expected_stored in test_cases:
            with self.subTest(intensity=intensity):
                event = self.store.add_event(
                    event_type="test",
                    description=f"Score test {intensity}",
                    score=intensity,
                )
                self.assertAlmostEqual(
                    event["score"], expected_stored, places=4,
                    msg=f"Intensity {intensity} should yield stored score {expected_stored}"
                )

    # ------------------------------------------------------------------
    # Bonus checks
    # ------------------------------------------------------------------

    def test_get_events_for_date(self):
        """get_events_for_date filters by date prefix."""
        self.store.add_event("test", "Today event")
        recent = self.store.get_recent_events(limit=1)[0]
        ts = recent["timestamp"]
        date_only = ts[:10]  # "YYYY-MM-DD"

        events = self.store.get_events_for_date(date_only)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["description"], "Today event")

    def test_get_top_events(self):
        """get_top_events sorts by score descending."""
        self.store.add_event("a", "Lowest", score=0.1)   # stored: 0.04
        self.store.add_event("b", "Highest", score=1.0)  # stored: 0.4
        self.store.add_event("c", "Middle", score=0.5)   # stored: 0.2

        top = self.store.get_top_events(limit=10)
        self.assertEqual(len(top), 3)
        self.assertEqual(top[0]["description"], "Highest")   # 0.4
        self.assertEqual(top[1]["description"], "Middle")    # 0.2
        self.assertEqual(top[2]["description"], "Lowest")    # 0.04


if __name__ == "__main__":
    unittest.main()
