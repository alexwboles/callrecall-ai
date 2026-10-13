"""callrecall-ai: self-hosted voice-agent memory layer.

Per-contact caller briefs stored in one human-inspectable JSON file.
Free, local, no cloud, no vector DB.

Quick start:
    from callrecall import CallRecallMemory

    mem = CallRecallMemory()  # ~/.callrecall/memory.json
    mem.record_call("+15551234567", transcript, display_name="Sam")
    print(mem.context_block("+15551234567"))  # inject into your system prompt
"""
from .memory import CallRecallMemory
from .brief import CallerBrief, BriefItem
from .store import JsonFileStore
from . import redact, extract
from . import adapters

__version__ = "0.1.0"
__all__ = [
    "CallRecallMemory",
    "CallerBrief",
    "BriefItem",
    "JsonFileStore",
    "redact",
    "extract",
    "adapters",
]
