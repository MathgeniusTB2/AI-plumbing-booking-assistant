from __future__ import annotations

import json
import os

import streamlit as st
from dotenv import load_dotenv

from booking_assistant.fallback_extractor import extraction_turn_fallback
from booking_assistant.llm_extractor import extraction_turn_via_llm
from booking_assistant.llm_extractor import local_llm_reachable
from booking_assistant.llm_extractor import resolved_local_llm_model
from booking_assistant.mock_notify import customer_confirmation_text
from booking_assistant.mock_notify import plumber_notification_text
from booking_assistant.scheduler import find_appointment_slot
from booking_assistant.scheduler import load_plumbers
from booking_assistant.scheduler import plumber_matches_issue
from booking_assistant.schemas import booking_info_complete
from booking_assistant.schemas import merge_turn_into_slots
from booking_assistant.schemas import missing_booking_fields
from booking_assistant.schemas import REQUIRED_BOOKING_SLOTS

load_dotenv()

st.set_page_config(
    page_title="Plumbing booking assistant",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)


def use_llm() -> bool:
    return os.getenv("USE_LLM", "1").strip() != "0"


def run_extraction(user_message: str, slots: dict) -> object:
    prior = json.dumps(slots, ensure_ascii=False)
    if use_llm() and local_llm_reachable():
        try:
            return extraction_turn_via_llm(user_message, prior)
        except Exception:
            return extraction_turn_fallback(user_message, slots)
    return extraction_turn_fallback(user_message, slots)


def init_state() -> None:
    defaults = {
        "slots": {},
        "conversation_phase": "collecting",
        "appointment": None,
        "messages": [],
        "last_booking_notifications": None,
        "_toast_llm_unreachable": False,
        "_booking_balloons_once": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_booking() -> None:
    st.session_state.slots = {}
    st.session_state.conversation_phase = "collecting"
    st.session_state.appointment = None
    st.session_state.messages = []
    st.session_state.last_booking_notifications = None


_SLOT_LABELS: dict[str, str] = {
    "issue_category": "Issue type",
    "urgency": "Urgency",
    "location": "Location",
    "customer_name": "Your name",
    "customer_phone_or_email": "Phone or email",
}

_SLOT_TRACK_KEYS = (*REQUIRED_BOOKING_SLOTS, "customer_phone_or_email")


def render_slot_progress(slots: dict) -> None:
    miss = missing_booking_fields(dict(slots))
    miss_set = set(miss)
    total = len(_SLOT_TRACK_KEYS)
    filled = total - len(miss_set)
    st.progress(min(1.0, filled / total) if total else 0.0)
    st.metric("Fields complete", f"{filled} / {total}")

    bullets: list[str] = []
    for key in _SLOT_TRACK_KEYS:
        human = _SLOT_LABELS.get(key, key.replace("_", " "))
        if key in miss_set:
            bullets.append(f"{human}: *needed*")
        else:
            bullets.append(f"{human}: ✓")
    st.markdown("  \n".join([f"- {b}" for b in bullets]))

    tn = slots.get("preferred_time_notes") if slots else None
    if tn and str(tn).strip():
        st.info(f"_Optional timing:_ {tn}")


init_state()

if use_llm() and not local_llm_reachable() and not st.session_state._toast_llm_unreachable:
    st.toast("Using rule-based extraction (local LLM unreachable).", icon="ℹ️")
    st.session_state._toast_llm_unreachable = True

st.title("AI plumbing booking assistant")
st.markdown("##### Book a plumber in plain English — mock scheduler, no SMS or OAuth.")
st.caption("Mock scheduling and calendar data only.")

# Prominent disclosure (only when AI extraction is OFF).
if not (use_llm() and local_llm_reachable()):
    st.warning(
        "AI extraction is **OFF**: this app is using **rule-based** (regex/keywords) extraction only. "
        "No LLM is called for understanding your messages.\n\n"
        "**To turn AI on:** set `USE_LLM=1`, start an OpenAI-compatible local server at "
        "`LOCAL_LLM_BASE_URL`, then restart the app. (If the server is unreachable, the app will "
        "auto-fallback to rule-based extraction.)",
        icon="⚠️",
    )

with st.sidebar:
    st.markdown("###### Navigation")
    try:
        st.page_link("pages/2_Tradie_dispatch.py", label="Tradie dispatch board")
    except Exception:
        st.markdown("Tradie dispatch: use the sidebar **Pages** menu.")

    st.divider()

    st.markdown("###### Assistant mode")
    if use_llm():
        if local_llm_reachable():
            st.success(
                "Local LLM reachable — **free** OpenAI-compatible endpoint (e.g. Ollama)."
            )
            st.caption(f"Model `{resolved_local_llm_model()}`")
        else:
            st.warning(
                "`USE_LLM=1` — start your server at `LOCAL_LLM_BASE_URL`, "
                "or set `USE_LLM=0`."
            )
    else:
        st.info("Heuristic-only (`USE_LLM=0`).")

    st.divider()
    st.markdown("###### Booking progress")
    render_slot_progress(st.session_state.slots)

    notif = st.session_state.last_booking_notifications
    if notif:
        st.success("Latest booking confirmed — drafts below.")
        with st.expander("Mock notification drafts", expanded=False):
            t1, t2 = st.tabs(["Customer SMS / email", "Tradie dispatch"])
            with t1:
                st.text(notif["customer"])
            with t2:
                st.text(notif["plumber"])

    if st.button("New booking", type="primary", use_container_width=True):
        reset_booking()
        st.rerun()

    if st.session_state.slots:
        with st.expander("Extracted slots (JSON)", expanded=False):
            st.json(st.session_state.slots)

st.divider()

for role, content in st.session_state.messages:
    with st.chat_message(role):
        st.markdown(content)

user_in = st.chat_input("Tell us what's going on…")
if not user_in:
    st.stop()

if st.session_state.conversation_phase == "booked":
    st.session_state.messages.append(("user", user_in.strip()))
    with st.chat_message("user"):
        st.markdown(user_in.strip())
    booked_msg = (
        "This booking is already confirmed for this chat session. "
        "Use **New booking** in the sidebar to start another appointment."
    )
    st.session_state.messages.append(("assistant", booked_msg))
    with st.chat_message("assistant"):
        st.markdown(booked_msg)
    st.stop()

st.session_state.messages.append(("user", user_in.strip()))
with st.chat_message("user"):
    st.markdown(user_in.strip())

with st.spinner("Understanding your message…"):
    turn = run_extraction(user_in, dict(st.session_state.slots))
merged = merge_turn_into_slots(dict(st.session_state.slots), turn)
st.session_state.slots = merged

eligible = True
issue = merged.get("issue_category")
if issue:
    eligible = any(
        plumber_matches_issue(str(issue), p) for p in load_plumbers()
    )

if booking_info_complete(merged):
    if not eligible:
        no_match = (
            "Thanks — we've captured your contact details and issue. "
            "This demo roster has no labelled specialist for that category; "
            "try wording the issue more generally (for example leak, blocked drain, or general)."
        )
        st.session_state.messages.append(("assistant", no_match))
        with st.chat_message("assistant"):
            st.markdown(no_match)
        st.stop()

    with st.spinner("Finding the next available slot…"):
        appt = find_appointment_slot(merged)
    if appt:
        cust = customer_confirmation_text(appt)
        plum = plumber_notification_text(appt)
        if not st.session_state._booking_balloons_once:
            st.balloons()
            st.session_state._booking_balloons_once = True

        summary_body = (
            f"**{appt.start:%a %d %b, %H:%M}–{appt.end:%H:%M}** · **{appt.plumber_name}** · {appt.issue_summary}\n\n"
            f"Draft notifications are in the sidebar (**Mock notification drafts**)."
        )
        st.session_state.messages.append(("assistant", summary_body))
        st.session_state.last_booking_notifications = {"customer": cust, "plumber": plum}
        with st.chat_message("assistant"):
            st.success("Appointment confirmed.")
            st.markdown(summary_body)

        st.session_state.conversation_phase = "booked"
        st.session_state.appointment = appt
    else:
        sorry = (
            "I have everything needed, but this demo couldn't find an open slot "
            "in the mocked availability window — try adjusting preferred timing "
            "or widen plumber hours in `data/plumbers.json`."
        )
        st.session_state.messages.append(("assistant", sorry))
        with st.chat_message("assistant"):
            st.markdown(sorry)
else:
    reply = turn.assistant_reply
    st.session_state.messages.append(("assistant", reply))
    with st.chat_message("assistant"):
        st.markdown(reply)

# Trigger a clean rerun so sidebar progress reflects this turn immediately.
st.rerun()
