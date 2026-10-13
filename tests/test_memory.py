"""Unit tests: memory core, store, toggles, expiry, skippable, backfill."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callrecall import CallRecallMemory, CallerBrief, BriefItem, JsonFileStore


def fresh_mem(**kw):
    tmp = tempfile.mkdtemp()
    kw.setdefault("path", os.path.join(tmp, "memory.json"))
    return CallRecallMemory(**kw), tmp


class TestStore(unittest.TestCase):
    def test_roundtrip_and_atomic(self):
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "m.json")
        s = JsonFileStore(p)
        s.put("c1", {"contact_id": "c1"})
        self.assertEqual(s.get("c1")["contact_id"], "c1")
        self.assertTrue(s.delete("c1"))
        self.assertFalse(s.delete("c1"))
        self.assertEqual(s.contact_ids(), [])

    def test_file_is_human_readable_json(self):
        mem, tmp = fresh_mem()
        mem.record_call("c1", [{"role": "user", "text": "I prefer mornings."}])
        with open(os.path.join(tmp, "memory.json")) as f:
            data = json.load(f)
        self.assertIn("c1", data["contacts"])


class TestMemory(unittest.TestCase):
    def test_record_and_recall(self):
        mem, _ = fresh_mem()
        mem.record_call("555", [
            {"role": "assistant", "text": "Hi!"},
            {"role": "user", "text": "I prefer text updates."},
        ], display_name="Sam")
        b = mem.brief("555")
        self.assertIsNotNone(b)
        self.assertEqual(b.display_name, "Sam")
        self.assertEqual(b.call_count, 1)
        self.assertTrue(any("text updates" in i.text for i in b.preferences))

    def test_unknown_caller(self):
        mem, _ = fresh_mem()
        self.assertIsNone(mem.brief("nobody"))
        self.assertEqual(mem.context_block("nobody"), "")
        self.assertEqual(mem.skippable("nobody", ["Ask name"]), [])

    def test_save_toggle_off(self):
        mem, _ = fresh_mem(save_enabled=False)
        mem.record_call("c", [{"role": "user", "text": "I prefer tea."}])
        self.assertIsNone(mem.brief("c"))

    def test_recall_toggle_off(self):
        mem, _ = fresh_mem()
        mem.record_call("c", [{"role": "user", "text": "I prefer tea."}])
        mem.recall_enabled = False
        self.assertIsNone(mem.brief("c"))
        self.assertEqual(mem.context_block("c"), "")

    def test_pii_redacted_by_default(self):
        mem, _ = fresh_mem()
        mem.record_call("c", [
            {"role": "user", "text": "My email is sam@example.com and my number is 555-123-4567."},
        ])
        b = mem.brief("c")
        blob = json.dumps(b.to_dict())
        self.assertNotIn("sam@example.com", blob)
        self.assertNotIn("555-123-4567", blob)
        self.assertIn("[EMAIL]", blob)

    def test_pii_toggle_off(self):
        mem, _ = fresh_mem(redact_pii=False)
        mem.record_call("c", [{"role": "user", "text": "My email is sam@example.com."}])
        blob = json.dumps(mem.brief("c").to_dict())
        self.assertIn("sam@example.com", blob)

    def test_resolved_expiry(self):
        mem, _ = fresh_mem(resolve_expiry_days=30)
        mem.record_call("c", [{"role": "user", "text": "Thanks, that worked!"}])
        b = mem.brief("c")
        self.assertTrue(b.resolved)
        # fake the clock: mark the item long expired
        past = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        b.resolved[0].valid_until = past
        mem.store.put("c", b.to_dict())
        b2 = mem.brief("c")
        self.assertEqual(b2.resolved, [])

    def test_resolution_closes_open_thread(self):
        mem, _ = fresh_mem()
        mem.record_call("c", [
            {"role": "assistant", "text": "I'll check the warehouse and call you back about the replacement."},
        ])
        self.assertTrue(mem.brief("c").open_threads)
        mem.record_call("c", [
            {"role": "user", "text": "Thanks, the replacement arrived — all resolved!"},
        ])
        b = mem.brief("c")
        self.assertTrue(b.resolved)
        # the warehouse callback thread should be closed by the resolution
        self.assertFalse(any("warehouse" in t.text for t in b.open_threads),
                         [t.text for t in b.open_threads])

    def test_skippable(self):
        mem, _ = fresh_mem()
        mem.record_call("c", [
            {"role": "user", "text": "My account number is AC-9921."},
        ])
        skip = mem.skippable("c", [
            "Ask the caller for their account number",
            "Ask the caller about their weekend plans",
        ])
        self.assertIn("Ask the caller for their account number", skip)
        self.assertNotIn("Ask the caller about their weekend plans", skip)

    def test_backfill(self):
        mem, _ = fresh_mem()
        mem.backfill("c", [
            [{"role": "user", "text": "I prefer morning calls."}],
            [{"role": "user", "text": "My name is Sam Rivera."}],
        ])
        b = mem.brief("c")
        self.assertEqual(b.call_count, 2)
        self.assertTrue(b.preferences)
        self.assertTrue(b.facts)

    def test_forget(self):
        mem, _ = fresh_mem()
        mem.record_call("c", [{"role": "user", "text": "I prefer tea."}])
        self.assertTrue(mem.forget("c"))
        self.assertIsNone(mem.brief("c"))

    def test_search(self):
        mem, _ = fresh_mem()
        mem.record_call("a", [{"role": "user", "text": "I prefer morning callbacks."}])
        mem.record_call("b", [{"role": "user", "text": "I love gardening."}])
        hits = mem.search("morning callbacks")
        self.assertTrue(hits and hits[0][0] == "a", hits)

    def test_empty_contact_id_rejected(self):
        mem, _ = fresh_mem()
        with self.assertRaises(ValueError):
            mem.record_call("", [{"role": "user", "text": "hi"}])


class TestBrief(unittest.TestCase):
    def test_prune_expired(self):
        b = CallerBrief(contact_id="c", resolved=[
            BriefItem(text="old", valid_until="2000-01-01T00:00:00+00:00"),
            BriefItem(text="fresh"),
        ])
        self.assertEqual(b.prune_expired(), 1)
        self.assertEqual(len(b.resolved), 1)


if __name__ == "__main__":
    unittest.main()
