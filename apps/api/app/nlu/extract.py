import re
from datetime import date

from pydantic import BaseModel, Field

from app.config_loader import Lexicon, default_lexicon
from app.nlu.dates import parse_date
from app.nlu.numbers import parse_number
from app.nlu.text import contains_phrase, normalise, tokenize

CLINICAL_REFUSAL = (
    "I cannot answer clinical questions. Please ask your ANM or doctor. "
    "এই বিষয়ে আমি পরামর্শ দিতে পারি না। অনুগ্রহ করে আপনার ANM বা ডাক্তারের সাথে কথা বলুন।"
)

CLAUSE_SPLIT = re.compile(r"[,;।.!?]+|\s+(?:ar|aar|ebong|and|আর|এবং)\s+", re.IGNORECASE)
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
    return None


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


def extract(
    text: str, today: date, lexicon: Lexicon | None = None
) -> Extraction:
    lexicon = lexicon or default_lexicon()
    lexicon_words = _lexicon_words(lexicon)
    entries: list[ExtractedEntry] = []
    refusal: str | None = None
    carried: tuple[date, bool, list[date]] | None = None

    for raw_clause in CLAUSE_SPLIT.split(text):
        clause = _clean(raw_clause)
        norm = normalise(clause)
        if not tokenize(norm):
            continue

        if any(contains_phrase(norm, kw) for kw in lexicon.clinical_keywords):
            refusal = CLINICAL_REFUSAL
            continue

        date_parse = parse_date(norm, today, lexicon)
        if date_parse.date is not None:
            carried = (date_parse.date, date_parse.ambiguous, date_parse.candidates)
            event_date, ambiguous, candidates = carried
            date_conf = 0.5 if ambiguous else 0.9
        elif carried is not None:
            event_date, ambiguous, candidates = carried
            date_conf = 0.7
        else:
            event_date, ambiguous, candidates = today, False, []
            date_conf = 0.4

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
