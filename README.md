# DidiNotes

A voice-first work diary for ASHA community health workers in West Bengal, India.
She speaks her day in Bengali or Benglish (Bengali mixed with English). The app
transcribes it, extracts structured work entries, reads them back for confirmation,
handles corrections, saves them, and produces register-ready lines and a month-end
incentive claim sheet.

It is a record-keeping tool. It never gives medical advice.

> **Demo. Do not enter real patient data.** Use synthetic data only.

## Status

Work in progress. Speech goes through swappable adapters. The app runs end to end
with no API keys (mock speech-to-text, browser text-to-speech). The Gnani Prisma
(STT) and Timbre (TTS) integration is **not implemented yet**; see "Plugging in Gnani".

## Quick start

Backend (Windows):

    cd apps/api
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements-dev.txt
    pytest -q
    ruff check .
    uvicorn app.main:app --port 8000

On macOS or Linux, activate with `source .venv/bin/activate`.

Frontend:

    cd apps/web
    npm install
    npm run typecheck
    npm run build
    npm run dev

## Configuration

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Purpose |
|---|---|
| LLM_PROVIDER | `rules` (default) or `openai` (needs OPENAI_API_KEY; falls back to rules if missing) |
| STT_PROVIDER / TTS_PROVIDER | Speech providers (mock and browser by default) |
| STORE_AUDIO | Currently not implemented; audio is never written to disk |
| GNANI_API_KEY / GNANI_BASE_URL | For the Gnani integration, once implemented |
| TZ | Asia/Kolkata |

## API

- `GET /api/health`, `GET /api/config/task-types`
- `POST /api/turn` (JSON text or multipart audio): one conversation turn
- `GET /api/entries?date=`, `PATCH /api/entries/{id}`, `POST /api/entries/{id}/confirm`, `DELETE /api/entries/{id}`
- `GET /api/claims/{yyyy-mm}`, `/export` (CSV), `/print` (HTML)

## How it works

Audio or text goes through speech-to-text, then text normalisation, then a dialogue
manager (read back, one follow-up question at a time, corrections), then
text-to-speech. Entries are saved only after she confirms. The date words "kal" and
"porshu" are ambiguous in Bengali (past or future), so the app asks explicitly.
See `ARCHITECTURE.md` for the turn pipeline and `DECISIONS.md` for design choices.

## Project layout

    apps/api   FastAPI backend (nlu, dialogue, speech adapters, claims)
    apps/web   Next.js frontend (talk, diary, claim screens)
    config     task types and incentives, lexicon, UI strings, prompts
    eval       evaluation data and scripts

## Plugging in Gnani

All Gnani calls belong in `apps/api/app/speech/gnani.py`, which currently holds stubs
that raise `NotImplementedError`. To finish:

1. Get an API key and read the Prisma and Timbre documentation.
2. Implement `GnaniPrismaSTT` and `GnaniTimbreTTS` in that file.
3. Set `GNANI_API_KEY`, `GNANI_BASE_URL` and the provider variables in `.env`.
4. Run the tests and the speech evaluation on noisy Bengali audio.

## Testing

Last recorded run: 146 backend tests passing, `ruff` clean, frontend type-check
clean, production build passing. The browser UI (microphone, speech playback) has
not been clicked through by hand.

## Limitations and not verified

- The Bengali lexicon and UI strings are first drafts and need native speaker review.
- Incentive categories, required documents and amounts in `config/incentives.yaml`
  are sample placeholders. Verify them against the official state circular and with a
  working ASHA before any real use. Amounts are null, so claims show "amount not configured".
- The extractor is rules-based and covers the sample phrasings in the tests.
- Real-world speech accuracy is untested.
- No licence has been chosen yet.
