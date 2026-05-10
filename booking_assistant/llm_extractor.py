from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from openai import OpenAI
from pydantic import ValidationError

from booking_assistant.prompts import JSON_REPAIR_SYSTEM, SYSTEM_PROMPT
from booking_assistant.schemas import ExtractionTurn

# Recommended for slot-filling + JSON on consumer hardware via Ollama.
DEFAULT_LOCAL_LLM_MODEL = "qwen2.5:3b-instruct"


def local_llm_base_url() -> str:
    return os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")


def resolved_local_llm_model() -> str:
    return os.getenv("LOCAL_LLM_MODEL", DEFAULT_LOCAL_LLM_MODEL)


def local_llm_reachable(timeout: float = 1.5) -> bool:
    """True if an OpenAI-compatible server responds (e.g. Ollama at /v1/models)."""
    url = f"{local_llm_base_url()}/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def _client() -> OpenAI:
    return OpenAI(
        base_url=local_llm_base_url(),
        api_key=os.getenv("LOCAL_LLM_API_KEY", "ollama"),
    )


def _unwrap_json_text(content: str) -> str:
    """Strip optional ```json ... ``` wrappers and extract a JSON object."""
    text = content.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    else:
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text.strip()


def _chat_create(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    json_mode: bool,
    temperature: float,
):
    base: dict = {"model": model, "temperature": temperature, "messages": messages}
    if json_mode:
        try:
            return client.chat.completions.create(
                **base,
                response_format={"type": "json_object"},
            )
        except Exception:
            pass
    return client.chat.completions.create(**base)


def _message_text(rsp) -> str:
    raw = rsp.choices[0].message.content
    if not raw:
        raise RuntimeError("Empty model response")
    return raw


def _parse_turn(content: str) -> ExtractionTurn:
    blob = _unwrap_json_text(content)
    data = json.loads(blob)
    return ExtractionTurn.model_validate(data)


def extraction_turn_via_llm(
    user_message: str,
    prior_slots_summary: str,
    *,
    model: str | None = None,
) -> ExtractionTurn:
    """Call a local OpenAI-compatible server (Ollama, LM Studio, etc.) — no paid API."""
    client = _client()
    m = model or resolved_local_llm_model()
    temperature = float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.2"))

    payload = (
        "Current known slots (JSON, may be empty):\n"
        f"{prior_slots_summary}\n\n"
        "Latest customer message:\n"
        f"{user_message.strip()}"
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": payload},
    ]

    rsp = _chat_create(client, model=m, messages=messages, json_mode=True, temperature=temperature)
    raw_text = _message_text(rsp)

    try:
        return _parse_turn(raw_text)
    except (json.JSONDecodeError, ValidationError) as first_exc:
        repair_user = (
            f"The assistant output failed to parse ({type(first_exc).__name__}). "
            f"Return corrected JSON ONLY.\n\nBroken output:\n{raw_text[:8000]}"
        )
        repair_messages = [
            {"role": "system", "content": JSON_REPAIR_SYSTEM},
            {"role": "user", "content": repair_user},
        ]
        rsp2 = _chat_create(
            client,
            model=m,
            messages=repair_messages,
            json_mode=True,
            temperature=min(temperature, 0.15),
        )
        fixed = _message_text(rsp2)
        return _parse_turn(fixed)
