from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from booking_assistant import mock_calendar as cal
from booking_assistant.models import ScheduledAppointment

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class PlumberConfig:
    id: str
    name: str
    skills: list[str]
    slot_minutes: int
    availability: list[dict[str, Any]]


def load_plumbers(path: Path | None = None) -> list[PlumberConfig]:
    p = path or (DATA_DIR / "plumbers.json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    out: list[PlumberConfig] = []
    for row in raw:
        out.append(
            PlumberConfig(
                id=row["id"],
                name=row["name"],
                skills=list(row.get("skills", [])),
                slot_minutes=int(row.get("slot_minutes", 120)),
                availability=list(row.get("availability", [])),
            )
        )
    return out


def plumber_matches_issue(issue: str, plumber: PlumberConfig) -> bool:
    sk = plumber.skills
    if not sk:
        return True
    if issue in sk:
        return True
    if issue == "general" and "general" in sk:
        return True
    return False


def overlaps(a_start: datetime, a_end: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    for b0, b1 in busy:
        if a_start < b1 and a_end > b0:
            return True
    return False


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _combine(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def _default_tz() -> ZoneInfo:
    try:
        return ZoneInfo("Australia/Sydney")
    except Exception:
        return ZoneInfo("UTC")


def find_appointment_slot(
    slots: dict[str, Any],
    *,
    tz: ZoneInfo | None = None,
    plumbers_path: Path | None = None,
    horizon_days: int = 21,
    step_minutes: int = 30,
) -> ScheduledAppointment | None:
    """Pick first plumber + slot matching skills and plumber availability."""
    tz = tz or _default_tz()
    issue = slots.get("issue_category") or "general"
    location = slots.get("location") or ""
    urgency = slots.get("urgency") or "medium"
    name = slots.get("customer_name") or "Customer"

    plumbers = [
        pm for pm in load_plumbers(plumbers_path) if plumber_matches_issue(str(issue), pm)
    ]
    if not plumbers:
        return None

    now = datetime.now(tz).replace(second=0, microsecond=0)

    for day_offset in range(0, horizon_days):
        day = (now + timedelta(days=day_offset)).date()
        wd = day.weekday()
        for plumber in plumbers:
            busy = cal.busy_intervals_for_plumber(plumber.id)
            duration = timedelta(minutes=plumber.slot_minutes)
            for win in plumber.availability:
                if int(win.get("weekday", -1)) != wd:
                    continue
                w_start = _parse_hhmm(str(win["start"]))
                w_end = _parse_hhmm(str(win["end"]))
                win_start = _combine(day, w_start, tz)
                win_end = _combine(day, w_end, tz)
                if win_end <= win_start:
                    continue
                cursor = win_start
                if day_offset == 0 and cursor < now:
                    cursor = now
                while cursor + duration <= win_end:
                    end = cursor + duration
                    if not overlaps(cursor, end, busy):
                        record = {
                            "plumber_id": plumber.id,
                            "plumber_name": plumber.name,
                            "start": cursor.isoformat(),
                            "end": end.isoformat(),
                            "issue_category": str(issue),
                            "urgency": str(urgency),
                            "location": location,
                            "customer_name": name,
                            "customer_phone": slots.get("customer_phone"),
                            "customer_email": slots.get("customer_email"),
                            "preferred_time_notes": slots.get("preferred_time_notes"),
                        }
                        cal.append_event(record)
                        return ScheduledAppointment(
                            plumber_id=plumber.id,
                            plumber_name=plumber.name,
                            start=cursor,
                            end=end,
                            issue_summary=f"{issue} ({urgency})",
                            location=str(location),
                            urgency=str(urgency),
                            customer_name=str(name),
                            customer_phone=slots.get("customer_phone"),
                            customer_email=slots.get("customer_email"),
                            calendar_record=record,
                        )
                    cursor += timedelta(minutes=step_minutes)
    return None
