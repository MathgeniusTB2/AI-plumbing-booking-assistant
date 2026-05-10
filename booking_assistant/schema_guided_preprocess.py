"""
Load and preprocess Hugging Face ``google-research-datasets/schema_guided_dstc8``.

Requires ``datasets`` 2.x and ``trust_remote_code=True`` (the dataset ships a
legacy builder script — see requirements.txt pin).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

HF_DATASET_ID = "google-research-datasets/schema_guided_dstc8"


def normalize_slot_value(raw: Any) -> str | None:
    """Flatten SGD slot_value_list entries like [['San Jose']] → 'San Jose'."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw if raw.strip() else None
    if isinstance(raw, list):
        if not raw:
            return None
        inner = raw[0]
        if isinstance(inner, list):
            return normalize_slot_value(inner)
        if isinstance(inner, str):
            return inner if inner.strip() else None
        return str(inner)
    return str(raw)


def slot_dict_from_frame(frame: dict[str, Any]) -> dict[str, str]:
    slots: dict[str, str] = {}
    for st in frame.get("state") or []:
        sv = st.get("slot_values") or {}
        names = sv.get("slot_name") or []
        values = sv.get("slot_value_list") or []
        for name, raw in zip(names, values):
            nv = normalize_slot_value(raw)
            if nv is not None:
                slots[str(name)] = nv
    return slots


def primary_intent_from_frame(frame: dict[str, Any]) -> str:
    for st in frame.get("state") or []:
        intent = st.get("active_intent") or ""
        if isinstance(intent, str) and intent.strip():
            return intent.strip()
    return ""


def load_sgd_stream(split: str, *, trust_remote_code: bool = True):
    from datasets import load_dataset

    return load_dataset(
        HF_DATASET_ID,
        split=split,
        streaming=True,
        trust_remote_code=trust_remote_code,
    )


def dialogue_services(dialogue: dict[str, Any]) -> list[str]:
    raw = dialogue.get("services") or []
    out: list[str] = []
    for s in raw:
        if isinstance(s, str) and s.strip():
            out.append(s.strip())
    return out


def passes_domain_filter(dialogue: dict[str, Any], allow: set[str] | None) -> bool:
    if not allow:
        return True
    svcs = set(dialogue_services(dialogue))
    return bool(svcs & allow)


def dialogue_to_records(dialogue: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One summary record + per-user-turn records."""
    did = dialogue["dialogue_id"]
    services = dialogue_services(dialogue)
    turns = dialogue["turns"]
    speakers = turns["speaker"]
    utterances = turns["utterance"]
    frames = turns["frames"]

    linear: list[dict[str, str]] = []
    for sp, utt in zip(speakers, utterances):
        role = "user" if int(sp) == 0 else "system"
        linear.append({"speaker": role, "text": str(utt)})

    dialogue_row = {
        "dialogue_id": did,
        "services": services,
        "turns": linear,
    }

    user_rows: list[dict[str, Any]] = []
    history: list[list[str]] = []

    for idx, (sp, utt) in enumerate(zip(speakers, utterances)):
        role = "user" if int(sp) == 0 else "system"
        history.append([role, str(utt)])

        if role != "user":
            continue

        frame = frames[idx] if idx < len(frames) else {}
        slots = slot_dict_from_frame(frame)
        intent = primary_intent_from_frame(frame)

        next_system = ""
        if idx + 1 < len(speakers) and int(speakers[idx + 1]) == 1:
            next_system = str(utterances[idx + 1])

        prior = history[:-1]

        user_rows.append(
            {
                "dialogue_id": did,
                "services": services,
                "turn_idx": idx,
                "user_utterance": str(utt),
                "system_utterance": next_system,
                "active_intent": intent,
                "filled_slots": slots,
                "dialogue_prefix": prior,
            }
        )

    return dialogue_row, user_rows


def iter_preprocessed_dialogues(
    split: str,
    *,
    max_dialogues: int | None = None,
    domain_allowlist: set[str] | None = None,
) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    stream = load_sgd_stream(split)
    seen = 0
    for dialogue in stream:
        if not passes_domain_filter(dialogue, domain_allowlist):
            continue
        yield dialogue_to_records(dialogue)
        seen += 1
        if max_dialogues is not None and seen >= max_dialogues:
            break


def run_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preprocess Schema-Guided Dialogue (DSTC8) from Hugging Face.")
    parser.add_argument("--split", default="train", choices=["train", "validation", "test"])
    parser.add_argument(
        "--max-dialogues",
        type=int,
        default=2000,
        help="Cap dialogues (-1 = entire split; can be very large).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory for JSONL outputs.",
    )
    parser.add_argument(
        "--prefix",
        default="sgd",
        help="Output file prefix, e.g. sgd -> sgd.train.dialogues.jsonl",
    )
    parser.add_argument(
        "--domains",
        nargs="*",
        default=[],
        help="Optional service names to keep, e.g. Restaurants_1 Hotels_2 (default: all).",
    )
    args = parser.parse_args(argv)

    allow = {d.strip() for d in args.domains if d.strip()} or None

    out_dir: Path = args.output_dir
    tag = args.split
    path_d = out_dir / f"{args.prefix}.{tag}.dialogues.jsonl"
    path_t = out_dir / f"{args.prefix}.{tag}.turns.jsonl"
    max_d = None if args.max_dialogues < 0 else args.max_dialogues

    out_dir.mkdir(parents=True, exist_ok=True)
    nd = nt = 0
    with path_d.open("w", encoding="utf-8") as fd, path_t.open("w", encoding="utf-8") as ft:
        for drow, trows in iter_preprocessed_dialogues(args.split, max_dialogues=max_d, domain_allowlist=allow):
            fd.write(json.dumps(drow, ensure_ascii=False) + "\n")
            nd += 1
            for tr in trows:
                ft.write(json.dumps(tr, ensure_ascii=False) + "\n")
                nt += 1

    print(f"Wrote {nd} dialogues -> {path_d.resolve()}")
    print(f"Wrote {nt} user-turn rows -> {path_t.resolve()}")
    print(f"Source: {HF_DATASET_ID} split={args.split!r} max_dialogues={max_d!r}")


if __name__ == "__main__":
    run_cli()
