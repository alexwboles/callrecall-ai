# callrecall-ai

> **This project has been merged into voice-memory — active development
> continues at <https://github.com/alexwboles/voice-memory>.**
> This repo is archived and read-only. See
> [MIGRATION.md](https://github.com/alexwboles/voice-memory/blob/main/MIGRATION.md)
> for the upgrade guide — your existing store auto-upgrades on load, and
> `CallRecallMemory` still imports as an alias for `VoiceMemory`.

**Self-hosted voice-agent memory: per-contact caller briefs in one JSON file.**

The free, local, open-source answer to Retell's paid contact-memory feature. After every call, callrecall-ai writes a structured brief for the caller — preferences, known facts, open threads, resolved items (which auto-expire) — and injects it when they call back, so your agent never asks twice. No cloud, no vector DB, no per-call fees. PII redaction is on by default.

```
pip install callrecall-ai
```

## Why not Mem0 / Zep?

| | callrecall-ai | Mem0 | Zep/Graphiti | Retell Memory |
|---|---|---|---|---|
| Price | free, self-hosted | free OSS / $19+ hosted | free OSS / hosted | paid, closed |
| Storage | **one JSON file, human-readable** | vector DB (opaque) | graph DB | closed |
| Voice-call shaped | **yes: briefs, skippable flow steps** | generic | generic | yes |
| PII redaction default-on | **yes** | no | no | no |
| LLM required | no (rule-based + optional hook) | yes | yes | yes |

## 30-second tour

```python
from callrecall import CallRecallMemory

mem = CallRecallMemory()  # ~/.callrecall/memory.json

# after the call ends:
mem.record_call("+15551234567", transcript, display_name="Sam")

# when they call back — inject into your system prompt:
prompt = mem.context_block("+15551234567")
# [Caller memory — 1 prior call(s)]
# Name: Sam
# Summary: Prefers: prefers text updates | Open: promised follow-up: about the replacement
# ...

# Retell-style "skip this node": which flow steps does memory cover?
mem.skippable("+15551234567", ["Ask for the order number", "Ask their name"])
# -> ["Ask for the order number"]
```

## Pipecat

```python
from callrecall.adapters import CallRecallPipecat

recall = CallRecallPipecat(mem, contact_id_fn=lambda frame: frame.caller_phone)

pipeline = Pipeline([
    transport.input(), stt, user_aggregator,
    recall.processor(),   # <-- memory goes here
    llm, assistant_aggregator, tts, transport.output(),
])
recall.on_call_end(caller_phone, transcript)  # when the call ends
```

Full example: `examples/pipecat_example.py`. LiveKit adapter: `callrecall.adapters.CallRecallLiveKit` (same three hooks, no hard dependency).

## The brief

```json
{
  "contact_id": "+15551234567",
  "display_name": "Sam",
  "preferences": [{"text": "prefers text updates", "source": "call_91"}],
  "facts": [{"text": "issue: package never arrived"}],
  "open_threads": [{"text": "promised follow-up: about the replacement"}],
  "resolved": [{"text": "resolved: the replacement arrived", "valid_until": "2026-11-11"}],
  "call_count": 2,
  "summary": "Prefers: prefers text updates | Resolved: ..."
}
```

Resolved items auto-expire after `resolve_expiry_days` (default 30) — temporal invalidation without a graph DB. Saving and recalling are separate toggles (`save_enabled`, `recall_enabled`), so one memory can serve agents that only save, only recall, or both.

## Bring your own LLM (optional)

Rule-based extraction covers the common patterns deterministically. For the long tail, pass any callable:

```python
def my_extractor(turns):  # e.g. local Ollama
    ...  # return {"preferences": [...], "facts": [...],
         #         "open_threads": [...], "resolved": [...]}
mem = CallRecallMemory(extractor=my_extractor)
```

An extractor can never break a call — exceptions are caught and the rule-based result stands.

## API

| Method | What it does |
|---|---|
| `record_call(contact_id, transcript, ...)` | extract + save a call's brief |
| `brief(contact_id)` | the structured brief (or `None`) |
| `context_block(contact_id)` | brief rendered for prompt injection |
| `skippable(contact_id, steps)` | flow steps memory already covers |
| `backfill(contact_id, transcripts)` | build a brief from old transcripts |
| `search(query)` | keyword search across all briefs |
| `forget(contact_id)` | delete a brief |

## Tests

```bash
python3 tests/smoke.py
python3 -m unittest discover -s tests -p "test_*.py"
```

## License

MIT. Competitor notes: Retell Memory's per-contact briefs + per-agent save/use toggles and "skip this node" shaped the API; Mem0's `add`/`search`/`get_all`/`update`/`delete` shaped the verbs; Zep/Graphiti's temporal validity windows inspired resolved-item expiry; the Pipecat `FrameProcessor`-between-aggregator-and-LLM placement follows Mem0MemoryService/Hindsight.
