"""Smoke test: package imports, one record/recall roundtrip, store file exists."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callrecall import CallRecallMemory, CallerBrief, BriefItem, JsonFileStore  # noqa: E402
from callrecall.adapters import CallRecallPipecat, CallRecallLiveKit, BaseAdapter  # noqa: E402


def main() -> int:
    tmp = tempfile.mkdtemp()
    mem = CallRecallMemory(path=os.path.join(tmp, "memory.json"))
    mem.record_call("+15550001111", [
        {"role": "assistant", "text": "Hi, how can I help?"},
        {"role": "user", "text": "Hi, I prefer text updates over calls."},
    ], display_name="Smoke Test")
    block = mem.context_block("+15550001111")
    assert "prefers text updates over calls" in block, block
    assert os.path.exists(os.path.join(tmp, "memory.json"))
    # adapters construct
    CallRecallPipecat(mem)
    CallRecallLiveKit(mem)
    assert issubclass(CallRecallPipecat, BaseAdapter)
    print("smoke: OK — import, record, recall, adapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
