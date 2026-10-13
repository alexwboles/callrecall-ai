"""Transcript -> structured memory, without an LLM by default.

Mem0 and Zep run an LLM extraction pass over every conversation. That is
powerful but it costs a model call per turn and needs a provider. callrecall
ships a deterministic rule-based extractor that covers the patterns that
actually show up in service calls (preferences, identity facts, callbacks,
resolutions) and lets you plug any LLM in as an *additional* extractor via
`extractor=` — e.g. a local Ollama model — for the long tail.

Transcript input: a list of {"role": "user"|"assistant", "text": ...}
(or "agent"/"caller" roles), or a plain string with "Agent:"/"Caller:" lines.
"""
from __future__ import annotations

import re
from typing import Callable

from .brief import BriefItem

# role normalisation
USER_ROLES = {"user", "caller", "customer", "human"}
AGENT_ROLES = {"assistant", "agent", "system", "bot"}

PREFERENCE_PATTERNS = [
    (re.compile(r"\bi\s+prefer\s+([^.,;!?]+)", re.I), "prefers {}"),
    (re.compile(r"\bi\s+like\s+([^.,;!?]+)", re.I), "likes {}"),
    (re.compile(r"\bi\s+love\s+([^.,;!?]+)", re.I), "loves {}"),
    (re.compile(r"\bi\s+don't\s+like\s+([^.,;!?]+)", re.I), "dislikes {}"),
    (re.compile(r"\bi\s+hate\s+([^.,;!?]+)", re.I), "dislikes {}"),
    (re.compile(r"\bplease\s+(?:don't|do\s+not)\s+([^.,;!?]+)", re.I), "asked not to: {}"),
    (re.compile(r"\bmy\s+favorite\s+(\w[\w\s]*?)\s+is\s+([^.,;!?]+)", re.I), "favorite {}: {}"),
    (re.compile(r"\bi['’]m\s+(?:a|an)\s+([^.,;!?]+)", re.I), "is {}"),
    (re.compile(r"\bi\s+am\s+([^.,;!?]+)", re.I), "is {}"),
]

FACT_PATTERNS = [
    # tight captures: one value per fact, no clause-grabbing
    (re.compile(r"\bmy\s+(?:phone\s+number|number)\s+is\s+([+\d][\d\s().-]{6,}\d)", re.I), "phone number: {}"),
    (re.compile(r"\bmy\s+email\s+is\s+(\S+@\S+)", re.I), "email: {}"),
    (re.compile(r"\bmy\s+address\s+is\s+([^;!?]+?)(?:\s+and\s+|\s+but\s+|$)", re.I), "address: {}"),
    (re.compile(r"\bmy\s+account\s+(?:number\s+)?is\s+([A-Za-z0-9][\w.-]*)", re.I), "account: {}"),
    (re.compile(r"\bmy\s+name\s+is\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2})", re.I), "name: {}"),
    (re.compile(r"\border\s+(?:number\s+|#\s*)?([A-Za-z0-9-]{4,})", re.I), "order: {}"),
]

ISSUE_PATTERNS = [
    (re.compile(
        r"\bmy\s+([\w][\w\s]*?)\s+"
        r"(never arrived|hasn'?t arrived|is broken|isn'?t working|doesn'?t work|"
        r"was lost|is missing|died|stopped working)\b",
        re.I), "issue: {} {}"),
]

RESOLVED_PATTERNS = [
    re.compile(r"\b(resolved|fixed|taken care of|all set|problem solved|issue (?:is\s+)?closed)\b", re.I),
    re.compile(r"\bthanks?,?\s+(?:that|it)\s+(worked|helped|did the trick)\b", re.I),
    re.compile(r"\bthat\s+(worked|did the trick|solved it)\b", re.I),
    re.compile(r"\bwe(?:'re| are)\s+all\s+(good|set)\b", re.I),
]

# agent says X -> open thread (callback promised, check pending).
# The "I'll" is optional: real speech is often "I'll check and call you back".
OPEN_THREAD_PATTERNS = [
    (re.compile(
        r"\b(?:i(?:'ll| will)\s+)?"
        r"(?:call you back|follow up|get back to you)"
        r"([^.,;!?]*)",
        re.I), "promised follow-up{}"),
    (re.compile(r"\blet me\s+(?:check|look)(?:\s+on|\s+into|\s+up)?\b([^.,;!?]*)", re.I),
     "agent checking{}"),
    (re.compile(r"\bwe(?:'ll| will)\s+(?:send|ship|email|mail)\s+([^.,;!?]+)", re.I), "to send: {}"),
    (re.compile(r"\byour\s+(?:replacement|refund|order|ticket|request)\s+is\s+(?:being\s+)?(processed|on (?:its|the) way|shipped)", re.I),
     "in progress: {}"),
]

# agent asks a question the caller never answers -> open thread
QUESTION = re.compile(r"\?\s*$")


def normalize_transcript(transcript) -> list[dict]:
    """Accept list-of-dicts or 'Agent:/Caller:' plain text; return [{'role','text'}]."""
    if isinstance(transcript, str):
        turns = []
        for line in transcript.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(agent|assistant|bot)\s*:\s*(.*)$", line, re.I)
            if m:
                turns.append({"role": "assistant", "text": m.group(2)})
                continue
            m = re.match(r"^(caller|customer|user|human)\s*:\s*(.*)$", line, re.I)
            if m:
                turns.append({"role": "user", "text": m.group(2)})
                continue
            # continuation of the previous turn
            if turns:
                turns[-1]["text"] += " " + line
        return turns
    out = []
    for t in transcript or []:
        role = str(t.get("role", "")).strip().lower()
        role = "user" if role in USER_ROLES else "assistant" if role in AGENT_ROLES else role
        out.append({"role": role, "text": str(t.get("text", ""))})
    return out


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", fragment).strip(" .")


def extract_rule_based(transcript, source: str = "") -> dict:
    """Deterministic extraction. Returns {preferences, facts, open_threads, resolved} lists of BriefItem."""
    turns = normalize_transcript(transcript)
    preferences, facts, open_threads, resolved = [], [], [], []
    seen = set()

    def add(bucket: list, text: str, tags: list | None = None):
        text = _clean(text)
        if not text or len(text) > 300:
            return
        key = (id(bucket), text.lower())
        if key in seen:
            return
        seen.add(key)
        bucket.append(BriefItem(text=text, source=source, tags=tags or []))

    user_texts = [t["text"] for t in turns if t["role"] == "user"]
    agent_texts = [t["text"] for t in turns if t["role"] == "assistant"]

    for ut in user_texts:
        for pat, template in PREFERENCE_PATTERNS:
            for m in pat.finditer(ut):
                groups = [g for g in m.groups() if g]
                add(preferences, template.format(*[_clean(g) for g in groups]),
                    tags=["preference"])
        for pat, template in FACT_PATTERNS:
            m = pat.search(ut)
            if m:
                add(facts, template.format(_clean(m.group(1))), tags=["fact"])
        for pat, template in ISSUE_PATTERNS:
            m = pat.search(ut)
            if m:
                add(facts, template.format(*[_clean(g) for g in m.groups()]),
                    tags=["fact", "issue"])

    for ut in user_texts:
        for pat in RESOLVED_PATTERNS:
            m = pat.search(ut)
            if m:
                add(resolved, f"resolved: {_clean(ut[:120])}", tags=["resolved"])
                break

    # Each pattern captures exactly one group: the topic tail (may be empty).
    for at in agent_texts:
        for pat, template in OPEN_THREAD_PATTERNS:
            for m in pat.finditer(at):
                topic = _clean(m.group(1) or "")
                frag = template.format(f": {topic}" if topic else "")
                add(open_threads, frag, tags=["open-thread"])

    # agent questions never answered by the caller -> open threads
    for i, t in enumerate(turns):
        if t["role"] == "assistant" and QUESTION.search(t["text"].strip()):
            answered = any(
                turns[j]["role"] == "user" and turns[j]["text"].strip()
                for j in range(i + 1, min(i + 3, len(turns)))
            )
            if not answered:
                add(open_threads, f"unanswered question: {_clean(t['text'][:140])}",
                    tags=["open-thread", "unanswered"])

    return {
        "preferences": preferences,
        "facts": facts,
        "open_threads": open_threads,
        "resolved": resolved,
    }


ExtractorFn = Callable[[list], dict]
"""Optional LLM extractor: fn(turns) -> {"preferences":[...], "facts":[...],
"open_threads":[...], "resolved":[...]} with plain strings."""


def extract_with_hook(transcript, extractor: ExtractorFn | None, source: str = "") -> dict:
    """Rule-based extraction merged with an optional LLM extractor's strings."""
    result = extract_rule_based(transcript, source=source)
    if extractor is None:
        return result
    turns = normalize_transcript(transcript)
    try:
        extra = extractor(turns) or {}
    except Exception:
        return result  # an extractor must never break the call
    for key in ("preferences", "facts", "open_threads", "resolved"):
        for text in extra.get(key, []) or []:
            text = _clean(str(text))
            if text and not any(i.text.lower() == text.lower() for i in result[key]):
                result[key].append(BriefItem(text=text, source=source or "llm",
                                             tags=["llm", key.rstrip("s")]))
    return result
