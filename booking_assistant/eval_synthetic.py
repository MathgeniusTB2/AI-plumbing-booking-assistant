from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from booking_assistant.fallback_extractor import extraction_turn_fallback
from booking_assistant.mock_calendar import CALENDAR_PATH
from booking_assistant.schemas import booking_info_complete, merge_turn_into_slots
from booking_assistant.scheduler import find_appointment_slot


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CASES_PATH = DATA_DIR / "eval" / "synthetic_booking_eval.jsonl"


def _norm(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return " ".join(s.split())


def _norm_issue(v: Any) -> str | None:
    s = _norm(v)
    return s.lower() if s else None


def _norm_urgency(v: Any) -> str | None:
    s = _norm(v)
    return s.lower() if s else None


def _value_match(key: str, pred: Any, gold: Any) -> bool:
    if key in ("issue_category",):
        return _norm_issue(pred) == _norm_issue(gold)
    if key in ("urgency",):
        return _norm_urgency(pred) == _norm_urgency(gold)
    return _norm(pred) == _norm(gold)


@dataclass(frozen=True)
class Case:
    case_id: str
    turns: list[str]
    gold_final_slots: dict[str, Any]


def load_cases(path: Path) -> list[Case]:
    cases: list[Case] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cases.append(
                Case(
                    case_id=str(row["case_id"]),
                    turns=list(row["turns"]),
                    gold_final_slots=dict(row["gold_final_slots"]),
                )
            )
    return cases


def run_case_fallback(case: Case) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    complete_at: int | None = None

    for i, msg in enumerate(case.turns):
        turn = extraction_turn_fallback(msg, slots)
        slots = merge_turn_into_slots(slots, turn)
        if complete_at is None and booking_info_complete(slots):
            complete_at = i + 1  # turns are 1-indexed for reporting

    return {"final_slots": slots, "complete_at": complete_at}


def score_cases(cases: list[Case], *, try_schedule: bool) -> dict[str, Any]:
    # Keys we score. (We intentionally do not score assistant_reply.)
    keys = [
        "issue_category",
        "urgency",
        "location",
        "customer_name",
        "customer_phone",
        "customer_email",
        "preferred_time_notes",
    ]

    # Micro counts over key/value pairs present in gold.
    tp = fp = fn = 0
    per_slot_acc: dict[str, list[int]] = {k: [] for k in keys}

    dialog_success = 0
    turns_to_complete: list[int] = []
    scheduled_success = 0

    # Isolate calendar side effects into a temp file.
    tmp_calendar = tempfile.NamedTemporaryFile(prefix="mock_calendar_eval_", suffix=".jsonl", delete=False)
    tmp_calendar_path = Path(tmp_calendar.name)
    tmp_calendar.close()
    try:
        # Monkeypatch module global used by scheduler
        import booking_assistant.mock_calendar as cal

        cal.CALENDAR_PATH = tmp_calendar_path  # type: ignore[attr-defined]

        for case in cases:
            pred = run_case_fallback(case)
            pred_slots = pred["final_slots"]
            is_complete = booking_info_complete(pred_slots)
            if is_complete:
                dialog_success += 1
                if pred["complete_at"] is not None:
                    turns_to_complete.append(int(pred["complete_at"]))

            if try_schedule and is_complete:
                appt = find_appointment_slot(pred_slots, horizon_days=7)
                if appt is not None:
                    scheduled_success += 1

            # Gold scoring: only keys that exist (non-null) in gold_final_slots are required.
            gold = case.gold_final_slots
            for k in keys:
                g = gold.get(k)
                p = pred_slots.get(k)
                if g is None:
                    # We don't penalize missing optional info, but count false positives if model invents it.
                    if p is not None and _norm(p) is not None:
                        fp += 1
                    continue
                # gold expects a value for this key
                if p is None or _norm(p) is None:
                    fn += 1
                    per_slot_acc[k].append(0)
                    continue
                if _value_match(k, p, g):
                    tp += 1
                    per_slot_acc[k].append(1)
                else:
                    fp += 1
                    fn += 1
                    per_slot_acc[k].append(0)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        per_slot_summary = {
            k: (sum(v) / len(v) if v else 0.0) for k, v in per_slot_acc.items()
        }

        out = {
            "n_cases": len(cases),
            "dialog_success_rate": dialog_success / len(cases) if cases else 0.0,
            "avg_turns_to_complete": (statistics.mean(turns_to_complete) if turns_to_complete else None),
            "median_turns_to_complete": (statistics.median(turns_to_complete) if turns_to_complete else None),
            "slot_micro_precision": precision,
            "slot_micro_recall": recall,
            "slot_micro_f1": f1,
            "per_slot_accuracy": per_slot_summary,
        }
        if try_schedule:
            out["scheduled_success_rate"] = (
                scheduled_success / dialog_success if dialog_success else 0.0
            )
        return out
    finally:
        try:
            tmp_calendar_path.unlink(missing_ok=True)
        except Exception:
            pass
        # Restore original calendar path if possible
        try:
            import booking_assistant.mock_calendar as cal

            cal.CALENDAR_PATH = CALENDAR_PATH  # type: ignore[attr-defined]
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate heuristic fallback extractor on synthetic labeled cases.")
    ap.add_argument("--cases", type=str, default=str(DEFAULT_CASES_PATH))
    ap.add_argument("--try-schedule", action="store_true", help="Also attempt scheduling for complete dialogues (writes to a temp calendar).")
    args = ap.parse_args()

    cases = load_cases(Path(args.cases))
    metrics = score_cases(cases, try_schedule=bool(args.try_schedule))
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
