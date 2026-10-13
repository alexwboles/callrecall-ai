"""Unit tests: rule-based transcript extraction."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callrecall import extract


class TestExtract(unittest.TestCase):
    def test_preferences(self):
        r = extract.extract_rule_based([
            {"role": "user", "text": "I prefer morning callbacks, and I don't like robocalls."},
        ])
        texts = [i.text for i in r["preferences"]]
        self.assertTrue(any("morning callbacks" in t for t in texts), texts)
        self.assertTrue(any("robocalls" in t for t in texts), texts)

    def test_facts(self):
        r = extract.extract_rule_based([
            {"role": "user", "text": "My name is Sam Rivera and my account number is AC-9921."},
        ])
        texts = [i.text for i in r["facts"]]
        self.assertTrue(any("Sam Rivera" in t for t in texts), texts)
        self.assertTrue(any("AC-9921" in t for t in texts), texts)

    def test_resolved(self):
        r = extract.extract_rule_based([
            {"role": "user", "text": "Thanks, that worked — the replacement arrived."},
        ])
        self.assertTrue(r["resolved"], "expected a resolved item")

    def test_open_thread_callback(self):
        r = extract.extract_rule_based([
            {"role": "assistant", "text": "Let me check with the warehouse and I'll call you back."},
            {"role": "user", "text": "Ok thanks."},
        ])
        self.assertTrue(r["open_threads"], "expected an open thread")

    def test_unanswered_question(self):
        r = extract.extract_rule_based([
            {"role": "assistant", "text": "What is your order number?"},
        ])
        self.assertTrue(any("unanswered" in i.text for i in r["open_threads"]))

    def test_answered_question_not_open(self):
        r = extract.extract_rule_based([
            {"role": "assistant", "text": "What is your order number?"},
            {"role": "user", "text": "It's 77881."},
        ])
        self.assertFalse(any("unanswered" in i.text for i in r["open_threads"]))

    def test_plain_text_transcript(self):
        r = extract.extract_rule_based(
            "Agent: How can I help?\nCaller: I prefer email updates.")
        self.assertTrue(r["preferences"])

    def test_llm_hook_merges(self):
        def fake_llm(turns):
            return {"preferences": ["likes pineapple pizza"], "facts": [], "open_threads": [], "resolved": []}
        r = extract.extract_with_hook(
            [{"role": "user", "text": "hello"}], fake_llm)
        self.assertTrue(any("pineapple" in i.text for i in r["preferences"]))

    def test_llm_hook_failure_is_safe(self):
        def bad(turns):
            raise RuntimeError("boom")
        r = extract.extract_with_hook([{"role": "user", "text": "I prefer tea."}], bad)
        self.assertTrue(r["preferences"])

    def test_dedupe_within_call(self):
        r = extract.extract_rule_based([
            {"role": "user", "text": "I prefer morning calls."},
            {"role": "user", "text": "I prefer morning calls!"},
        ])
        self.assertEqual(len(r["preferences"]), 1)


if __name__ == "__main__":
    unittest.main()
