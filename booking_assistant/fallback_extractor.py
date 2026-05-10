from __future__ import annotations

import re
from typing import Iterable

from booking_assistant.schemas import ExtractionTurn, missing_booking_fields

_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3}\)?[\s\-]?)?\d{3}[\s\-]?\d{3}[\s\-]?\d{3}"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_ISSUE_TERMS: list[tuple[Iterable[str], str]] = [
    (("blocked", "clog", "drain", "slow drain"), "blocked_drain"),
    (("toilet",), "toilet"),
    (("sewer", "septic"), "sewer"),
    (("hot water", "hotwater", "heater"), "hot_water"),
    (("gas",), "gas"),
    (("burst", "broken pipe"), "burst_pipe"),
    (("tap", "faucet", "mixer"), "tap"),
    (("leak", "leaking", "drip"), "leak"),
]

_URGENCY_TERMS = [
    (("urgent", "asap", "emergency", "flooding", "now"), "emergency"),
    (("today", "tonight"), "high"),
    (("soon",), "medium"),
]


def _infer_issue(text_lc: str) -> str | None:
    for terms, cat in _ISSUE_TERMS:
        if any(t in text_lc for t in terms):
            return cat
    if "pipe" in text_lc or "plumb" in text_lc:
        return "general"
    return None


def _infer_urgency(text_lc: str) -> str | None:
    for words, lvl in _URGENCY_TERMS:
        if any(w in text_lc for w in words):
            return lvl
    return None


def _pick_location(text: str) -> str | None:
    m = re.search(
        r"\b(\d{1,5}\s+[\w\s]+(?:street|st|road|rd|avenue|ave|drive|dr|lane|ln|court|ct)\b[^\n]*)",
        text,
        flags=re.I,
    )
    if m:
        loc = " ".join(m.group(1).split())
        return loc.split(",")[0].strip()
    m2 = re.search(r"\bat\s+([A-Za-z][\w\s\-]+?)(?:\.|,|$)", text)
    if m2:
        return m2.group(1).strip()
    return None


def _pick_name(text: str) -> str | None:
    m = re.search(
        r"(?i)(?:i(?:['’]m| am)\s+|name(?:'s|['’]s| is)\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        text,
    )
    if m:
        return m.group(1).strip()
    return None


def extraction_turn_fallback(user_message: str, prior_slots: dict) -> ExtractionTurn:
    """Heuristic demo extractor when no API key or USE_LLM=0."""
    text = user_message.strip()
    text_lc = text.lower()

    base = dict(prior_slots)

    issue = _infer_issue(text_lc)
    urgency = _infer_urgency(text_lc)
    location = _pick_location(text)
    phone_m = _PHONE_RE.search(text)
    email_m = _EMAIL_RE.search(text)
    name = _pick_name(text)

    preferred = None
    for kw in ("tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "morning", "afternoon", "evening", "next week"):
        if kw in text_lc:
            preferred = text.strip()
            break

    if issue:
        base["issue_category"] = issue
    if urgency:
        base["urgency"] = urgency
    if location:
        base["location"] = location
    if name:
        base["customer_name"] = name
    if phone_m:
        base["customer_phone"] = phone_m.group(0)
    if email_m:
        base["customer_email"] = email_m.group(0)
    if preferred:
        base["preferred_time_notes"] = preferred

    merged_issue = base.get("issue_category")
    merged_urgency = base.get("urgency")
    merged_loc = base.get("location")
    merged_name = base.get("customer_name")
    merged_phone = base.get("customer_phone")
    merged_email = base.get("customer_email")
    merged_pref = base.get("preferred_time_notes")

    draft = {
        "issue_category": merged_issue,
        "urgency": merged_urgency,
        "location": merged_loc,
        "customer_name": merged_name,
        "customer_phone": merged_phone,
        "customer_email": merged_email,
        "preferred_time_notes": merged_pref,
    }
    miss = missing_booking_fields(draft)
    if not miss:
        reply = (
            "Thanks — I have what we need. I’ll check the next available licensed plumber "
            "and confirm the appointment."
        )
    else:
        if "customer_phone_or_email" in miss:
            miss = [m for m in miss if m != "customer_phone_or_email"]
            miss.append("a phone number or email")
        human = ", ".join(m.replace("_", " ") for m in miss)
        reply = f"Thanks for the details. Could you also share: {human}?"

    return ExtractionTurn(
        intent="book_plumbing",
        issue_category=merged_issue,
        urgency=merged_urgency,
        location=merged_loc,
        preferred_time_notes=merged_pref,
        customer_name=merged_name,
        customer_phone=merged_phone,
        customer_email=merged_email,
        assistant_reply=reply,
        confidence_notes="Heuristic demo mode — local LLM off or unreachable.",
    )
