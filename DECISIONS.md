# Decisions

- Dates: `kal` and `porshu` are ambiguous. The parser defaults to the past (yesterday, or the day before yesterday) and sets `ambiguous=true` with both candidates. Completed work is never silently given a future date.
- Incentives: amounts stay null and `verified` stays false. The loader raises an error if an amount is set while unverified.
- Names: full names are reduced to initials in notes and `beneficiary_ref`. An `ID <n>` pattern takes precedence as the reference.
- Time zone: all date and time logic uses Asia/Kolkata. `tzdata` is a runtime dependency because Windows has no built-in IANA database.
- Timestamps: `created_at` is stored as naive IST wall-clock time, because SQLite has no timezone support.
- Extractor: rules-based only (`LLM_PROVIDER=rules`). Clauses are split on punctuation and conjunctions. Clinical keywords return a fixed refusal, not an answer.
- Lexicon: `config/lexicon.yaml` is a first draft and needs native speaker review.
- Gnani: `docs.gnani.ai` returned HTTP 403, so the API format is unknown. `GnaniPrismaSTT` and `GnaniTimbreTTS` are stubs that raise `NotImplementedError` with a TODO. Nothing is guessed. The turn endpoint returns 503 when a Gnani provider is selected.
- Dialogue: `handle()` is pure. It takes the session state and returns a reply, the new state, and the entries. It persists nothing. `/api/turn` saves entries only on a confirmed "yes".
- Confidence gate: a field below its threshold is left empty and asked again, so low-confidence entries are never saved without confirmation.
- Sessions: an in-memory store with a TTL (`SESSION_TTL_SECONDS`, default 900). Restarting the server clears sessions.
- Rate limit: in-memory, per client IP, `RATE_LIMIT_PER_MINUTE` (default 30).
- Audio: the mock STT reads text from the request. Uploaded audio is held in memory only and is never written to disk, so there is nothing to delete unless `STORE_AUDIO=true` (not implemented, since no storage path is needed yet).
- Extractor fix: a bare count clause such as "2 jon" after a task clause now sets the previous entry's count, instead of creating an `other` entry.
