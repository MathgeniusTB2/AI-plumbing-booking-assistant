from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

IntentLiteral = Literal["book_plumbing", "question", "other"]


class ExtractionTurn(BaseModel):
    """Structured output for one conversational turn."""

    intent: IntentLiteral = Field(
        default="book_plumbing",
        description="Primary user goal for this message.",
    )
    issue_category: str | None = Field(
        default=None,
        description="Normalized issue e.g. leak, blocked_drain, toilet, hot_water, gas, general",
    )
    urgency: str | None = Field(
        default=None,
        description="low, medium, high, or emergency",
    )
    location: str | None = Field(
        default=None,
        description="Street address or suburb + state",
    )
    preferred_time_notes: str | None = Field(
        default=None,
        description="Customer phrasing about when they prefer service",
    )
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None

    assistant_reply: str = Field(
        ...,
        description="Natural reply to user: confirm receipt, clarify missing slots politely.",
    )
    confidence_notes: str | None = Field(
        default=None,
        description="Optional brief note about uncertainty.",
    )

    @field_validator("intent", mode="before")
    @classmethod
    def _coerce_intent(cls, v):  # noqa: ANN001
        if v in ("book_plumbing", "question", "other"):
            return v
        return "book_plumbing"


REQUIRED_BOOKING_SLOTS: tuple[str, ...] = (
    "issue_category",
    "urgency",
    "location",
    "customer_name",
)


def missing_booking_fields(slots: dict) -> list[str]:
    """Return human-readable missing required keys (including contact rule)."""
    missing: list[str] = []
    for key in REQUIRED_BOOKING_SLOTS:
        val = slots.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(key)
    phone = slots.get("customer_phone")
    email = slots.get("customer_email")
    ok_contact = (
        phone and str(phone).strip()
    ) or (email and str(email).strip())
    if not ok_contact:
        missing.append("customer_phone_or_email")
    return missing


def booking_info_complete(slots: dict) -> bool:
    return len(missing_booking_fields(slots)) == 0


def merge_turn_into_slots(prior: dict, turn: ExtractionTurn) -> dict:
    """Overlay non-empty fields from a model turn onto prior slots."""
    out = dict(prior)
    for key in (
        "issue_category",
        "urgency",
        "location",
        "preferred_time_notes",
        "customer_name",
        "customer_phone",
        "customer_email",
    ):
        val = getattr(turn, key, None)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        out[key] = val.strip() if isinstance(val, str) else val
    return out
