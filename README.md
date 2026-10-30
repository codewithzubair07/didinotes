# DidiNotes (ASHA Diary)

Demo. Do not enter real patient data.

## What It Is

**DidiNotes** (internally called "ASHA Diary") is a voice-first work diary for Accredited Social Health Activist (ASHA) community health workers in West Bengal, India.

An ASHA worker verbally speaks her daily activities in colloquial Bengali or Benglish (Bengali mixed with English), such as:
> *"aaj Rina-r ANC visit korlam, 2 jon baccha-r teeka dilam"*

The application:
1. Transcribes audio input using a Speech-to-Text adapter (Mock STT for local development; Gnani Prisma in production).
2. Extracts structured work records using an NLU extractor (task type, event date, count, beneficiary reference).
3. Holds an interactive voice/text confirmation dialogue (reading back recognized records, asking single follow-up questions for missing fields, handling corrections, resolving date traps such as *kal* and *porshu*).
4. Persists confirmed records to an SQLite database.
5. Generates official register-ready lines and monthly incentive claim sheets with CSV export and printable summaries.
6. **Strictly refuses clinical advice queries.** DidiNotes is a record-keeping diary, never a clinical decision or diagnostic tool.

---

## Status

- **Milestones 1 to 4 Complete**:
  - Backend API: FastAPI + Pydantic v2 + SQLAlchemy/SQLite in `apps/api`.
  - Frontend: Next.js (App Router, TypeScript strict, Tailwind CSS) in `apps/web`.
  - NLU Extractor: Pure rules-based extractor with 100% exact match across the 60-item evaluation set; optional OpenAI LLM fallback.
  - Evaluation Suite: 60-item utterance and dialogue evaluation suite (`eval/run_extraction_eval.py`), noise mixing tool (`eval/add_noise.py`), and STT Word Error Rate evaluation tool (`eval/run_stt_eval.py`).
  - Automated Smoke Scripts: Cross-platform end-to-end conversation and persistence smoke scripts (`scripts/smoke.sh`, `scripts/smoke.ps1`).
  - 164 automated backend unit and integration tests passing.

---

## Quick Start

The system runs end-to-end with **no external API keys** out of the box (uses `MockSTT` and browser speech synthesis).

### Windows

#### 1. Backend (FastAPI)
```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
uvicorn app.main:app --port 8000
```

#### 2. Frontend (Next.js)
```powershell
cd apps/web
cmd /c npm install
cmd /c npm run typecheck
cmd /c npm run build
cmd /c npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

#### 3. Automated Smoke Test (Windows)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
```

---

### macOS and Linux

#### 1. Backend (FastAPI)
```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
uvicorn app.main:app --port 8000
```

#### 2. Frontend (Next.js)
```bash
cd apps/web
npm install
npm run typecheck
npm run build
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

#### 3. Automated Smoke Test (macOS / Linux)
```bash
bash scripts/smoke.sh
```

---

## Configuration

Settings are managed via `pydantic-settings` from environment variables or a `.env` file at repository root. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `rules` | NLU extraction engine (`rules` or `openai`). Defaults to zero-dependency rules. |
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key if `LLM_PROVIDER=openai`. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name for OpenAI extractor. Runs with `temperature: 0`. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible endpoint. |
| `LLM_TIMEOUT_SECONDS` | `5.0` | Timeout in seconds before falling back to rules extractor. |
| `STT_PROVIDER` | `mock` | Speech-to-Text provider (`mock` or `gnani`). Runs locally without keys. |
| `TTS_PROVIDER` | `browser` | Text-to-Speech provider (`browser` or `gnani`). Browser TTS triggers client synthesis. |
| `STORE_AUDIO` | `false` | Whether to persist uploaded audio files to disk. Currently uncommitted in memory. |
| `GNANI_API_KEY` | *(empty)* | API key for Gnani Prisma STT / Timbre TTS when plugged in. |
| `GNANI_BASE_URL` | *(empty)* | Base URL for Gnani services. |
| `TZ` | `Asia/Kolkata` | Application timezone (Indian Standard Time). |
| `DATABASE_URL` | `sqlite:///asha_diary.db` | SQLAlchemy SQLite database connection string. |
| `CONFIG_DIR` | `config/` | Path to YAML configuration directory. |
| `MAX_AUDIO_BYTES` | `2000000` | Maximum uploaded audio payload size (2 MB). |
| `MAX_AUDIO_SECONDS` | `60` | Maximum audio duration in seconds. |
| `RATE_LIMIT_PER_MINUTE` | `30` | In-memory rate limit per client IP for `/api/turn`. |
| `SESSION_TTL_SECONDS` | `900` | Dialogue session time-to-live in memory (15 minutes). |

---

## API Endpoints

All backend routes are prefixed with `/api`.

### Core & Configuration
- `GET /api/health` — Returns system status (`"status": "ok"`) and the mandatory demo banner.
- `GET /api/config/task-types` — Returns the list of 6 health task types and required documentation.

### Conversational Turn Pipeline
- `POST /api/turn` — Handles audio or JSON text input. Accepts `{ session_id, text, lang }` or multipart audio. Returns:
  - `transcript`: Transcribed speech or echoed input text.
  - `entries`: List of recognized draft entries.
  - `response_text`: Bengali or English dialogue response for the ASHA worker.
  - `response_audio`: Base64-encoded audio if server TTS is active, else `null` (uses browser TTS).
  - `ui_hint`: UI action tag (`ask_field`, `confirm`, `saved`, `repeat`, `type_input`, `refusal`).
  - `timings_ms`: Latency breakdown (`stt`, `nlu`, `llm`, `tts`).
  - `providers`: Active provider names (`stt`, `tts`, `nlu`).

### Work Diary & Entries
- `GET /api/entries?date=YYYY-MM-DD` — Lists diary entries for a specific date (defaults to today in IST).
- `PATCH /api/entries/{id}` — Updates editable fields (`task_type`, `count`, `event_date`, `beneficiary_ref`, `notes`, `documents`). Re-validates constraints.
- `POST /api/entries/{id}/confirm` — Explicitly marks a draft entry as confirmed.
- `DELETE /api/entries/{id}` — Deletes an entry.

### Claims & Register Export
- `GET /api/claims/{yyyy-mm}` — Aggregates confirmed entries for the month, calculates sample incentive totals, flags missing documents, and generates register lines.
- `GET /api/claims/{yyyy-mm}/export` — Exports the monthly claim summary as a UTF-8 CSV with BOM for Excel compatibility.
- `GET /api/claims/{yyyy-mm}/print` — Generates a printable HTML report of the monthly register with demo disclaimer.

---

## How It Works

```mermaid
flowchart LR
    A["Voice or Text Input"] --> B["FastAPI Rate Limiter"]
    B --> C{"STT Adapter"}
    C -->|mock| D["Mock Transcript"]
    C -->|gnani| G["Gnani Prisma (503 if not configured)"]
    D --> E["Text Normaliser"]
    E --> F["NLU Extractor (Rules / OpenAI)"]
    F --> H["DialogueManager (Pure State Machine)"]
    H --> I{"Phase"}
    I -->|AWAITING_FIELD| J["Prompt for missing field"]
    I -->|AWAITING_CONFIRMATION| K["Readback summary (Initials only)"]
    I -->|Saved| L[("SQLite DB (Confirmed Entries)")]
    H --> M{"TTS Adapter"}
    M -->|browser| N["Browser Web Speech API"]
    M -->|gnani| O["Gnani Timbre (503 if not configured)"]
```

1. **Privacy-Preserving Beneficiary Reference**: Beneficiary names are reduced to initials (e.g. "Rina" becomes "R", "Mina Begum" becomes "MB") or short IDs (e.g. "ID 47"). Full patient names are never stored or logged.
2. **Ambiguous Date Handling**: Bengali terms *kal* and *porshu* refer to either past or future days depending on context. The system defaults to the past (yesterday / day before yesterday) and sets `date_ambiguous: true`, prompting the ASHA for clarification. Completed work is never silently recorded in the future.
3. **Dialogue State Machine**: Pure state machine with states `IDLE`, `AWAITING_CONFIRMATION`, and `AWAITING_FIELD`. Handles readback, corrections ("na, count 3"), repeat prompts on unintelligible speech, and fallback to typed input.
4. **Strict Clinical Refusal**: Medical advice queries (e.g., *"ki dose dibo"*, *"jor hole ki korbo"*) trigger an immediate standard refusal directing the worker to consult an ANM/MO-IC.

---

## Project Layout

```text
didinotes/
├── config/                     # Configuration files
│   ├── i18n.yaml               # User-facing strings (Bengali and English)
│   ├── incentives.yaml         # Sample task types and required documents
│   ├── lexicon.yaml            # Bengali/Benglish keywords (NEEDS NATIVE SPEAKER REVIEW)
│   └── prompts/
│       └── extract_entries.txt # Strict JSON prompt template for LLM extractor
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── app/
│   │   │   ├── dialogue/       # Pure state machine dialogue manager
│   │   │   ├── nlu/            # Text normalisation, dates, numbers, extraction, LLM
│   │   │   ├── speech/         # STT/TTS protocols, MockSTT, BrowserTTS, Gnani stubs
│   │   │   ├── claims.py       # Month-end claim calculation, CSV, HTML print logic
│   │   │   ├── factory.py      # App factory and DB startup migrations
│   │   │   ├── main.py         # Entrypoint for uvicorn
│   │   │   ├── repository.py   # SQLAlchemy database operations
│   │   │   ├── routes.py       # Health and task type endpoints
│   │   │   ├── settings.py     # Pydantic settings
│   │   │   └── turn.py         # POST /api/turn HTTP handler
│   │   ├── tests/              # 164 pytest automated tests
│   │   ├── pyproject.toml      # Ruff and pytest configuration
│   │   ├── requirements.txt    # Production Python dependencies
│   │   └── requirements-dev.txt# Development and test dependencies
│   └── web/                    # Next.js frontend (App Router, Tailwind)
│       ├── app/                # Pages: / (Talk), /diary, /claim
│       ├── components/         # TalkScreen, DiaryScreen, ClaimScreen, DevPanel
│       └── public/
├── eval/                       # Evaluation and benchmarking tools
│   ├── utterances.jsonl        # 60 curated evaluation test cases
│   ├── run_extraction_eval.py  # NLU extraction and dialogue benchmark
│   ├── add_noise.py            # NumPy-based SNR noise mixing utility
│   ├── run_stt_eval.py         # jiwer-based Word Error Rate evaluation tool
│   └── results/                # Timestamped JSON and Markdown benchmark reports
├── scripts/                    # Operational and smoke test scripts
│   ├── smoke.ps1               # PowerShell automated smoke test
│   └── smoke.sh                # Bash automated smoke test
├── PROGRESS.md                 # Project milestone completion log
├── ARCHITECTURE.md             # Pipeline architecture diagrams and design
├── DECISIONS.md                # Architecture Decision Records (ADRs)
├── CONTRIBUTION_LOG.md         # Template for personal work log
├── .env.example                # Sample environment configuration
└── .gitignore                  # Git ignore rules (audio, DBs, secrets, cache)
```

---

## Plugging in Gnani

Gnani Prisma (STT) and Timbre (TTS) integration stubs are isolated in `apps/api/app/speech/gnani.py`. To plug in real Gnani endpoints:

1. **Locate the adapter file**:
   Open [`apps/api/app/speech/gnani.py`](apps/api/app/speech/gnani.py).
   Currently, `GnaniPrismaSTT.transcribe()` and `GnaniTimbreTTS.speak()` raise `NotImplementedError` with explicit TODO markers.

2. **Configure environment variables in `.env`**:
   ```bash
   STT_PROVIDER=gnani
   TTS_PROVIDER=gnani
   GNANI_API_KEY=your_actual_gnani_api_key
   GNANI_BASE_URL=https://api.gnani.ai/v1
   ```

3. **Implement the HTTP calls in `apps/api/app/speech/gnani.py`**:
   - In `GnaniPrismaSTT.transcribe(audio_bytes, mime, lang_hint)`: Send audio bytes with `lang_hint="bn"` to the Gnani Prisma speech-to-text API and return a `Transcript(text=..., confidence=...)`.
   - In `GnaniTimbreTTS.speak(text, lang)`: Send text to the Gnani Timbre text-to-speech API and return a `Speech(audio_bytes=..., mime="audio/wav", use_browser_tts=False)`.
   - *Never guess API payloads or URLs; follow the official Gnani partner documentation.*

4. **Run the STT Word Error Rate evaluation tool**:
   Collect real test recordings in `eval/audio/` with sidecar reference transcript files (`.txt`), then run:
   ```powershell
   python eval/run_stt_eval.py --audio-dir eval/audio --adapter gnani
   ```
   This will report the mean Word Error Rate (WER) across clean and noisy audio levels.

---

## Testing Status

| Suite | Scope | Result |
|---|---|---|
| `pytest -q` | `apps/api/tests` (164 tests) | **164 passed**, 1 warning |
| `ruff check .` | `apps/api` and `eval/` | **All checks passed** |
| `npm run typecheck` | `apps/web` (TypeScript strict) | **0 errors** |
| `npm run build` | `apps/web` (Next.js 15 production build) | **Compiled successfully**, 4 routes generated |
| `run_extraction_eval.py` | 60 items in `eval/utterances.jsonl` | **100.0% exact match** (60/60) |
| `smoke.ps1` | End-to-end conversation & persistence | **PASSED** |

---

## Limitations and Not Verified

1. **Lexicon and Bengali Strings**: `config/lexicon.yaml` and `config/i18n.yaml` are initial developer drafts and **require native speaker review** for colloquial West Bengal ASHA terminology.
2. **Incentive Amounts**: Amounts in `config/incentives.yaml` are sample data only and marked `verified: false`. The system deliberately displays *"amount not configured"* on monthly claim summaries until verified.
3. **Rules-Based Extractor Phrasings**: The rules-based extractor is optimized for standard ASHA reporting phrasing and the 60 evaluation items. Highly varied syntax requires either the LLM fallback or continuous lexicon expansion.
4. **Real-World Speech Accuracy Untested**: No real ASHA speech recordings have been collected or committed. Accuracy with background field noise (traffic, clinics, rain) cannot be measured until real field recordings are conducted.
5. **Gnani Integration Not Implemented**: The Gnani Prisma and Timbre integration remains a stub raising `NotImplementedError` until valid partner API credentials and documentation are supplied.

