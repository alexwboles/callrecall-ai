"""CallRecallMemory: the middleware core.

Two toggles, like Retell's "Use contact memory" / per-agent save settings:
  save_enabled   — record_call() writes/updates the brief (default True)
  recall_enabled — brief()/context_block() return memory (default True)

Turn either off and that direction becomes a no-op, so one memory instance
can serve agents that only save, only recall, or both.

    mem = CallRecallMemory()                       # ~/.callrecall/memory.json
    mem.record_call("+15551234567", transcript)     # after the call
    mem.context_block("+15551234567")              # inject at session start
    mem.skippable("+15551234567", flow_steps)      # which steps to skip
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .brief import CallerBrief, BriefItem, utcnow_iso
from .store import JsonFileStore
from . import redact as redact_mod
from . import extract as extract_mod

_WORD = re.compile(r"[a-z0-9]+")

# canonicalize near-synonyms so "problem" matches "issue", "updates" matches
# "update", etc. — matching is topical, not just lexical.
_SYNONYMS = {
    "problem": "issue", "problems": "issue",
    "asking": "ask", "asked": "ask",
    "prefers": "prefer", "preferred": "prefer", "preference": "prefer",
    "updates": "update", "updated": "update", "callbacks": "callback",
    "likes": "like", "loves": "like",
}


def _tokens(s: str) -> set:
    return {_SYNONYMS.get(t, t) for t in _WORD.findall(s.lower())}


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "is", "it",
    "you", "your", "we", "do", "does", "what", "when", "how", "please", "me",
    "my", "with", "ask", "about", "get", "can", "i", "this", "that",
}


def _overlap(a: str, b: str) -> float:
    """Topical overlap: fraction of the *smaller* side's tokens that are shared."""
    ta, tb = _tokens(a) - _STOPWORDS, _tokens(b) - _STOPWORDS
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


class CallRecallMemory:
    def __init__(
        self,
        path: str | None = None,
        *,
        save_enabled: bool = True,
        recall_enabled: bool = True,
        redact_pii: bool = True,
        resolve_expiry_days: int = 30,
        extractor=None,  # optional LLM hook: fn(turns) -> dict of string lists
        store: JsonFileStore | None = None,
    ):
        from .store import DEFAULT_PATH
        self.store = store or JsonFileStore(path or DEFAULT_PATH)
        self.save_enabled = save_enabled
        self.recall_enabled = recall_enabled
        self.redact_pii = redact_pii
        self.resolve_expiry_days = resolve_expiry_days
        self.extractor = extractor

    # -- write path -------------------------------------------------------
    def record_call(
        self,
        contact_id: str,
        transcript,
        *,
        display_name: str = "",
        call_id: str = "",
        metadata: dict | None = None,
    ) -> CallerBrief | None:
        """Extract a transcript into the contact's brief. Returns the brief."""
        if not self.save_enabled:
            return self.brief(contact_id)
        if not contact_id:
            raise ValueError("contact_id is required")

        raw = self.store.get(contact_id)
        brief = CallerBrief.from_dict(raw) if raw else CallerBrief(contact_id=contact_id)
        if display_name:
            brief.display_name = display_name

        found = extract_mod.extract_with_hook(
            transcript, self.extractor, source=call_id or "call")
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(days=self.resolve_expiry_days)).isoformat(timespec="seconds")

        def scrub(items: list[BriefItem]) -> list[BriefItem]:
            for it in items:
                if self.redact_pii:
                    it.text = redact_mod.redact_text(it.text)
            return items

        brief.preferences.extend(scrub(found["preferences"]))
        brief.facts.extend(scrub(found["facts"]))
        brief.open_threads.extend(scrub(found["open_threads"]))
        for it in scrub(found["resolved"]):
            it.valid_until = expiry
            brief.resolved.append(it)
            # a resolution closes matching open threads (topical overlap)
            brief.open_threads = [
                t for t in brief.open_threads
                if _overlap(t.text, it.text) < 0.1
            ]

        # merge near-duplicates so the brief doesn't grow without bound
        for key in ("preferences", "facts", "open_threads"):
            brief.__dict__[key] = self._dedupe(brief.__dict__[key])

        brief.call_count += 1
        brief.last_call_at = utcnow_iso()
        pruned = brief.prune_expired()
        brief.summary = self._summarize(brief)
        self.store.put(contact_id, brief.to_dict())
        return brief

    @staticmethod
    def _dedupe(items: list[BriefItem]) -> list[BriefItem]:
        kept: list[BriefItem] = []
        for it in items:
            if not any(_overlap(it.text, k.text) > 0.8 for k in kept):
                kept.append(it)
        return kept[-50:]  # cap: a brief is a brief, not an archive

    @staticmethod
    def _summarize(brief: CallerBrief) -> str:
        parts = []
        if brief.preferences:
            parts.append("Prefers: " + "; ".join(i.text for i in brief.preferences[-3:]))
        if brief.open_threads:
            parts.append("Open: " + "; ".join(i.text for i in brief.open_threads[-3:]))
        if brief.resolved:
            parts.append("Resolved: " + "; ".join(i.text for i in brief.resolved[-2:]))
        return " | ".join(parts)[:600]

    def backfill(self, contact_id: str, transcripts: list, **kwargs) -> CallerBrief | None:
        """Build a brief from a pile of old transcripts. Same pipeline as record_call."""
        brief = None
        for i, t in enumerate(transcripts):
            brief = self.record_call(contact_id, t, call_id=f"backfill-{i}", **kwargs)
        return brief

    # -- read path ----------------------------------------------------------
    def brief(self, contact_id: str) -> CallerBrief | None:
        if not self.recall_enabled:
            return None
        raw = self.store.get(contact_id)
        if not raw:
            return None
        brief = CallerBrief.from_dict(raw)
        brief.prune_expired()
        return brief

    def context_block(self, contact_id: str) -> str:
        """Render the brief as system-prompt text. Empty string = new caller."""
        brief = self.brief(contact_id)
        if not brief:
            return ""
        lines = [f"[Caller memory — {brief.call_count} prior call(s)]"]
        if brief.display_name:
            lines.append(f"Name: {brief.display_name}")
        if brief.summary:
            lines.append(f"Summary: {brief.summary}")
        for label, items in (("Preferences", brief.preferences),
                             ("Known facts", brief.facts),
                             ("Open threads", brief.open_threads)):
            if items:
                lines.append(f"{label}:")
                lines.extend(f"  - {i.text}" for i in items[-8:])
        if brief.resolved:
            lines.append("Recently resolved:")
            lines.extend(f"  - {i.text}" for i in brief.resolved[-5:])
        lines.append("Do not ask the caller to repeat anything covered above.")
        return "\n".join(lines)

    def skippable(self, contact_id: str, steps: list[str], threshold: float = 0.3) -> list[str]:
        """Retell-style "use memory to skip this node": which flow steps does
        memory already cover? Steps are plain descriptions, e.g.
        "Ask for the caller's account number"."""
        brief = self.brief(contact_id)
        if not brief:
            return []
        known = [i.text for i in brief.all_items()]
        return [s for s in steps if any(_overlap(s, k) >= threshold for k in known)]

    def search(self, query: str, limit: int = 5) -> list[tuple[str, str]]:
        """Keyword search across all briefs. Returns [(contact_id, snippet)]."""
        if not self.recall_enabled:
            return []
        hits = []
        for cid in self.store.contact_ids():
            brief = self.brief(cid)
            if not brief:
                continue
            for item in brief.all_items():
                score = _overlap(query, item.text)
                if score > 0:
                    hits.append((score, cid, item.text))
        hits.sort(reverse=True)
        return [(cid, text) for _, cid, text in hits[:limit]]

    def forget(self, contact_id: str) -> bool:
        """Delete a contact's brief entirely."""
        return self.store.delete(contact_id)
