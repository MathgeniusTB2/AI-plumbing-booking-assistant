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

load_dotenv()

st.set_page_config(page_title="Plumbing booking assistant", page_icon=None)


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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_booking() -> None:
    st.session_state.slots = {}
    st.session_state.conversation_phase = "collecting"
    st.session_state.appointment = None
    st.session_state.messages = []


init_state()

st.title("AI plumbing booking assistant")
st.caption(
    "Describe your plumbing issue in plain language. Mock scheduling and calendar — no real SMS or OAuth."
)
st.caption("**Tradie view:** open **Tradie dispatch** from the left sidebar (multipage menu).")

with st.sidebar:
    st.header("Assistant mode")
    if use_llm():
        if local_llm_reachable():
            st.success(
                "Local LLM reachable — extraction uses your **free** OpenAI-compatible "
                "server (e.g. Ollama)."
            )
            st.caption(f"Model: `{resolved_local_llm_model()}`")
        else:
            st.warning(
                "`USE_LLM=1` but no server at `LOCAL_LLM_BASE_URL` "
                "(start [Ollama](https://ollama.com/), or set `USE_LLM=0` for rules-only)."
            )
    else:
        st.info("Heuristic-only mode (`USE_LLM=0`) — no local model.")

    if st.button("New booking"):
        reset_booking()
        st.rerun()

    if st.session_state.slots:
        with st.expander("Extracted slots (session)"):
            st.json(st.session_state.slots)

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

    appt = find_appointment_slot(merged)
    if appt:
        cust = customer_confirmation_text(appt)
        plum = plumber_notification_text(appt)
        summary = (
            f"✅ **Appointment confirmed**\n\n"
            f"- **When:** {appt.start:%a %d %b %Y, %H:%M} → {appt.end:%H:%M}\n"
            f"- **Plumber:** {appt.plumber_name}\n"
            f"- **Job:** {appt.issue_summary}\n"
        )
        history = (
            summary
            + "\n**Mock — customer confirmation**\n"
            + cust
            + "\n\n**Mock — plumber notification**\n"
            + plum
        )
        with st.chat_message("assistant"):
            st.markdown(summary)
            c1, c2 = st.columns(2)
            with c1:
                with st.expander("Mock — customer SMS / email"):
                    st.write(cust)
            with c2:
                with st.expander("Mock — plumber dispatch"):
                    st.write(plum)
        st.session_state.messages.append(("assistant", history))
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