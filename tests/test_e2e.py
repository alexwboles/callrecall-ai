"""End-to-end: two calls from one caller, full middleware lifecycle.

Simulates the Retell Memory demo scenario (lost package -> replacement)
through the Pipecat shim processor: session start injects the brief,
skippable flow steps are detected, the second call resolves the thread,
PII is redacted in the store file, and everything survives a restart.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callrecall import CallRecallMemory
from callrecall.adapters import CallRecallPipecat, CallRecallLiveKit

CALLER = "+15551234567"

CALL_1 = [
    {"role": "assistant", "text": "Thanks for calling Acme Shipping. How can I help?"},
    {"role": "user", "text": "Hi, my package never arrived. My email is sam.rivera@example.com and my number is 555-123-4567."},
    {"role": "assistant", "text": "I'm sorry to hear that. What is your order number?"},
    {"role": "user", "text": "It's order 77881. I'd like a replacement sent, and I prefer text updates."},
    {"role": "assistant", "text": "Let me check with the warehouse and I'll call you back about the replacement."},
    {"role": "user", "text": "Ok, thanks."},
]

CALL_2 = [
    {"role": "assistant", "text": "Hi Sam, calling back about your replacement."},
    {"role": "user", "text": "Yes! The replacement arrived yesterday — thanks, that worked."},
    {"role": "assistant", "text": "Wonderful. Anything else I can do?"},
    {"role": "user", "text": "Nope, we're all set."},
]

FLOW_STEPS = [
    "Ask the caller what the problem is",
    "Ask the caller for their order number",
    "Ask the caller how they would like to be updated",
]


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "memory.json")

    def test_two_call_lifecycle(self):
        # ---- call 1 -------------------------------------------------
        mem = CallRecallMemory(path=self.path)
        pipe = CallRecallPipecat(mem)
        proc = pipe.processor(contact_id=CALLER)

        out = proc.process_frame({"type": "session_start"})
        self.assertEqual(out, [])  # brand-new caller: nothing to inject

        proc.process_frame({"type": "user_message", "text": "hello"})  # passthrough
        saved = proc.process_frame({"type": "call_end", "transcript": CALL_1})
        self.assertEqual(saved[0]["type"], "saved")

        brief = mem.brief(CALLER)
        self.assertEqual(brief.call_count, 1)
        self.assertTrue(brief.open_threads, "warehouse callback should be an open thread")
        self.assertTrue(any("text updates" in p.text for p in brief.preferences))

        # ---- call 2: a fresh process, same file ----------------------
        mem2 = CallRecallMemory(path=self.path)
        pipe2 = CallRecallPipecat(mem2)
        proc2 = pipe2.processor(contact_id=CALLER)

        out = proc2.process_frame({"type": "session_start"})
        self.assertEqual(len(out), 1)
        ctx = out[0]["text"]
        self.assertIn("prior call", ctx)
        self.assertIn("replacement", ctx)  # open thread injected

        skip = mem2.skippable(CALLER, FLOW_STEPS)
        self.assertIn("Ask the caller what the problem is", skip)
        self.assertIn("Ask the caller for their order number", skip)
        self.assertIn("Ask the caller how they would like to be updated", skip)

        proc2.process_frame({"type": "call_end", "transcript": CALL_2})
        brief2 = mem2.brief(CALLER)
        self.assertEqual(brief2.call_count, 2)
        self.assertTrue(brief2.resolved, "replacement arrival should resolve")
        self.assertFalse(brief2.open_threads, "open thread should be closed")

    def test_pii_redacted_in_store_file(self):
        mem = CallRecallMemory(path=self.path)
        mem.record_call(CALLER, CALL_1)
        with open(self.path, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("sam.rivera@example.com", raw)
        self.assertNotIn("555-123-4567", raw)
        self.assertIn("[EMAIL]", raw)
        self.assertIn("[PHONE]", raw)

    def test_livekit_instructions(self):
        mem = CallRecallMemory(path=self.path)
        mem.record_call(CALLER, CALL_1)
        lk = CallRecallLiveKit(mem)
        instr = lk.session_instructions(CALLER, base_instructions="You are a helpful agent.")
        self.assertIn("Caller memory", instr)
        self.assertIn("You are a helpful agent.", instr)
        # new caller: instructions untouched
        self.assertEqual(
            lk.session_instructions("+1999", base_instructions="Base."), "Base.")

    def test_backfill_then_recall(self):
        mem = CallRecallMemory(path=self.path)
        mem.backfill(CALLER, [CALL_1])
        ctx = mem.context_block(CALLER)
        self.assertIn("replacement", ctx)


if __name__ == "__main__":
    unittest.main()
