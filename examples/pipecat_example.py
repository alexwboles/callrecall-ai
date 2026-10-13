"""Pipecat example: wire callrecall-ai memory into a voice pipeline.

Place the memory processor between your user context aggregator and the
LLM service — the same slot Mem0MemoryService / HindsightMemoryService use.
The caller ID must be stable per caller (phone number, account id), not
per call.

Requires: pip install "callrecall-ai[pipecat]"
"""
from callrecall import CallRecallMemory
from callrecall.adapters import CallRecallPipecat

# One memory instance per agent. Save + recall are separate toggles —
# e.g. an intake agent that only saves, and a support agent that recalls.
memory = CallRecallMemory(
    path="~/.callrecall/memory.json",
    save_enabled=True,    # like Retell's per-agent "save memory"
    recall_enabled=True,  # like Retell's "use contact memory"
    redact_pii=True,      # on by default
)

recall = CallRecallPipecat(
    memory,
    contact_id_fn=lambda frame: getattr(frame, "caller_phone", ""),
)


def build_pipeline(transport, stt, user_aggregator, llm,
                   assistant_aggregator, tts):
    from pipecat.pipeline.pipeline import Pipeline
    return Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        recall.processor(),   # <-- memory goes here
        llm,
        assistant_aggregator,
        tts,
        transport.output(),
    ])


# At call start, the brief is injected automatically by the processor.
# When the call ends, hand the transcript over:
#
#   recall.on_call_end(
#       caller_phone,
#       transcript,                       # list of {"role","text"} or "A:/C:" text
#       display_name="Sam Rivera",        # optional
#       call_id="call_abc123",            # optional
#   )
#
# Retell-style skippable flow steps:
#
#   steps = ["Ask for the order number", "Ask how they'd like updates"]
#   for step in recall.skippable(caller_phone, steps):
#       flow.mark_skipped(step)
