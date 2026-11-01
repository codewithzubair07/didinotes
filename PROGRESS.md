# ASHA Diary Progress

Demo. Do not enter real patient data.

## Milestone 1: done

- Repo skeleton: `apps/api`, `config`, `.gitignore`, `.env.example`.
- Settings via pydantic-settings (`apps/api/app/settings.py`).
- SQLAlchemy `Entry` model and repository (create, get, list by date, update, confirm, delete).
- `config/incentives.yaml` with 6 sample task types. Loader rejects any amount set while `verified` is false.
- `config/lexicon.yaml` (marked NEEDS NATIVE SPEAKER REVIEW).
- Text normaliser, number parsing, date parsing with kal and porshu ambiguity, rules-based extractor.
- Endpoints: `GET /api/health`, `GET /api/config/task-types`.

## How to run

```
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
uvicorn app.main:app --port 8000
```

## Milestone 2: done

- `DialogueManager` (`apps/api/app/dialogue/manager.py`): states IDLE, AWAITING_CONFIRMATION, AWAITING_FIELD. Covers readback, one follow-up at a time, kal/porshu ambiguity, yes/no, corrections, repeat then type fallback, clinical refusal.
- All response strings live in `config/i18n.yaml` (Bengali and English).
- Speech: `SpeechToText` and `TextToSpeech` protocols. `MockSTT` and `BrowserTTS` work with no keys. `app/speech/gnani.py` holds stubs that raise `NotImplementedError`.
- `POST /api/turn` (`apps/api/app/turn.py`): JSON text or multipart audio. Size, duration, and MIME limits. Rate limit. In-memory session store with TTL. Persists entries on a confirmed yes. Returns transcript, entries, response text, base64 audio or null, ui hint, timings, and provider names.
- Architecture diagram of the turn pipeline in `ARCHITECTURE.md`.

## How to run

```
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
uvicorn app.main:app --port 8000
```

## Milestone 3: done

- Entry endpoints (`apps/api/app/entry_routes.py`): `GET /api/entries?date=`, `PATCH /api/entries/{id}`, `POST /api/entries/{id}/confirm`, `DELETE /api/entries/{id}`. Entries have a nullable `documents` JSON column.
- Claim logic (`apps/api/app/claims.py`): confirmed entries only, amounts only where configured, otherwise "amount not configured". Missing-document flags, attention list, register lines, CSV export and print HTML.
- Endpoints: `GET /api/claims/{yyyy-mm}`, `/export` (CSV), `/print` (HTML).
- Frontend (`apps/web`, Next.js App Router, TypeScript strict, Tailwind): talk screen (hold-to-talk, typed fallback, YES/NO/EDIT readback, today's entries, browser TTS fallback, dev panel behind `NEXT_PUBLIC_DEV_PANEL`), diary screen (edit and delete with confirmation), claim screen (table, attention list, CSV, print, copy register lines). Bengali default with English toggle. Demo banner on every screen.
- Existing SQLite databases gain the `documents` column on startup.

## How to run

```
cd apps/api
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
uvicorn app.main:app --port 8000

cd apps/web
npm install
npm run typecheck
npm run build
npm run dev
```

## Test status

- `pytest -q` in `apps/api`: 146 passed (includes 31 claim and entry tests and an old-schema migration test).
- `ruff check .`: all checks passed.
- `npm run typecheck`: zero errors.
- `npm run build`: compiled, 4 routes generated.

## Manual test script

1. Open the talk screen. The demo banner shows at the top.
2. Type "aaj Rina ANC visit korlam" and send. The reply asks how many.
3. Type "2 jon" and send. The readback card shows YES, NO and EDIT.
4. Press YES. The reply says saved, and the entry appears under today's work as confirmed.
5. Open the diary screen. Edit the entry count to 3 and save. Status becomes confirmed again.
6. Open the claim screen for the current month. The entry appears in the table and register lines.
7. Press Download CSV. The file has the header row and the entry.
8. Press Print page. The page shows the demo banner and register lines.

Verified against the running API with curl-equivalent calls: steps 2 to 4 (`ask_field`, `confirm`, `saved`), the clinical refusal, step 5 (PATCH to 200, and a future date rejected with 422), steps 6 to 8 (claim, CSV header, print banner). Browser UI interaction (mic, speech, clicks) was not exercised by hand, only builds and type-check.

## Known issues

- The browser UI was not clicked through by hand. Verification is the type-check, the production build, and API calls. Mic capture and browser TTS are unverified.
- Gnani STT and TTS are not implemented. Selecting a Gnani provider returns 503.
- Lexicon and Bengali strings are first drafts and need native speaker review.
- Incentive amounts are null and unverified, so the claim shows "amount not configured".
- Extractor is rules-based and covers the sample phrasings in the tests.
- `STORE_AUDIO=true` is not implemented. Audio is never written to disk.
- Required documents in `config/incentives.yaml` are placeholders.

## Milestone 4: done

### What was done
- **Evaluation data check (`eval/utterances.jsonl`)**: Verified dataset contains exactly 60 items with required mix: 20 simple single-entry, 10 multi-entry, 8 correction dialogues, 6 kal/porshu date traps, 6 number-word/Bengali-digit cases, and 10 clinical questions. Verified mix of Bengali script and romanised text. Format and count are correct.
- **Extraction evaluation tool (`eval/run_extraction_eval.py`)**: Implemented tool that runs all 60 items through the real extractor and dialogue manager. Reports per-field accuracy, overall exact-match rate, clinical refusal rate, and detailed failures. Automatically saves timestamped reports in `eval/results/` as JSON and Markdown.
  - Overall Exact Match Rate: **60/60 (100.0%)**
  - Clinical Refusal Rate: **10/10 (100.0%)**
  - Per-field accuracy (on 63 expected entries):
    - `task_type`: 63/63 (100.0%)
    - `count`: 63/63 (100.0%)
    - `date`: 63/63 (100.0%)
    - `beneficiary_ref`: 63/63 (100.0%)
  - Failures: 0.
- **Noise mixing tool (`eval/add_noise.py`)**: Implemented SNR noise mixing tool using standard library `wave` and `numpy` only. Accurately scales noise power to target SNR in dB and handles length mismatch and clipping.
- **STT evaluation tool (`eval/run_stt_eval.py`)**: Implemented Word Error Rate evaluation tool using `jiwer`. Computes WER per noise level and supports sidecar `.txt` transcripts and manifest files. Added `jiwer>=3.0,<4` to `apps/api/requirements-dev.txt`.
- **Git configuration**: Added `eval/audio/` to `.gitignore` to prevent any audio recordings from being committed.
- **Speech evaluation verification**: Generated synthetic test WAV and sidecar transcript, verified `eval/add_noise.py` at 10 dB SNR, and verified `eval/run_stt_eval.py` with MockSTT (0.0% WER). Explicitly labeled as *"tooling check only, NOT a real speech-accuracy result"*.
- **LLM extractor comparison**: Confirmed all requirements in `apps/api/app/nlu/llm.py` and `apps/api/tests/test_llm.py`: temperature 0, strict JSON schema validation, fallback to rules on failure/timeout/invalid JSON, logged reason without raw transcripts or personal data, and provider plus latency in `/api/turn` timings. No LLM key is configured in the environment, so the LLM evaluation comparison was **not run**.
- **Automated Smoke Scripts**: Created `scripts/smoke.sh` and `scripts/smoke.ps1`. Ran `scripts/smoke.ps1` on Windows; verified end-to-end conversation via `POST /api/turn` (report, ask count, confirm), persistence via `GET /api/entries`, and clean server shutdown.
- **Documentation**:
  - Created `README.md` covering architecture, configuration, quick start, API reference, Gnani integration steps, and limitations.
  - Created `CONTRIBUTION_LOG.md` with blank template sections for user.
  - Updated `DECISIONS.md` with all architectural and implementation decisions from this session.
- **Cleanup check**: Inspected root-level `main.py` (0 bytes, unused leftover; proposed for deletion). Confirmed build artifacts like `tsconfig.tsbuildinfo` are ignored and not tracked.

### What is NOT done / unverified
- Gnani Prisma STT and Timbre TTS: remain stubs with `NotImplementedError` until Gnani documentation and credentials are provided.
- Real-world speech accuracy under field noise: unverified pending collection of real field audio.
- LLM extractor evaluation comparison: not run because no `OPENAI_API_KEY` was present in the environment.
- Native speaker review of `config/lexicon.yaml` and `config/i18n.yaml`.
- Incentive verification: amounts remain unverified sample data in `config/incentives.yaml`.
- Real browser audio recording and TTS: verified via automated tests, API calls, and smoke scripts, but not manually exercised with a microphone in a browser.

### Test results
- `apps/api`: `pytest -q` -> 164 passed, 1 warning (StarletteDeprecationWarning) in 5.20s.
- `apps/api`: `ruff check .` -> All checks passed!
- `eval/`: `ruff check eval/run_extraction_eval.py eval/add_noise.py eval/run_stt_eval.py` -> All checks passed!
- `apps/web`: `npm run typecheck` -> 0 errors.
- `apps/web`: `npm run build` -> Compiled successfully, 4 routes generated.
- `scripts/smoke.ps1` -> PASSED.


## Milestone 4 - Session A: Gnani STT and TTS Backend Adapters (done)

### What was done
- **A1. Baseline audit**: Audited how speech adapters are invoked from `turn.py`, audio limits (2 MB, 60s, MIME restrictions), and audited `Transcript.confidence` usage. Allowed `confidence: float | None = None` on `Transcript` because Gnani Prisma returns no confidence score (NLU extraction confidence is computed independently).
- **A2. Settings and startup validation**: Added comprehensive Gnani settings to `Settings` (`apps/api/app/settings.py`) and `.env.example`. Added startup check `validate_startup_settings()` in `app/main.py` failing with a clear message if Gnani provider is chosen with an empty key. Added `.cache/` to `.gitignore`.
- **A3. Bengali spoken numbers (`apps/api/app/speech/spoken_bn.py`)**: Implemented `number_to_spoken_bn()` converting digits (0-100, years, ordinals/calendar days, currency) into spoken Bengali words to ensure natural pronunciation by Timbre TTS. Marked subtle colloquial forms with `# NEEDS NATIVE SPEAKER REVIEW`.
- **A4. Gnani Prisma STT adapter (`apps/api/app/speech/gnani.py: GnaniPrismaSTT`)**:
  - Implements `SpeechToText` protocol with `POST https://api.vachana.ai/stt/v3`.
  - Enforces pre-send checks: rejects WebM format (HTTP 415) and duration > 30s (HTTP 413) before sending HTTP requests.
  - Concurrency control via `threading.Semaphore(GNANI_MAX_CONCURRENCY)`.
  - Retries 429 and 5xx up to 2 times with exponential backoff (0.5s, 1.0s); fails fast on client errors (400, 401, 402, 403, 422).
  - Handles `truncated=true` as `GnaniAudioError`.
  - Strict privacy-safe logging: logs only `request_id`, `model`, `latency_ms`, and `status`. Never logs audio bytes, transcripts, or keys.
- **A5. Gnani Timbre TTS adapter (`apps/api/app/speech/gnani.py: GnaniTimbreTTS`)**:
  - Implements `TextToSpeech` protocol with `POST https://api.vachana.ai/api/v1/tts/inference`.
  - Preprocesses text using `number_to_spoken_bn()` when enabled.
  - Deterministic disk caching using SHA-256 hashes stored in `.cache/tts/`.
  - Graceful fallback: on failure or network error, falls back to client browser TTS with `tts_fallback=True` without failing the turn.
- **A6. Wiring into `/api/turn` & `providers.py`**:
  - Updated `providers.get_stt` and `get_tts` to instantiate Gnani adapters with runtime settings.
  - Updated `/api/turn` error handling to return bilingual error messages (401, 402, 413, 415, 429, 502, 504).
  - Exposes `tts_fallback` flag and detailed provider info in `/api/turn` response payload.
- **A7. Unit tests (`apps/api/tests/test_gnani.py`)**:
  - 23 comprehensive tests using `httpx.MockTransport` covering STT valid response, empty transcript, truncation, auth errors, quota exhaustion, 429 retries, timeout, pre-send format and duration validation, TTS synthesis, disk caching, number conversion, browser TTS fallback, and caplog privacy verification.
- **A8. Developer utility scripts**:
  - `scripts/gnani_live_check.py`: Opt-in live check script requiring `--yes` to run 1 live TTS call and 1 live STT call round-trip. Exits safely with warning otherwise.
  - `scripts/tts_voice_samples.py`: Opt-in voice sample script requiring `--yes` to synthesize samples in 6 voices (`Shivani`, `Riyaa`, `Kalpana`, `Chetana`, `Devansh`, `Harshad`) into `eval/audio/voices/`. Exits safely with warning otherwise.
- **A9. Documentation**: Updated `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `PROGRESS.md`.

### Test results
- `apps/api`: `pytest -q` -> **187 passed**, 1 warning in 15.01s.
- `apps/api`: `ruff check .` -> All checks passed!
- `scripts/`: `ruff check scripts/gnani_live_check.py scripts/tts_voice_samples.py` -> All checks passed!
- `apps/web`: `npm run typecheck` -> 0 errors.
- `apps/web`: `npm run build` -> Compiled successfully, 4 routes generated.


## Milestone 5: Browser Recording, Dev Panel & Real-Speech Evaluation (done)

### What was done
- **B1. Browser Audio Recording & WAV Encoding**:
  - Implemented `apps/web/lib/wav.ts` providing client-side 16 kHz Mono 16-bit PCM WAV encoding and resampling via Web Audio `OfflineAudioContext` / `AudioContext` without third-party dependencies.
  - Uploads audio as `recording.wav` with MIME `audio/wav`.
  - Added visible recording timer with automatic auto-stop at 29 seconds to prevent Gnani 30-second rejection.
  - Added backend support for `audio/wave` in `ALLOWED_MIMES` and `SUPPORTED_STT_MIMES`.
  - Added friendly bilingual alerts for mic permission denied, recording too long, rate limit busy (429), quota exhausted (402), and speech service errors.
  - Handled browser audio autoplay restrictions by detecting promise rejection in `playBase64Audio()` and surfacing a prominent "Tap to hear" (🔊 শুনতে চাপুন) button.
  - Created native Node.js test script `apps/web/scripts/check-wav.mjs` (runnable via `npm run test:wav`) verifying RIFF header, length, 16-bit clamping, and resampling ratios without adding testing framework dependencies.
- **B2. Dev Panel Telemetry**:
  - Enhanced `POST /api/turn` with a `dev` telemetry payload exposing STT model, STT format, STT request ID, TTS model, TTS voice, TTS latency, TTS cache hit status, TTS request ID, and TTS fallback reason.
  - Rendered comprehensive telemetry in `apps/web/app/page.tsx` when `NEXT_PUBLIC_DEV_PANEL=true`.
- **B3. Manual Browser Test Script**:
  - Added a 10-step manual browser test script in `README.md` covering mic permissions, hold-to-talk, 29s auto-stop, typed input fallback, interactive readback, voice correction, diary editing, monthly claim sheets, CSV export, and print preview.
- **B4. STT Evaluation Tool Upgrade (`eval/run_stt_eval.py`)**:
  - Upgraded to read `eval/audio/manifest.jsonl`.
  - Added `--configs` support (`eval/stt_configs.json`) running 7 candidate STT configurations sequentially (never parallel).
  - Reports WER and CER via `jiwer`, median and 95th percentile latencies, empty transcript count, and error counts.
  - Implemented unified text normalization: Unicode NFC, Bengali digits to ASCII (০-৯ -> 0-9), punctuation/Dari ('।') removal, lowercasing, and whitespace collapse.
  - Added `--dry-run` and `--max-calls` safety guards, with automatic early stopping on consecutive 402/429 errors.
  - Labeled all outputs with timestamp, clip count, and `"small sample, indicative only"`.
- **B5. End-to-End Evaluation Pipeline (`eval/run_e2e_eval.py`)**:
  - Implemented pipeline: Audio -> STT -> Extractor vs Expected Entries, reporting field accuracy (`task_type`, `count`, `date`, `beneficiary_ref`) next to the text-only baseline and WER.
  - Added automated Punctuation Sensitivity Test: verified that rules extractor behaves with 100% identity (0 discrepancies) on sample sentences with or without trailing Bengali Dari '।' or ASCII period '.'.
  - Documented proposed lexicon and extractor improvements for user review without modifying existing extraction logic.
- **B6. Noise Dataset Augmentation (`eval/make_noisy_set.py`)**:
  - Created utility to generate 20 dB, 10 dB, and 5 dB SNR audio variants from clean clips and user-supplied background noise into `eval/audio/noisy/` and extend `eval/audio/manifest.jsonl`.
  - Verified `eval/audio/` and audio files are ignored in `.gitignore`.
- **B7. Dataset Collection & Recording Guide (`docs/RECORDING_GUIDE.md`)**:
  - Authored a comprehensive field recording guide covering privacy governance, informed consent, synthetic patient references, 50/50 quiet vs noise mix, Bengali/Benglish phrasing, manifest formatting with examples, and execution workflows.
- **B8. Documentation Updates**:
  - Updated `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `PROGRESS.md`.

### What is NOT done / unverified
- Browser microphone hardware capture and audio playback remain unverified until the 10-step manual browser test script is executed by the user.
- Real field speech audio has not been recorded or committed. Speech accuracy figures under real rural background noise remain unmeasured until real recordings are collected per `docs/RECORDING_GUIDE.md`.
- Native speaker review of `config/lexicon.yaml` and `config/i18n.yaml` by local health workers in West Bengal remains pending.
- Incentive amounts in `config/incentives.yaml` remain unverified sample data.

### Test results
- `apps/api`: `pytest -q` -> **190 passed** in 17.93s.
- `apps/api`: `ruff check .` -> All checks passed!
- `eval/`: `ruff check eval/` -> All checks passed!
- `apps/web`: `node scripts/check-wav.mjs` -> All WAV encoder and resampler checks passed.
- `apps/web`: `npm run typecheck` -> 0 errors.
- `apps/web`: `npm run build` -> Compiled successfully, 4 routes generated.

