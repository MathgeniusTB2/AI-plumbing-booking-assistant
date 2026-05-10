from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CALENDAR_PATH = DATA_DIR / "mock_calendar.jsonl"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def append_event(record: dict[str, Any]) -> None:
    ensure_data_dir()
    line = json.dumps(record, default=str) + "\n"
    CALENDAR_PATH.open("a", encoding="utf-8").write(line)


def iter_events() -> Iterator[dict[str, Any]]:
    if not CALENDAR_PATH.is_file():
        return
    with CALENDAR_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def busy_intervals_for_plumber(plumber_id: str) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for ev in iter_events():
        if ev.get("plumber_id") != plumber_id:
            continue
        try:
            s = datetime.fromisoformat(ev["start"])
            e = datetime.fromisoformat(ev["end"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append((s, e))
    return out


def _parse_event_start(ev: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ev["start"]))
    except (KeyError, TypeError, ValueError):
        return None


def list_events_chronological(
    *,
    plumber_id: str | None = None,
    upcoming_only: bool = False,
) -> list[dict[str, Any]]:
    """All calendar rows, sorted by start time (for tradie dashboards)."""
    rows: list[dict[str, Any]] = []
    for ev in iter_events():
        if plumber_id and ev.get("plumber_id") != plumber_id:
            continue
        start = _parse_event_start(ev)
        if upcoming_only and start is not None:
            ref = datetime.now(tz=start.tzinfo) if start.tzinfo else datetime.now()
            if start < ref:
                continue
        rows.append(ev)

    def sort_key(ev: dict[str, Any]) -> datetime:
        s = _parse_event_start(ev)
        if s is not None:
            return s
        return datetime.min

    rows.sort(key=sort_key)
    return rows

