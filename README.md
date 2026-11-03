# DidiNotes

> A voice-first work diary for ASHA community health workers in Bengali, Benglish and English.

Demo application. Do not enter real patient data.

---

## Problem

Accredited Social Health Activist (ASHA) community health workers in West Bengal deliver vital maternal, newborn, and immunization care across rural villages. Today, ASHAs record their daily field visits by hand into multiple paper registers. 

Because paperwork is done on the move or late at night, records frequently get lost, damaged, or submitted late at the end of the month. This delays government incentive claims and deprives health workers of timely pay for their service.

---

## Solution

**DidiNotes** (internally "ASHA Diary") replaces paper note-taking with an intelligent voice assistant:
1. **Speak the Day**: The ASHA speaks naturally in colloquial Bengali or code-mixed Benglish (e.g. *"aaj ekta ANC ar duijon-ke vaccination dilam"*).
2. **Instant Extraction**: The app transcribes the speech and extracts structured work entries: task type, count, date, and beneficiary reference.
3. **Follow-Up Clarification**: If any vital field is missing, the app asks targeted, conversational follow-up questions.
4. **Read-Back Confirmation**: The assistant reads the complete entry back in natural Bengali and asks for confirmation.
5. **Saved Only After YES**: Work entries are committed to the database **only after explicit confirmation** (saying or clicking YES / হ্যাঁ / haan).

---

## Features

- **Voice & Typed Entry**: Large hold-to-talk microphone button with a 29-second auto-stop guard and an immediate text input fallback for noisy environments.
- **Interactive Follow-Up Questions**: Prompts only for missing fields (count, date, or task) one at a time.
- **Read-Back with YES / NO / EDIT**: Interactive confirmation cards with **YES (হ্যাঁ)**, **NO (না)**, and **EDIT (সম্পাদনা)** controls, accepting voice or touch input.
- **Code-Mixed Speech Understanding**: Recognizes Bengali script, Romanised Benglish, and English loanwords with Bengali grammatical case suffixes (e.g. *vaccination-ke*, *ANC-এর*, *delivery-র*, *checkup*, *home visit*).
- **Multi-Task Sentence Splitting**: Automatically splits compound sentences containing multiple tasks (conjunctions like *ar*, *ebong*, *o*, *and*, *tarpor*, punctuation, or weak particle *এর* between distinct tasks), assigning each count to its respective task and sharing dates across clauses.
- **Audio Noise Checks & "I Heard" Line**:
  - Web Audio API measures recording client-side: rejects recordings under 0.5 seconds or near-silent audio, and warns if audio is clipped, saving API credits.
  - Microphone capture uses hardware noise suppression, echo cancellation, and auto-gain control.
  - Client displays a transparent *"আমি শুনেছি / I heard: <transcript>"* banner under each assistant response and in the Dev Panel.
- **Visit Checklists with Danger-Sign Banner**:
  - After confirming an Antenatal (ANC) or Newborn Home Visit (HBNC), offers a step-by-step checklist.
  - Evaluates danger signs (e.g. bleeding, severe headache, baby temperature/weight, convulsions) and triggers a prominent warning banner: *"ANM বা ডাক্তারকে জানান / Please inform your ANM or doctor"*.
- **Work Diary**: Daily list view of entries with inline editing and deletion capabilities.
- **Monthly Claim Sheet**: Aggregates verified work lines for the month, calculates sample incentive totals, flags missing documentation, exports to Excel-compatible UTF-8 CSV with BOM, and provides a print-ready register view.
- **Bilingual Interface**: Quick toggle between Bengali (বাংলা) and English (EN) for all interface text and spoken dialogue.

---

## Gnani Speech Models

DidiNotes integrates with [Gnani.ai](https://docs.gnani.ai) speech services for high-accuracy Indic language processing:

| Service | Model | Endpoint | Purpose |
|---|---|---|---|
| **Speech-to-Text (STT)** | **Prisma** (`prisma-v2.5` / `prisma-v3.0`) | `POST https://api.vachana.ai/stt/v3` | Transcribes spoken Bengali and Benglish audio (`bn-IN`). Pre-validates audio format (rejects WebM) and ensures duration < 30 seconds before sending. |
| **Text-to-Speech (TTS)** | **Timbre** (`timbre-v3.0`, voice *Shivani*) | `POST https://api.vachana.ai/api/v1/tts/inference` | Synthesizes spoken Bengali responses. Uses `number_to_spoken_bn()` to convert bare numbers and dates to spoken Bengali words for natural inflection. Local SHA-256 disk caching prevents redundant API calls. |

---

## Architecture Summary

DidiNotes follows a decoupled, privacy-first architecture:

- **Client (`apps/web`)**: Next.js 15 (App Router, React 19, TypeScript strict, Tailwind CSS). Records raw audio, downsamples to 16 kHz Mono, and encodes directly into 16-bit linear PCM WAV (`apps/web/lib/wav.ts`) using the Web Audio API without third-party dependencies.
- **Backend API (`apps/api`)**: FastAPI service with Pydantic v2 validation and SQLAlchemy SQLite persistence (`asha_diary.db`).
- **NLU & Dialogue State Machine**:
  - `apps/api/app/nlu`: Deterministic tokenizers, date parsers, number extractors, and clause splitters.
  - `apps/api/app/dialogue/manager.py`: Pure state machine managing `IDLE`, `AWAITING_FIELD`, `AWAITING_CONFIRMATION`, `OFFERING_CHECKLIST`, and `IN_CHECKLIST` phases.
- **Speech Adapters (`apps/api/app/speech`)**: Abstract `SpeechToText` and `TextToSpeech` providers. Seamlessly swaps between Gnani production models and zero-dependency local mocks (`MockSTT` and browser SpeechSynthesis).

For full architectural diagrams and deep-dive design documentation, see [ARCHITECTURE.md](file:///c:/Users/pc/Desktop/didinotes/ARCHITECTURE.md).

---

## How to Run

### 1. Environment Configuration

Copy the example environment configuration:
```bash
cp .env.example .env
```

> [!NOTE]
> **Zero Keys Required for Development**: No API keys are committed to the repository. If `GNANI_API_KEY` is not provided, DidiNotes runs out-of-the-box using built-in mock STT and browser Web Speech synthesis (`STT_PROVIDER=mock`, `TTS_PROVIDER=browser`).

To enable real Gnani models, add your key to `.env`:
```env
STT_PROVIDER=gnani
TTS_PROVIDER=gnani
GNANI_API_KEY=your_actual_gnani_api_key
```

### 2. Backend Setup (FastAPI)

From the repository root:
```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
The API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 3. Frontend Setup (Next.js)

In a separate terminal:
```powershell
cd apps/web
cmd /c npm install
cmd /c npm run dev
```

> [!IMPORTANT]
> **Use Localhost Only**: Always access the web interface at **[http://localhost:3000](http://localhost:3000)**. Modern web browsers strictly block microphone access (`navigator.mediaDevices.getUserMedia`) over plain HTTP unless the hostname is `localhost` or `127.0.0.1`.

---

## Automated Test Suite

All tests pass cleanly in automated validation:

| Test Command | Scope | Real Result |
|---|---|---|
| `cd apps/api; .venv/Scripts/python -m pytest` | Backend test suite (`apps/api/tests`) | **284 passed**, 1 warning |
| `apps/api/.venv/Scripts/ruff check apps/api` | Backend linter and code quality | **All checks passed!** |
| `cd apps/web; npm run typecheck` | Frontend TypeScript type check (`tsc --noEmit`) | **0 errors** (clean) |
| `cd apps/web; npm test` | Audio WAV encoder, resampler & quality check suite | **All 5/5 checks passed!** |
| `cd apps/web; npm run build` | Next.js production build & static generation | **Compiled successfully** (4 routes generated) |

---

## Safety and Privacy

- **Demo Banner**: A persistent banner (*"Demo. Do not enter real patient data" / "ডেমো সংস্করণ। কোনো আসল রোগীর তথ্য দেবেন না।"*) is displayed on every screen, export, and API response.
- **No Real Patient Data**: Beneficiary names are never stored or logged in full. Names are reduced to initials (e.g. "Rina Begum" $\to$ "RB") or arbitrary beneficiary IDs (e.g. "ID 104").
- **Strict Clinical Refusal**: DidiNotes is strictly a record-keeping diary and **never provides medical advice, diagnosis, or triage**. Any clinical inquiry (e.g. *"ei rogir ki dose dibo?"*, *"jor hole ki oshudh khabo?"*) triggers an immediate clinical refusal advising the worker to consult an ANM, Medical Officer, or doctor.
- **Zero Audio Storage**: Audio files are processed strictly in-memory during the conversational turn and are **never written to disk or persisted**.
- **No Server-Side Audio or Transcript Logging**: Server logs record only sanitized operational telemetry (`request_id`, status code, latency). Raw audio, transcripts, and API credentials are never logged.
