import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config_loader import Checklist, Lexicon, default_lexicon, default_task_types
from app.i18n import t, to_bn_digits
from app.nlu.dates import DateParse, parse_date
from app.nlu.extract import ExtractedEntry, extract
from app.nlu.llm import Extractor
from app.nlu.numbers import parse_number
from app.nlu.text import BENGALI_DIGITS, contains_phrase, normalise, tokenize

Phase = Literal[
    "IDLE",
    "AWAITING_CONFIRMATION",
    "AWAITING_FIELD",
    "OFFERING_CHECKLIST",
    "IN_CHECKLIST",
]


class Draft(BaseModel):
    task_type: str | None = None
    count: int | None = None
    event_date: date | None = None
    date_ambiguous: bool = False
    date_candidates: list[date] = Field(default_factory=list)
    beneficiary_ref: str | None = None
    notes: str = ""
    confidence: float = 0.0


class SessionState(BaseModel):
    phase: Phase = "IDLE"
    field: str | None = None
    drafts: list[Draft] = Field(default_factory=list)
    repeats: int = 0
    lang: Literal["bn", "en"] = "bn"
    active_checklist_id: str | None = None
    checklist_question_idx: int = 0
    checklist_answers: dict[str, Any] = Field(default_factory=dict)
    checklist_unclear_attempts: int = 0
    linked_entry_id: int | None = None
    danger_sign_triggered: bool = False


class DialogueResult(BaseModel):
    response_text: str
    new_state: SessionState
    entries: list[Draft]
    ui_hint: str
    danger_banner: str | None = None
    has_danger_sign: bool = False
    checklist_answers: dict[str, Any] | None = None
    checklist_id: str | None = None
    checklist_complete: bool = False
    linked_entry_id: int | None = None


YES_WORDS = {
    "হ্যাঁ",
    "হাঁ",
    "হ্যা",
    "ha",
    "haan",
    "han",
    "yes",
    "y",
    "thik",
    "thik ache",
    "ho",
    "hye",
}
NO_WORDS = {"না", "na", "nah", "nahi", "nai", "no", "n", "noy"}
SKIP_WORDS = {
    "skip",
    "porer ta",
    "porerta",
    "পরেরটা",
    "পরের টা",
    "পরের",
    "next",
    "bad dao",
    "বাদ দাও",
    "chhere dao",
}
DANGER_BANNER = "ANM বা ডাক্তারকে জানান / Please inform your ANM or doctor"

FRACTION_WORDS: dict[str, float] = {
    "সাড়ে সাঁইত্রিশ": 37.5,
    "sade shaitrish": 37.5,
    "সাড়ে সাইত্রিশ": 37.5,
    "সাড়ে সায়ত্রিশ": 37.5,
    "আড়াই": 2.5,
    "aarai": 2.5,
    "দেড়": 1.5,
    "dedh": 1.5,
    "সাড়ে তিন": 3.5,
    "sade tin": 3.5,
    "সাড়ে দুই": 2.5,
    "sade dui": 2.5,
}


def parse_checklist_number(raw_text: str, norm_text: str, lexicon: Lexicon) -> float | int | None:
    for phrase, val in FRACTION_WORDS.items():
        if phrase in raw_text or phrase in norm_text:
            return val

    converted = unicodedata.normalize("NFC", raw_text).translate(BENGALI_DIGITS)
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", converted)
    if match:
        num_str = match.group(1)
        return float(num_str) if "." in num_str else int(num_str)

    return parse_number(norm_text, lexicon)


def _draft_from(entry: ExtractedEntry) -> Draft:
    conf = entry.field_confidence
    return Draft(
        task_type=entry.task_type if conf.get("task_type", 0) >= 0.9 else None,
        count=entry.count if conf.get("count", 0) >= 0.9 else None,
        event_date=entry.event_date if conf.get("event_date", 0) >= 0.5 else None,
        date_ambiguous=entry.date_ambiguous,
        date_candidates=entry.date_candidates,
        beneficiary_ref=entry.beneficiary_ref,
        notes=entry.notes,
        confidence=entry.confidence,
    )


def _has(norm: str, words: list[str]) -> bool:
    return any(contains_phrase(norm, word) for word in words)


def _task_from(norm: str, lexicon: Lexicon) -> str | None:
    for task_id, words in lexicon.task_keywords.items():
        if _has(norm, words):
            return task_id
    for task in default_task_types():
        if _has(norm, [task.bn_label, task.en_label]):
            return task.id
    return None


def _set_date(draft: Draft, parsed: DateParse) -> None:
    draft.event_date = parsed.date
    draft.date_ambiguous = parsed.ambiguous
    draft.date_candidates = parsed.candidates


def _next_missing(draft: Draft, today: date) -> str | None:
    if draft.task_type is None:
        return "task"
    if draft.event_date is None or draft.date_ambiguous or draft.event_date > today:
        return "date"
    if draft.count is None:
        return "count"
    return None


def _plain_date(day: date, lang: str) -> str:
    text = f"{day.day} {t(f'months.{day.month}', lang)} {day.year}"
    return to_bn_digits(text) if lang == "bn" else text


def _format_date(day: date, today: date, lang: str) -> str:
    text = _plain_date(day, lang)
    if day == today:
        return f"{t('relative_dates.today', lang)} ({text})"
    if day == today - timedelta(days=1):
        return f"{t('relative_dates.yesterday', lang)} ({text})"
    if day == today + timedelta(days=1):
        return f"{t('relative_dates.tomorrow', lang)} ({text})"
    return text


def _task_label(task_id: str | None, lang: str) -> str:
    for task in default_task_types():
        if task.id == task_id:
            return task.bn_label if lang == "bn" else task.en_label
    return task_id or ""


def _summary(drafts: list[Draft], today: date, lang: str) -> str:
    parts = []
    for draft in drafts:
        beneficiary = (
            t("summary.beneficiary", lang, ref=draft.beneficiary_ref)
            if draft.beneficiary_ref
            else ""
        )
        count = str(draft.count)
        if lang == "bn":
            count = to_bn_digits(count)
        parts.append(
            t(
                "summary.entry",
                lang,
                date=_format_date(draft.event_date, today, lang),
                task=_task_label(draft.task_type, lang),
                count=count,
                beneficiary=beneficiary,
            )
        )
    return t("summary.join", lang).join(parts)


def _question(field: str, draft: Draft, today: date, lang: str) -> str:
    if field == "task":
        return t("dialogue.ask_task", lang)
    if field == "count":
        return t("dialogue.ask_count", lang)
    if draft.date_ambiguous:
        past, future = draft.date_candidates
        if (today - past).days == 2:
            return t(
                "dialogue.ask_porshu_ambiguous",
                lang,
                past=_plain_date(past, lang),
                future=_plain_date(future, lang),
            )
        return t(
            "dialogue.ask_date_ambiguous",
            lang,
            yesterday=_plain_date(past, lang),
            tomorrow=_plain_date(future, lang),
        )
    if draft.event_date is not None and draft.event_date > today:
        return t("dialogue.future_date", lang)
    return t("dialogue.ask_date", lang)


def _continue(drafts: list[Draft], today: date, lang: str) -> DialogueResult:
    for draft in drafts:
        field = _next_missing(draft, today)
        if field:
            state = SessionState(phase="AWAITING_FIELD", field=field, drafts=drafts, lang=lang)
            return DialogueResult(
                response_text=_question(field, draft, today, lang),
                new_state=state,
                entries=drafts,
                ui_hint="ask_field",
            )
    state = SessionState(phase="AWAITING_CONFIRMATION", drafts=drafts, lang=lang)
    return DialogueResult(
        response_text=t("dialogue.readback", lang, summary=_summary(drafts, today, lang)),
        new_state=state,
        entries=drafts,
        ui_hint="confirm",
    )


def _repeat(state: SessionState) -> DialogueResult:
    repeats = state.repeats + 1
    if repeats == 1:
        text, hint = t("dialogue.repeat", state.lang), "repeat"
    else:
        text, hint = t("dialogue.type_input", state.lang), "type_input"
    return DialogueResult(
        response_text=text,
        new_state=state.model_copy(update={"repeats": repeats}),
        entries=state.drafts,
        ui_hint=hint,
    )


def _fill(field: str, drafts: list[Draft], norm: str, today: date, lexicon: Lexicon) -> bool:
    target = next((d for d in drafts if _next_missing(d, today) == field), None)
    if target is None:
        return False
    if field == "task":
        task = _task_from(norm, lexicon)
        if task is None:
            return False
        target.task_type = task
    elif field == "date":
        parsed = parse_date(norm, today, lexicon)
        if parsed.date is None:
            return False
        _set_date(target, parsed)
    else:
        number = parse_number(norm, lexicon)
        if number is None:
            return False
        target.count = number
    return True


def _apply_corrections(
    drafts: list[Draft], raw: str, norm: str, today: date, lexicon: Lexicon
) -> bool:
    changed = False
    if _has(norm, lexicon.count_words):
        number = parse_number(norm, lexicon)
        if number is not None:
            for draft in drafts:
                draft.count = number
            changed = True
    parsed = parse_date(norm, today, lexicon)
    if parsed.date is not None:
        for draft in drafts:
            _set_date(draft, parsed)
        changed = True
    refs = [e.beneficiary_ref for e in extract(raw, today, lexicon).entries if e.beneficiary_ref]
    if refs:
        for draft in drafts:
            draft.beneficiary_ref = refs[-1]
        changed = True
    return changed


def handle(
    state: SessionState,
    user_text: str,
    today: date,
    lexicon: Lexicon | None = None,
    extractor: Extractor | None = None,
    checklists: dict[str, Checklist] | None = None,
) -> DialogueResult:
    lexicon = lexicon or default_lexicon()
    lang = state.lang
    raw = user_text.strip()
    norm = normalise(raw)

    if not tokenize(norm):
        return _repeat(state)

    if _has(norm, lexicon.clinical_keywords):
        return DialogueResult(
            response_text=t("dialogue.clinical_refusal", lang),
            new_state=state,
            entries=state.drafts,
            ui_hint="refusal",
        )

    if state.phase == "OFFERING_CHECKLIST":
        is_no = any(w in norm.split() for w in NO_WORDS) or _has(norm, lexicon.no_words)
        is_yes = any(w in norm.split() for w in YES_WORDS) or _has(norm, lexicon.yes_words)
        checklist_id = state.active_checklist_id or "anc"
        checklist = checklists.get(checklist_id) if checklists else None

        if is_no or not checklist:
            return DialogueResult(
                response_text=t("dialogue.saved", lang),
                new_state=SessionState(lang=lang),
                entries=state.drafts,
                ui_hint="saved",
            )
        if is_yes:
            first_q = checklist.questions[0]
            new_state = state.model_copy(
                update={
                    "phase": "IN_CHECKLIST",
                    "checklist_question_idx": 0,
                    "checklist_unclear_attempts": 0,
                    "checklist_answers": {},
                    "danger_sign_triggered": False,
                }
            )
            return DialogueResult(
                response_text=first_q.text.get(lang, first_q.text.get("bn", "")),
                new_state=new_state,
                entries=state.drafts,
                ui_hint="checklist_question",
            )

        return DialogueResult(
            response_text=t("dialogue.offer_checklist", lang),
            new_state=state,
            entries=state.drafts,
            ui_hint="offer_checklist",
        )

    if state.phase == "IN_CHECKLIST":
        checklist_id = state.active_checklist_id or "anc"
        checklist = checklists.get(checklist_id) if checklists else None
        if not checklist:
            return DialogueResult(
                response_text=t("dialogue.saved", lang),
                new_state=SessionState(lang=lang),
                entries=state.drafts,
                ui_hint="saved",
            )

        idx = state.checklist_question_idx
        if idx >= len(checklist.questions):
            return DialogueResult(
                response_text=t("dialogue.checklist_completed", lang),
                new_state=SessionState(lang=lang),
                entries=state.drafts,
                ui_hint="checklist_completed",
            )

        q = checklist.questions[idx]
        is_skip = any(s in norm for s in SKIP_WORDS)
        answers = dict(state.checklist_answers)
        danger = state.danger_sign_triggered
        answered = False
        skipped_unclear = False

        if is_skip:
            answers[q.id] = {
                "answer": "skipped",
                "text": q.text.get(lang, q.text.get("bn", "")),
                "is_danger_sign": q.is_danger_sign,
            }
            answered = True
        elif q.answer_type == "yes_no":
            is_yes = any(w in norm.split() for w in YES_WORDS) or _has(norm, lexicon.yes_words)
            is_no = any(w in norm.split() for w in NO_WORDS) or _has(norm, lexicon.no_words)
            if is_yes:
                if q.is_danger_sign:
                    danger = True
                answers[q.id] = {
                    "answer": "yes",
                    "text": q.text.get(lang, q.text.get("bn", "")),
                    "is_danger_sign": q.is_danger_sign,
                }
                answered = True
            elif is_no:
                answers[q.id] = {
                    "answer": "no",
                    "text": q.text.get(lang, q.text.get("bn", "")),
                    "is_danger_sign": q.is_danger_sign,
                }
                answered = True
        elif q.answer_type == "number":
            num = parse_checklist_number(raw, norm, lexicon)
            if num is not None:
                answers[q.id] = {
                    "answer": num,
                    "unit": q.unit,
                    "text": q.text.get(lang, q.text.get("bn", "")),
                    "is_danger_sign": q.is_danger_sign,
                }
                answered = True

        if not answered:
            attempts = state.checklist_unclear_attempts + 1
            if attempts == 1:
                q_text = q.text.get(lang, q.text.get("bn", ""))
                return DialogueResult(
                    response_text=t("dialogue.checklist_unclear", lang, question=q_text),
                    new_state=state.model_copy(
                        update={
                            "checklist_unclear_attempts": 1,
                            "danger_sign_triggered": danger,
                        }
                    ),
                    entries=state.drafts,
                    ui_hint="checklist_unclear",
                    danger_banner=DANGER_BANNER if danger else None,
                    has_danger_sign=danger,
                )
            else:
                answers[q.id] = {
                    "answer": "unclear",
                    "text": q.text.get(lang, q.text.get("bn", "")),
                    "is_danger_sign": q.is_danger_sign,
                }
                answered = True
                skipped_unclear = True

        next_idx = idx + 1
        if next_idx < len(checklist.questions):
            next_q = checklist.questions[next_idx]
            next_text = next_q.text.get(lang, next_q.text.get("bn", ""))
            response_text = (
                t("dialogue.checklist_skip", lang, question=next_text)
                if skipped_unclear
                else next_text
            )
            new_state = state.model_copy(
                update={
                    "checklist_question_idx": next_idx,
                    "checklist_answers": answers,
                    "checklist_unclear_attempts": 0,
                    "danger_sign_triggered": danger,
                }
            )
            return DialogueResult(
                response_text=response_text,
                new_state=new_state,
                entries=state.drafts,
                ui_hint="checklist_question",
                danger_banner=DANGER_BANNER if danger else None,
                has_danger_sign=danger,
            )

        final_text = (
            t("dialogue.checklist_completed_danger", lang)
            if danger
            else t("dialogue.checklist_completed", lang)
        )
        return DialogueResult(
            response_text=final_text,
            new_state=SessionState(lang=lang),
            entries=state.drafts,
            ui_hint="checklist_completed",
            danger_banner=DANGER_BANNER if danger else None,
            has_danger_sign=danger,
            checklist_complete=True,
            checklist_answers=answers,
            checklist_id=checklist.id,
            linked_entry_id=state.linked_entry_id,
        )

    if state.phase == "IDLE":
        if extractor is None:
            extraction = extract(raw, today, lexicon)
        else:
            extraction = extractor.extract(raw, today)
        if extraction.entries:
            return _continue([_draft_from(e) for e in extraction.entries], today, lang)
        if _has(norm, lexicon.yes_words + lexicon.no_words):
            return DialogueResult(
                response_text=t("dialogue.nothing_to_confirm", lang),
                new_state=SessionState(lang=lang),
                entries=[],
                ui_hint="idle",
            )
        return _repeat(state)

    drafts = state.drafts

    if state.phase == "AWAITING_CONFIRMATION":
        if _apply_corrections(drafts, raw, norm, today, lexicon):
            return _continue(drafts, today, lang)
        if _has(norm, lexicon.yes_words) or any(w in norm.split() for w in YES_WORDS):
            checklist_id = None
            if checklists:
                for draft in drafts:
                    if draft.task_type == "antenatal_visit":
                        checklist_id = "anc"
                        break
                    elif draft.task_type == "newborn_home_visit":
                        checklist_id = "hbnc"
                        break

            if checklist_id and checklists and checklist_id in checklists:
                new_state = SessionState(
                    phase="OFFERING_CHECKLIST",
                    active_checklist_id=checklist_id,
                    drafts=drafts,
                    lang=lang,
                    linked_entry_id=state.linked_entry_id,
                )
                return DialogueResult(
                    response_text=t("dialogue.offer_checklist", lang),
                    new_state=new_state,
                    entries=drafts,
                    ui_hint="offer_checklist",
                    checklist_id=checklist_id,
                )

            return DialogueResult(
                response_text=t("dialogue.saved", lang),
                new_state=SessionState(lang=lang),
                entries=drafts,
                ui_hint="saved",
            )
        if _has(norm, lexicon.no_words) or any(w in norm.split() for w in NO_WORDS):
            return DialogueResult(
                response_text=t("dialogue.ask_which_field", lang),
                new_state=SessionState(
                    phase="AWAITING_FIELD", field="which", drafts=drafts, lang=lang
                ),
                entries=drafts,
                ui_hint="ask_field",
            )
        return _repeat(state)

    # AWAITING_FIELD
    if state.field == "which":
        if _apply_corrections(drafts, raw, norm, today, lexicon):
            return _continue(drafts, today, lang)
        return _repeat(state)
    if _fill(state.field or "", drafts, norm, today, lexicon):
        return _continue(drafts, today, lang)
    return _repeat(state)
