import re
from datetime import date
from functools import lru_cache

from pydantic import BaseModel, Field

from app.config_loader import Lexicon, default_lexicon, default_task_types
from app.nlu.dates import DateParse, parse_date
from app.nlu.numbers import CLASSIFIER_SUFFIXES, EXTRA_NUMBER_WORDS, parse_number
from app.nlu.text import BENGALI_DIGITS, CASE_SUFFIXES, contains_phrase, normalise, tokenize

CLINICAL_REFUSAL = (
    "I cannot answer clinical questions. Please ask your ANM or doctor. "
    "এই বিষয়ে আমি পরামর্শ দিতে পারি না। অনুগ্রহ করে আপনার ANM বা ডাক্তারের সাথে কথা বলুন।"
)

PUNCT_SPLIT = r"(?:(?<!\d)\.(?!\d)|[,;।!?])+"
CONJUNCTIONS = r"(?:ar|aar|ebong|and|tarpor|o|আর|এবং|তারপর|ও)"
CLAUSE_SPLIT = re.compile(
    rf"{PUNCT_SPLIT}(?:\s*{CONJUNCTIONS}(?=\s|{PUNCT_SPLIT}|$))*|\s+(?:{CONJUNCTIONS}(?:\s+|$))+",
    re.IGNORECASE,
)
ID_PATTERN = re.compile(r"\bID[\s:#-]*([A-Za-z0-9]{1,16})\b", re.IGNORECASE)
NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


class ExtractedEntry(BaseModel):
    task_type: str
    count: int
    event_date: date
    beneficiary_ref: str | None = None
    notes: str
    field_confidence: dict[str, float] = Field(default_factory=dict)
    confidence: float
    date_ambiguous: bool = False
    date_candidates: list[date] = Field(default_factory=list)


class Extraction(BaseModel):
    entries: list[ExtractedEntry] = Field(default_factory=list)
    clinical_refusal: str | None = None


def _match_task(normalised: str, lexicon: Lexicon) -> str | None:
    for task_id, keywords in lexicon.task_keywords.items():
        if any(contains_phrase(normalised, keyword) for keyword in keywords):
            return task_id
    for task in default_task_types():
        if any(contains_phrase(normalised, label) for label in (task.bn_label, task.en_label)):
            return task.id
    return None


def find_matched_keywords(normalised: str, lexicon: Lexicon | None = None) -> list[str]:
    lexicon = lexicon or default_lexicon()
    matched = []
    for keywords in lexicon.task_keywords.values():
        for keyword in keywords:
            if contains_phrase(normalised, keyword) and keyword not in matched:
                matched.append(keyword)
    for task in default_task_types():
        for label in (task.bn_label, task.en_label):
            if contains_phrase(normalised, label) and label not in matched:
                matched.append(label)
    return matched


def _lexicon_words(lexicon: Lexicon) -> set[str]:
    words = set(lexicon.non_name_words)
    for keywords in lexicon.task_keywords.values():
        words.update(keywords)
    for values in lexicon.number_words.values():
        words.update(values)
    for values in lexicon.date_words.model_dump().values():
        words.update(values)
    words.update(lexicon.yes_words + lexicon.no_words + lexicon.correction_words)
    return {normalise(word) for word in words}


def _beneficiary(clause: str, lexicon_words: set[str]) -> tuple[str | None, float, str]:
    """Return (ref, confidence, clause with full names replaced by initials)."""
    initials_ref: str | None = None

    def replace(match: re.Match[str]) -> str:
        nonlocal initials_ref
        kept = [w for w in match.group().split() if w.lower() not in lexicon_words]
        if not kept:
            return match.group()
        initials = "".join(w[0].upper() for w in kept)
        if initials_ref is None:
            initials_ref = initials
        return initials

    notes = NAME_PATTERN.sub(replace, clause)
    id_match = ID_PATTERN.search(clause)
    if id_match:
        return id_match.group(1).upper(), 0.95, notes
    if initials_ref is None:
        return None, 0.0, notes
    return initials_ref, 0.8, notes


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=32)
def _compile_phrase_pattern(phrases_tuple: tuple[str, ...]) -> re.Pattern[str] | None:
    if not phrases_tuple:
        return None
    patterns: list[str] = []
    for p in phrases_tuple:
        words = p.split()
        if not words:
            continue
        pat = (
            r"\s+".join(re.escape(w) for w in words[:-1])
            + (r"\s+" if len(words) > 1 else "")
            + re.escape(words[-1])
            + r"(?:-[a-zA-Z\u0980-\u09ff]+|[a-zA-Z\u0980-\u09ff]+)?"
        )
        patterns.append(pat)
    if not patterns:
        return None
    return re.compile(rf"(?<!\S)(?:{'|'.join(patterns)})(?!\S)", re.IGNORECASE)


def _get_multi_word_phrases(lexicon: Lexicon) -> tuple[str, ...]:
    phrases: list[str] = []
    for kws in lexicon.task_keywords.values():
        phrases.extend(kws)
    for t in default_task_types():
        phrases.extend([t.bn_label, t.en_label])
    phrases.extend(lexicon.clinical_keywords)
    multi = [p.strip() for p in phrases if len(p.strip().split()) > 1]
    multi.sort(key=len, reverse=True)
    return tuple(multi)


_TASK_PATTERNS_CACHE: dict[int, list[tuple[re.Pattern[str], str, str]]] = {}
_NUMBER_RE_CACHE: dict[int, re.Pattern[str]] = {}

PARTICLES_RE = re.compile(
    r"^(?:\s*[-–—]?(?:এর|er|ke|কে|ও|o|r|র|te|তে|ar|aar|আর|ebong|এবং|and|tarpor|তারপর)(?=$|[^\u0980-\u09ff\w]))+",
    re.IGNORECASE,
)


def _get_task_patterns(lexicon: Lexicon) -> list[tuple[re.Pattern[str], str, str]]:
    key = id(lexicon)
    if key not in _TASK_PATTERNS_CACHE:
        all_kws: list[tuple[str, str]] = []
        for tid, kws in lexicon.task_keywords.items():
            for kw in kws:
                all_kws.append((kw, tid))
        for t in default_task_types():
            all_kws.append((t.bn_label, t.id))
            all_kws.append((t.en_label, t.id))
        all_kws.sort(key=lambda x: len(x[0]), reverse=True)
        suffix_pat = "|".join(re.escape(s) for s in sorted(CASE_SUFFIXES, key=len, reverse=True))

        compiled: list[tuple[re.Pattern[str], str, str]] = []
        for kw, tid in all_kws:
            words = kw.split()
            if len(words) > 1:
                kw_regex = (
                    r"\s+".join(re.escape(w) for w in words[:-1])
                    + r"\s+"
                    + re.escape(words[-1])
                    + rf"(?:[-–—]?(?:{suffix_pat}))?"
                )
            else:
                kw_regex = re.escape(words[0]) + rf"(?:[-–—]?(?:{suffix_pat}))?"
            pat = re.compile(
                rf"(?:^|[^\u0980-\u09ff\w])(?P<kw>{kw_regex})(?=$|[^\u0980-\u09ff\w])",
                re.IGNORECASE,
            )
            compiled.append((pat, kw, tid))
        _TASK_PATTERNS_CACHE[key] = compiled
    return _TASK_PATTERNS_CACHE[key]


def _get_number_phrase_regex(lexicon: Lexicon) -> re.Pattern[str]:
    key = id(lexicon)
    if key not in _NUMBER_RE_CACHE:
        word_pairs: list[tuple[str, int]] = []
        for val, words in lexicon.number_words.items():
            for w in words:
                word_pairs.append((normalise(w), val))
        for alias, val in EXTRA_NUMBER_WORDS:
            if not any(w == alias for w, _ in word_pairs):
                word_pairs.append((alias, val))
        word_pairs.sort(key=lambda x: len(x[0]), reverse=True)
        num_word_pat = "|".join(re.escape(w) for w, _ in word_pairs)
        _NUMBER_RE_CACHE[key] = re.compile(
            rf"(?:^|[^\u0980-\u09ff\w])(?P<num>(?:\d+|{num_word_pat}){CLASSIFIER_SUFFIXES})(?=$|[^\u0980-\u09ff\w])",
            re.IGNORECASE,
        )
    return _NUMBER_RE_CACHE[key]


def _find_task_spans(text: str, lexicon: Lexicon) -> list[tuple[int, int, str, str, str]]:
    patterns = _get_task_patterns(lexicon)
    found: list[tuple[int, int, str, str, str]] = []
    occupied = [False] * len(text)
    for pat, kw, tid in patterns:
        for m in pat.finditer(text):
            s, e = m.start("kw"), m.end("kw")
            if not any(occupied[s:e]):
                found.append((s, e, kw, tid, text[s:e]))
                for i in range(s, e):
                    occupied[i] = True
    found.sort(key=lambda x: x[0])
    return found


def _find_number_spans(text: str, lexicon: Lexicon) -> list[tuple[int, int, str]]:
    pat = _get_number_phrase_regex(lexicon)
    norm = text.translate(BENGALI_DIGITS)
    return [(m.start("num"), m.end("num"), m.group("num")) for m in pat.finditer(norm)]


def _split_clause_by_different_tasks(clause: str, lexicon: Lexicon) -> list[str]:
    tasks = _find_task_spans(clause, lexicon)
    distinct_tasks = {t[3] for t in tasks}
    if len(distinct_tasks) <= 1:
        return [clause]

    numbers = _find_number_spans(clause, lexicon)
    split_indices: list[int] = []
    for i in range(len(tasks) - 1):
        t1 = tasks[i]
        t2 = tasks[i + 1]
        if t1[3] == t2[3]:
            continue
        gap_start = t1[1]
        gap_end = t2[0]
        gap_numbers = [n for n in numbers if n[0] >= gap_start and n[1] <= gap_end]
        if gap_numbers:
            split_idx = gap_numbers[-1][0]
        else:
            gap_text = clause[gap_start:gap_end]
            m = PARTICLES_RE.match(gap_text)
            if m:
                split_idx = gap_start + m.end()
            else:
                split_idx = gap_end
        split_indices.append(split_idx)

    clauses: list[str] = []
    prev = 0
    for s_idx in split_indices:
        c = clause[prev:s_idx].strip()
        if c:
            clauses.append(c)
        prev = s_idx
    last = clause[prev:].strip()
    if last:
        clauses.append(last)
    return clauses


def split_into_clauses(text: str, lexicon: Lexicon) -> list[str]:
    multi = _get_multi_word_phrases(lexicon)
    pattern = _compile_phrase_pattern(multi)
    protected_spans: list[tuple[int, int]] = []
    if pattern:
        protected_spans = [m.span() for m in pattern.finditer(text)]

    valid_splits: list[tuple[int, int]] = []
    for m in CLAUSE_SPLIT.finditer(text):
        m_start, m_end = m.span()
        # If the delimiter is strictly inside a protected keyword phrase, do not split
        if any(k_start < m_start and m_end < k_end for k_start, k_end in protected_spans):
            continue
        valid_splits.append((m_start, m_end))

    initial_clauses: list[str] = []
    prev = 0
    for s_start, s_end in valid_splits:
        clause = text[prev:s_start].strip()
        if clause:
            initial_clauses.append(clause)
        prev = s_end
    last = text[prev:].strip()
    if last:
        initial_clauses.append(last)

    final_clauses: list[str] = []
    for clause in initial_clauses:
        final_clauses.extend(_split_clause_by_different_tasks(clause, lexicon))

    return final_clauses


def _resolve_clause_date(
    idx: int, date_parses: list[DateParse], today: date
) -> tuple[date, bool, list[date], float]:
    current = date_parses[idx]
    if current.date is not None:
        conf = 0.5 if current.ambiguous else 0.9
        return current.date, current.ambiguous, current.candidates, conf

    # Search backwards for preceding explicit date
    for prev_idx in range(idx - 1, -1, -1):
        prev = date_parses[prev_idx]
        if prev.date is not None:
            return prev.date, prev.ambiguous, prev.candidates, 0.7

    # Search forwards for following explicit date
    for next_idx in range(idx + 1, len(date_parses)):
        nxt = date_parses[next_idx]
        if nxt.date is not None:
            return nxt.date, nxt.ambiguous, nxt.candidates, 0.7

    # Default to today
    return today, False, [], 0.4


def extract(
    text: str, today: date, lexicon: Lexicon | None = None
) -> Extraction:
    lexicon = lexicon or default_lexicon()
    lexicon_words = _lexicon_words(lexicon)
    entries: list[ExtractedEntry] = []
    refusal: str | None = None

    raw_clauses = split_into_clauses(text, lexicon)
    if not raw_clauses:
        return Extraction(entries=[])

    valid_clauses: list[tuple[str, str, DateParse]] = []
    for raw_clause in raw_clauses:
        clause = _clean(raw_clause)
        norm = normalise(clause)
        if not tokenize(norm):
            continue
        if any(contains_phrase(norm, kw) for kw in lexicon.clinical_keywords):
            refusal = CLINICAL_REFUSAL
            continue
        d_parse = parse_date(norm, today, lexicon)
        valid_clauses.append((clause, norm, d_parse))

    if not valid_clauses:
        return Extraction(entries=[], clinical_refusal=refusal)

    date_parses = [item[2] for item in valid_clauses]

    for idx, (clause, norm, _) in enumerate(valid_clauses):
        event_date, ambiguous, candidates, date_conf = _resolve_clause_date(
            idx, date_parses, today
        )

        task = _match_task(norm, lexicon)
        number = parse_number(ID_PATTERN.sub(" ", norm), lexicon)
        ref, ref_conf, notes = _beneficiary(clause, lexicon_words)

        field_confidence: dict[str, float] = {"event_date": date_conf}
        if number is not None:
            count, count_conf = number, 0.9
        else:
            count, count_conf = 1, 0.6
        field_confidence["count"] = count_conf
        if ref is not None:
            field_confidence["beneficiary_ref"] = ref_conf

        if task is None and number is not None and ref is None and entries:
            # A bare count such as "2 jon" completes the previous entry.
            previous = entries[-1]
            updated = {**previous.field_confidence, "count": 0.9}
            entries[-1] = previous.model_copy(
                update={
                    "count": number,
                    "field_confidence": updated,
                    "confidence": min(updated.values()),
                }
            )
            continue

        if task is not None:
            field_confidence["task_type"] = 0.9
        else:
            content = [
                t for t in tokenize(norm)
                if t not in lexicon_words and not t.isdigit()
            ]
            if not content:
                continue
            task = "other"
            field_confidence["task_type"] = 0.3

        entries.append(
            ExtractedEntry(
                task_type=task,
                count=count,
                event_date=event_date,
                beneficiary_ref=ref,
                notes=notes,
                field_confidence=field_confidence,
                confidence=min(field_confidence.values()),
                date_ambiguous=ambiguous,
                date_candidates=candidates,
            )
        )

    return Extraction(entries=entries, clinical_refusal=refusal)
