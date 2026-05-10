from __future__ import annotations

from booking_assistant.models import ScheduledAppointment


def customer_confirmation_text(appt: ScheduledAppointment) -> str:
    return (
        f"Your plumbing visit is confirmed for {appt.start:%A %d %b %Y at %H:%M}–{appt.end:%H:%M} "
        f"with {appt.plumber_name}. Job: {appt.issue_summary}. "
        f"If anything changes, reply to this thread."
    )


def plumber_notification_text(appt: ScheduledAppointment) -> str:
    return (
        f"New job — {appt.customer_name} | {appt.start:%a %d %b %H:%M}–{appt.end:%H:%M} | "
        f"{appt.issue_summary}. Address/directions: {appt.location}. "
        f"Primary contact: {appt.customer_phone or appt.customer_email or 'not provided'}."
    )
