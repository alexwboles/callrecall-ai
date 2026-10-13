"""Structured caller brief: the unit of memory in callrecall-ai.

A brief is what a good human agent keeps in their head about a caller:
what they prefer, what is true about them, what is still open, and what
got resolved. Resolved items auto-expire after N days so the brief stays
fresh — a simplified take on Zep/Graphiti's temporal invalidation, without
a graph database.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BriefItem:
    """One remembered fact about a contact."""
    text: str
    source: str = ""          # call_id or "backfill" / "manual"
    created_at: str = field(default_factory=utcnow_iso)
    valid_until: str = ""     # ISO date; empty = does not expire
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BriefItem":
        return cls(
            text=str(d.get("text", "")),
            source=str(d.get("source", "")),
            created_at=str(d.get("created_at", "")),
            valid_until=str(d.get("valid_until", "")),
            tags=list(d.get("tags", []) or []),
        )

    def expired(self, now: datetime | None = None) -> bool:
        if not self.valid_until:
            return False
        try:
            until = datetime.fromisoformat(self.valid_until)
            now = now or datetime.now(timezone.utc)
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            return now >= until
        except ValueError:
            return False


@dataclass
class CallerBrief:
    """Everything remembered about one contact (phone number, account id...)."""
    contact_id: str
    display_name: str = ""
    preferences: list = field(default_factory=list)   # list[BriefItem]
    facts: list = field(default_factory=list)         # list[BriefItem]
    open_threads: list = field(default_factory=list)  # list[BriefItem]
    resolved: list = field(default_factory=list)      # list[BriefItem], auto-expire
    call_count: int = 0
    last_call_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "display_name": self.display_name,
            "preferences": [i.to_dict() for i in self.preferences],
            "facts": [i.to_dict() for i in self.facts],
            "open_threads": [i.to_dict() for i in self.open_threads],
            "resolved": [i.to_dict() for i in self.resolved],
            "call_count": self.call_count,
            "last_call_at": self.last_call_at,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CallerBrief":
        b = cls(contact_id=str(d.get("contact_id", "")), display_name=str(d.get("display_name", "")))
        for key in ("preferences", "facts", "open_threads", "resolved"):
            setattr(b, key, [BriefItem.from_dict(i) for i in d.get(key, []) or []])
        b.call_count = int(d.get("call_count", 0) or 0)
        b.last_call_at = str(d.get("last_call_at", ""))
        b.summary = str(d.get("summary", ""))
        return b

    def prune_expired(self) -> int:
        """Drop expired resolved items. Returns the number removed."""
        before = len(self.resolved)
        self.resolved = [i for i in self.resolved if not i.expired()]
        return before - len(self.resolved)

    def all_items(self) -> list:
        return self.preferences + self.facts + self.open_threads + self.resolved
