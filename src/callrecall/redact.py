"""PII redaction, ON by default.

Retell-style memory stores whatever the extractor finds; callrecall-ai
scrubs the obvious identifiers before anything is written to the brief.
Regex-based, dependency-free, deterministic.

Covered by default: email addresses, phone numbers, street addresses,
US SSNs, credit-card numbers. Person names are masked with a conservative
heuristic (two or more consecutive capitalized words) — identity fields
(contact_id, display_name) are never touched.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(
    r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}"
)
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
# crude street address: number + words + street suffix
ADDRESS = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-z]+\s+){1,4}"
    r"(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd|court|ct|"
    r"place|pl|terrace|ter|way|circle|cir|parkway|pkwy)\b\.?",
    re.IGNORECASE,
)
# zip codes usually ride along with an address
ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")

# Conservative person-name heuristic: 2+ consecutive capitalized words.
# Common false positives (days, months, places-as-words) are allowlisted out.
_NAME_STOPWORDS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "main street", "high street", "first avenue",
}
NAME_PAIR = re.compile(r"\b([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})+)\b")


def _mask_name(match: re.Match) -> str:
    phrase = match.group(1)
    if phrase.lower() in _NAME_STOPWORDS:
        return phrase
    return "[NAME]"


def redact_text(
    text: str,
    *,
    email: bool = True,
    phone: bool = True,
    address: bool = True,
    ssn: bool = True,
    card: bool = True,
    names: bool = True,
) -> str:
    """Scrub PII from free text. Each category can be toggled off."""
    if not text:
        return text
    out = text
    if email:
        out = EMAIL.sub("[EMAIL]", out)
    if phone:
        # avoid eating years / plain 4-digit fragments: require 10+ digits total
        def _phone(m: re.Match) -> str:
            digits = re.sub(r"\D", "", m.group(0))
            return "[PHONE]" if len(digits) >= 10 else m.group(0)
        out = PHONE.sub(_phone, out)
    if ssn:
        out = SSN.sub("[SSN]", out)
    if card:
        def _card(m: re.Match) -> str:
            digits = re.sub(r"\D", "", m.group(0))
            return "[CARD]" if 13 <= len(digits) <= 16 else m.group(0)
        out = CARD.sub(_card, out)
    if address:
        out = ADDRESS.sub("[ADDRESS]", out)
        # a zip glued to a redacted address line is part of the address
        out = re.sub(r"\[ADDRESS\][,\s]*" + ZIP.pattern, "[ADDRESS]", out)
    if names:
        out = NAME_PAIR.sub(_mask_name, out)
    return out


def redact_brief_texts(texts: list[str], **kwargs) -> list[str]:
    return [redact_text(t, **kwargs) for t in texts]
