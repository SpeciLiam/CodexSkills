"""Unit tests for the pure helpers in agent_inbox.py (no network)."""

import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent_inbox


class TestAgentInbox(unittest.TestCase):
    def test_new_key_is_sortable_and_prefixed(self):
        now = datetime(2026, 7, 2, 9, 30, 15, tzinfo=timezone.utc)
        key = agent_inbox.new_key(now)
        self.assertTrue(re.fullmatch(r"agent_req:20260702093015-[a-z0-9]{4}", key), key)

    def test_build_reply_value_preserves_text_and_created(self):
        existing = {"text": "add padmapper", "status": "open", "created": "2026-07-02T01:00:00Z"}
        v = agent_inbox.build_reply_value(existing, "duplicates Zumper; skipped")
        self.assertEqual(v["status"], "answered")
        self.assertEqual(v["text"], "add padmapper")
        self.assertEqual(v["created"], "2026-07-02T01:00:00Z")
        self.assertEqual(v["reply"], "duplicates Zumper; skipped")
        self.assertTrue(v["answeredAt"])

    def test_build_closed_value_keeps_reply_if_present(self):
        existing = {"text": "t", "status": "answered", "reply": "done", "created": "c", "answeredAt": "a"}
        v = agent_inbox.build_closed_value(existing)
        self.assertEqual(v["status"], "closed")
        self.assertEqual(v["reply"], "done")
        # No reply -> field simply absent, not None
        v2 = agent_inbox.build_closed_value({"text": "t", "status": "open"})
        self.assertEqual(v2, {"text": "t", "status": "closed"})

    def test_find_accepts_suffix_and_rejects_ambiguity(self):
        reqs = [
            {"key": "agent_req:20260702-aaaa", "text": "one"},
            {"key": "agent_req:20260702-bbbb", "text": "two"},
        ]
        self.assertEqual(agent_inbox.find(reqs, "agent_req:20260702-aaaa")["text"], "one")
        self.assertEqual(agent_inbox.find(reqs, "bbbb")["text"], "two")
        self.assertIsNone(agent_inbox.find(reqs, "20260702"))  # matches both -> ambiguous
        self.assertIsNone(agent_inbox.find(reqs, "zzzz"))


if __name__ == "__main__":
    unittest.main()
