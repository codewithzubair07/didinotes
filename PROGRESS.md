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
- `README.md` is still not written, so the manual test script lives here for now.
- Required documents in `config/incentives.yaml` are placeholders.
