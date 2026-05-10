"""Tradie-facing job board (reads same mock_calendar.jsonl as the customer app)."""

from __future__ import annotations

import json

import streamlit as st

from booking_assistant.mock_calendar import CALENDAR_PATH
from booking_assistant.mock_calendar import list_events_chronological
from booking_assistant.mock_notify import plumber_notification_text
from booking_assistant.models import ScheduledAppointment
from booking_assistant.scheduler import load_plumbers

st.set_page_config(page_title="Tradie dispatch", page_icon="🔧", layout="wide")

st.title("Tradie dispatch board")
st.caption(
    "Mock **plumber-facing** view: jobs written when customers confirm bookings. "
    f"Data file: `{CALENDAR_PATH.name}`"
)

plumbers = load_plumbers()
filter_labels = ["All plumbers"] + [p.name for p in plumbers]
choice = st.sidebar.selectbox("Show jobs for", filter_labels, index=0)
plumber_id: str | None = None
if choice != "All plumbers":
    plumber_id = next(p.id for p in plumbers if p.name == choice)

upcoming_only = st.sidebar.checkbox("Upcoming only (hide past jobs)", value=True)
raw_json = st.sidebar.checkbox("Show raw calendar row (debug)", value=False)

if st.sidebar.button("Refresh list"):
    st.rerun()

events = list_events_chronological(plumber_id=plumber_id, upcoming_only=upcoming_only)

st.sidebar.metric("Jobs shown", len(events))

if not events:
    st.info(
        "No jobs match this filter yet. Complete a booking in the **Customer** page and "
        "come back here — or turn off “Upcoming only” to see past slots."
    )
    st.stop()

for i, ev in enumerate(events):
    appt = ScheduledAppointment.try_from_calendar_record(ev)
    if appt is None:
        with st.expander(f"Invalid row {i + 1}", expanded=False):
            st.json(ev)
        continue

    label = (
        f"{appt.start:%a %d %b %H:%M}–{appt.end:%H:%M} · {appt.customer_name} · {appt.issue_summary}"
    )
    with st.expander(label, expanded=(i == 0)):
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
            st.code(plumber_notification_text(appt), language=None)
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
