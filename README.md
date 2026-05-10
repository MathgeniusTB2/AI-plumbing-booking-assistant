# AI plumbing booking assistant

Streamlit demo of an NLP-driven plumbing booking flow: extract slots from free text (local LLM or rules), mock scheduling against a static plumber roster, append bookings to a JSONL “calendar,” and show mock customer/tradie notifications.

## Features

- **Customer chat** (`app.py`): slot filling (issue, urgency, location, contact, timing notes), clarification loop until fields are complete, then mock schedule + confirmation.
- **Tradie dispatch** ([`pages/2_Tradie_dispatch.py`](pages/2_Tradie_dispatch.py)): same mock calendar as a plumber-facing job list (filter by plumber, upcoming only, export JSON).
- **Local LLM** (no paid API): OpenAI-compatible endpoint — defaults to **Ollama** + `qwen2.5:3b-instruct`. **Heuristic fallback** when `USE_LLM=0` or the server is down.
- **Schema-Guided Dialogue preprocessing** ([`booking_assistant/schema_guided_preprocess.py`](booking_assistant/schema_guided_preprocess.py)): optional export of [`google-research-datasets/schema_guided_dstc8`](https://huggingface.co/datasets/google-research-datasets/schema_guided_dstc8) for experiments / fine-tuning (see below).

## Requirements

- Python **3.10+**
- Optional: **[Ollama](https://ollama.com/)** for local models (`ollama pull qwen2.5:3b-instruct` recommended).

## Quick start

```bash
cd /path/to/NLP
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # edit if needed; optional
```

Start the LLM server (optional):

```bash
ollama serve                         # in a separate terminal if not already running
ollama pull qwen2.5:3b-instruct
```

Run the app:

```bash
python -m streamlit run app.py
```

Visual theme and chrome (colors, background, minimal toolbar) live in [`.streamlit/config.toml`](.streamlit/config.toml). Edit the `[theme]` section to rebrand.

Open the URL Streamlit prints (usually [http://localhost:8501](http://localhost:8501)). Use the sidebar **multipage** menu to switch between **Customer** and **Tradie dispatch**.

## Environment variables

Copy [`.env.example`](.env.example) to `.env`. Main variables:

| Variable | Purpose |
|----------|---------|
| `USE_LLM` | `1` = use local LLM when reachable; `0` = rules only. |
| `LOCAL_LLM_BASE_URL` | OpenAI-compatible base URL (Ollama: `http://127.0.0.1:11434/v1`). |
| `LOCAL_LLM_MODEL` | Model tag (e.g. `qwen2.5:3b-instruct`). |
| `LOCAL_LLM_TEMPERATURE` | Lower = more deterministic JSON (default `0.2`). |
| `LOCAL_LLM_API_KEY` | Placeholder for the HTTP client; Ollama ignores it. |

## Data files

| Path | Role |
|------|------|
| [`data/plumbers.json`](data/plumbers.json) | Mock plumbers, skills, weekly availability. |
| `data/mock_calendar.jsonl` | Append-only mock bookings (created at runtime; gitignored). |
| `data/processed/` | SGD JSONL exports (gitignored; see preprocessing). |

## Schema-Guided Dialogue (SGD) preprocessing

Loads **DSTC8 Schema-Guided Dialogue** from Hugging Face. Because the hub dataset uses a **legacy loader script**, this repo pins **`datasets` 2.x** (see [`requirements.txt`](requirements.txt)).

```bash
python -m booking_assistant.schema_guided_preprocess --split train --max-dialogues 2000
```

Outputs under `data/processed/` (default prefix `sgd`):

- `sgd.train.dialogues.jsonl` — full dialogues with speaker-labelled turns.
- `sgd.train.turns.jsonl` — one row per **user** turn with `filled_slots`, `active_intent`, `dialogue_prefix`, etc.

Options: `--domains Restaurants_1 ...` to filter services, `--max-dialogues -1` for the full split (large).

## Project layout

```text
app.py                          # Customer Streamlit entrypoint
pages/2_Tradie_dispatch.py      # Tradie job board
booking_assistant/              # Core logic (extractors, scheduler, calendar, SGD prep)
data/plumbers.json              # Mock roster
requirements.txt
.env.example
```
