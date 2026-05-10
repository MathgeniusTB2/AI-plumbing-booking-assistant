"""Tradie-facing job board (reads same mock_calendar.jsonl as the customer app)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

import streamlit as st


def _event_stable_id(ev: dict) -> str:
    blob = json.dumps(ev, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]

from booking_assistant.mock_calendar import CALENDAR_PATH
from booking_assistant.mock_calendar import list_events_chronological
from booking_assistant.mock_notify import plumber_notification_text
from booking_assistant.models import ScheduledAppointment
from booking_assistant.scheduler import load_plumbers

st.set_page_config(page_title="Tradie dispatch", page_icon="🔧", layout="wide", initial_sidebar_state="expanded")

st.title("Tradie dispatch board")
st.caption(
    "Mock **plumber-facing** view: jobs written when customers confirm bookings. "
    f"Data file: `{CALENDAR_PATH.name}`"
)

st.sidebar.markdown("### Filters")

plumbers = load_plumbers()
filter_labels = ["All plumbers"] + [p.name for p in plumbers]
choice = st.sidebar.selectbox("Show jobs for", filter_labels, index=0)
plumber_id: str | None = None
if choice != "All plumbers":
    plumber_id = next(p.id for p in plumbers if p.name == choice)

upcoming_only = st.sidebar.checkbox("Upcoming only (hide past jobs)", value=True)
raw_json = st.sidebar.checkbox("Show raw calendar row (debug)", value=False)
search_q = st.sidebar.text_input("Search (name / address / issue)", value="", placeholder="Filter table…")

sort_order = st.sidebar.selectbox(
    "Sort by start time",
    options=["Soonest first", "Latest first"],
    index=0,
)

if st.sidebar.button("Refresh list"):
    st.rerun()

if st.sidebar.button("Open customer booking chat"):
    st.switch_page("app.py")

events = list_events_chronological(plumber_id=plumber_id, upcoming_only=upcoming_only)
q_low = search_q.strip().lower()
if q_low:
    filtered: list[dict] = []
    for ev in events:
        blob = json.dumps(ev, default=str).lower()
        if q_low in blob:
            filtered.append(ev)
    events = filtered


def _sort_key(ev: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ev["start"]))
    except (KeyError, TypeError, ValueError):
        return None


reverse = sort_order == "Latest first"
events = sorted(events, key=lambda e: (_sort_key(e) or datetime.min), reverse=reverse)

st.sidebar.divider()
st.sidebar.metric("Jobs shown", len(events))

rows: list[dict[str, object]] = []
broken: list[dict] = []
for ev in events:
    appt = ScheduledAppointment.try_from_calendar_record(ev)
    if appt is None:
        broken.append(ev)
        continue
    rows.append(
        {
            "Start": appt.start.strftime("%a %d %b %Y %H:%M"),
            "End": appt.end.strftime("%H:%M"),
            "Customer": appt.customer_name,
            "Issue": appt.issue_summary,
            "Plumber": appt.plumber_name,
            "Location": appt.location,
            "Contact": appt.customer_phone or appt.customer_email or "",
        }
    )

if not events:
    st.markdown("**No jobs yet** for these filters.")
    st.info(
        "Complete a booking on the **Customer** page "
        '(sidebar: “Open customer booking chat”) — or turn off “Upcoming only”.'
    )
    st.stop()

st.divider()
st.markdown("### Upcoming jobs (summary)")

if rows:
    st.caption(f"{len(events)} booking(s) after filters — scroll the table or open a row below.")

    first_appt: ScheduledAppointment | None = None
    for ev in events:
        ap = ScheduledAppointment.try_from_calendar_record(ev)
        if ap is not None:
            first_appt = ap
            break

    m1, m2 = st.columns(2)
    with m1:
        st.metric("Jobs on this view", len(rows))
    with m2:
        if first_appt is not None:
            st.metric(
                "Next job (by sort)",
                f"{first_appt.start:%a %d %b}, {first_appt.start:%H:%M}",
                delta=first_appt.customer_name,
            )

    col_cfg = {
        "Start": st.column_config.TextColumn("Start", width="medium"),
        "End": st.column_config.TextColumn("Ends", width="small"),
        "Customer": st.column_config.TextColumn("Customer", width="small"),
        "Issue": st.column_config.TextColumn("Issue", width="large"),
        "Plumber": st.column_config.TextColumn("Plumber", width="small"),
        "Location": st.column_config.TextColumn("Location", width="medium"),
        "Contact": st.column_config.TextColumn("Contact", width="medium"),
    }
    st.dataframe(rows, hide_index=True, use_container_width=True, column_config=col_cfg)
elif broken and len(broken) == len(events):
    st.caption(f"{len(events)} calendar row(s) matched filters but could not be read as jobs.")
    st.warning("All matching rows failed to parse; see **Invalid calendar rows** below.")

if broken:
    with st.expander(f"Invalid calendar rows ({len(broken)})", expanded=False):
        for ev in broken:
            st.json(ev)

st.divider()
st.markdown("### Job detail")

first_valid_idx = next(
    (j for j, e in enumerate(events) if ScheduledAppointment.try_from_calendar_record(e) is not None),
    None,
)

for i, ev in enumerate(events):
    appt = ScheduledAppointment.try_from_calendar_record(ev)
    if appt is None:
        continue

    label = (
        f"Job {i + 1} — {appt.start:%a %d %b %H:%M}–{appt.end:%H:%M} · {appt.customer_name} · {appt.issue_summary}"
    )
    dispatch_plain = plumber_notification_text(appt)
    with st.expander(label, expanded=(first_valid_idx is not None and i == first_valid_idx)):
        c1, c2 = st.columns((1, 1))
        with c1:
            st.markdown("**Where**")
            st.write(appt.location or "—")
            st.markdown("**Contact**")
            st.write(appt.customer_phone or appt.customer_email or "—")
            if appt.customer_phone and appt.customer_email:
                st.caption(appt.customer_email)
            st.markdown("**Assigned**")
            st.write(appt.plumber_name)
        with c2:
            st.markdown("**Dispatch text** (mock SMS / app push)")
            ev_id = _event_stable_id(ev)
            show_plain = st.checkbox(
                "Plain text box",
                key=f"plain_row{i}_{ev_id}",
            )
            if show_plain:
                st.text(dispatch_plain)
            else:
                st.code(dispatch_plain, language=None)
            notes = appt.calendar_record.get("preferred_time_notes")
            if notes:
                st.markdown("**Customer timing note**")
                st.write(notes)
        if raw_json:
            st.json(ev)

st.divider()
st.download_button(
    label="Download filtered jobs as JSON",
    data=json.dumps(events, indent=2, default=str),
    file_name="tradie_jobs_export.json",
    mime="application/json",
)
