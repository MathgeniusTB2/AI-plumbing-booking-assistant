from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ScheduledAppointment:
    """Result of mock scheduling + calendar write."""

    plumber_id: str
    plumber_name: str
    start: datetime
    end: datetime
    issue_summary: str
    location: str
    urgency: str
    customer_name: str
    customer_phone: str | None
    customer_email: str | None
    calendar_record: dict[str, Any]

    @classmethod
    def try_from_calendar_record(cls, ev: dict[str, Any]) -> ScheduledAppointment | None:
        """Rehydrate from a mock_calendar JSONL row; return None if invalid."""
        try:
            start = datetime.fromisoformat(str(ev["start"]))
            end = datetime.fromisoformat(str(ev["end"]))
        except (KeyError, TypeError, ValueError):
            return None
        cat = str(ev.get("issue_category") or "general")
        urg = str(ev.get("urgency") or "medium")
        summary = ev.get("issue_summary")
        if isinstance(summary, str) and summary.strip():
            issue_summary = summary.strip()
        else:
            issue_summary = f"{cat} ({urg})"
        phone = ev.get("customer_phone")
        email = ev.get("customer_email")
        return cls(
            plumber_id=str(ev.get("plumber_id") or ""),
            plumber_name=str(ev.get("plumber_name") or "Plumber"),
            start=start,
            end=end,
            issue_summary=issue_summary,
            location=str(ev.get("location") or ""),
            urgency=urg,
            customer_name=str(ev.get("customer_name") or "Customer"),
            customer_phone=str(phone).strip() if phone else None,
            customer_email=str(email).strip() if email else None,
            calendar_record=dict(ev),
        )
