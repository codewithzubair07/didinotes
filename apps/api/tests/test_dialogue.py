from datetime import date

import pytest

from app.dialogue.manager import SessionState, handle

TODAY = date(2026, 10, 29)


def turn(state: SessionState, text: str, today: date = TODAY):
    return handle(state, text, today)


def confirmed_state() -> SessionState:
    result = turn(SessionState(), "aaj Rina ANC visit korlam, 2 jon")
    assert result.ui_hint == "confirm"
    return result.new_state


def test_idle_full_sentence_goes_to_confirmation():
    result = turn(SessionState(), "aaj Rina ANC visit korlam, 2 jon")
    assert result.ui_hint == "confirm"
    assert result.new_state.phase == "AWAITING_CONFIRMATION"
    assert "আমি শুনেছি" in result.response_text
    assert "আজ" in result.response_text
    assert "29" in result.response_text or "২৯" in result.response_text


def test_readback_contains_beneficiary_initials_only():
    result = turn(SessionState(), "aaj Rina ANC visit korlam, 2 jon")
    assert result.entries[0].beneficiary_ref == "R"
    assert "Rina" not in result.response_text


def test_missing_count_asks_count_first():
    result = turn(SessionState(), "aaj Rina ANC visit korlam")
    assert result.ui_hint == "ask_field"
    assert result.new_state.field == "count"
    assert "কতজন" in result.response_text


def test_missing_task_asks_task_first():
    result = turn(SessionState(), "aaj 2 jon")
    assert result.new_state.field == "task"


def test_missing_date_asks_date_when_task_known():
    result = turn(SessionState(), "ANC visit korlam 2 jon")
    assert result.new_state.field == "date"


def test_answering_count_question_completes_entry():
    asked = turn(SessionState(), "aaj Rina ANC visit korlam")
    result = turn(asked.new_state, "2 jon")
    assert result.ui_hint == "confirm"
    assert result.entries[0].count == 2


def test_answering_task_question_fills_task():
    asked = turn(SessionState(), "aaj 2 jon")
    result = turn(asked.new_state, "teeka")
    assert result.entries[0].task_type == "immunization_session"
    assert result.ui_hint in ("ask_field", "confirm")


def test_yes_saves_and_returns_to_idle():
    result = turn(confirmed_state(), "hyan")
    assert result.ui_hint == "saved"
    assert result.new_state.phase == "IDLE"
    assert result.response_text == "সংরক্ষিত হয়েছে। আরও কিছু?"


@pytest.mark.parametrize("word", ["ha", "হ্যাঁ", "thik ache", "ঠিক আছে"])
def test_yes_words_both_scripts(word):
    assert turn(confirmed_state(), word).ui_hint == "saved"


def test_no_asks_which_field_then_accepts_correction():
    after_no = turn(confirmed_state(), "na")
    assert after_no.ui_hint == "ask_field"
    assert after_no.new_state.phase == "AWAITING_FIELD"
    assert "কোন তথ্যটি ভুল" in after_no.response_text
    corrected = turn(after_no.new_state, "count 3")
    assert corrected.entries[0].count == 3
    assert corrected.ui_hint == "confirm"


def test_correction_date_word_sets_date():
    result = turn(confirmed_state(), "na, gotokal chilo")
    assert result.ui_hint == "confirm"
    assert result.entries[0].event_date == date(2026, 10, 28)


def test_correction_count_sets_count():
    result = turn(confirmed_state(), "count 5")
    assert result.entries[0].count == 5
    assert result.ui_hint == "confirm"


def test_correction_beneficiary_changes_ref():
    result = turn(confirmed_state(), "Rina na, Mina")
    assert result.entries[0].beneficiary_ref == "M"
    assert result.ui_hint == "confirm"


def test_repeat_then_type_fallback_on_empty_input():
    first = turn(SessionState(), "   ")
    assert first.ui_hint == "repeat"
    second = turn(first.new_state, "   ")
    assert second.ui_hint == "type_input"


def test_repeat_then_fallback_on_gibberish_in_question():
    asked = turn(SessionState(), "aaj Rina ANC visit korlam")
    first = turn(asked.new_state, "xxx yyy")
    assert first.ui_hint == "repeat"
    second = turn(first.new_state, "xxx yyy")
    assert second.ui_hint == "type_input"


def test_repeat_counter_resets_after_progress():
    asked = turn(SessionState(), "aaj Rina ANC visit korlam")
    stuck = turn(asked.new_state, "xxx")
    done = turn(stuck.new_state, "2 jon")
    assert done.new_state.repeats == 0


def test_kal_is_ambiguous_and_asks_both_days():
    result = turn(SessionState(), "kal Rina ANC korlam 2 jon")
    assert result.ui_hint == "ask_field"
    assert result.new_state.field == "date"
    assert "২৮ অক্টোবর" in result.response_text
    assert "৩০ অক্টোবর" in result.response_text


def test_kal_answer_gotokal_resolves_to_yesterday():
    asked = turn(SessionState(), "kal Rina ANC korlam 2 jon")
    result = turn(asked.new_state, "gotokal")
    assert result.entries[0].event_date == date(2026, 10, 28)
    assert result.entries[0].date_ambiguous is False
    assert result.ui_hint == "confirm"


def test_kal_answer_agamikal_asks_future_warning():
    asked = turn(SessionState(), "kal Rina ANC korlam 2 jon")
    result = turn(asked.new_state, "agamikal")
    assert "ভবিষ্যতের" in result.response_text
    assert result.new_state.field == "date"


def test_porshu_is_ambiguous_and_names_both_days():
    result = turn(SessionState(), "porshu Rina ANC korlam 2 jon")
    assert result.ui_hint == "ask_field"
    assert "দু'দিন আগে" in result.response_text
    assert "দু'দিন পরে" in result.response_text


def test_porshu_answer_with_unknown_word_repeats():
    # No lexicon word for "two days ago" exists yet, so the answer cannot be resolved.
    asked = turn(SessionState(), "porshu Rina ANC korlam 2 jon")
    result = turn(asked.new_state, "aagei")
    assert result.ui_hint == "repeat"
    assert result.new_state.field == "date"


def test_future_date_is_never_accepted_silently():
    result = turn(SessionState(), "agamikal Rina ANC korlam 2 jon")
    assert result.ui_hint == "ask_field"
    assert result.new_state.field == "date"
    assert "ভবিষ্যতের" in result.response_text


def test_multi_entry_read_back_lists_every_entry():
    result = turn(SessionState(), "aaj Rina ANC visit korlam, 2 jon baccha-r teeka dilam")
    assert len(result.entries) == 2
    assert result.ui_hint == "ask_field"
    answered = turn(result.new_state, "1 jon")
    assert answered.ui_hint == "confirm"
    assert answered.response_text.count(";") == 1


def test_english_mode_uses_english_strings():
    state = SessionState(lang="en")
    result = turn(state, "aaj Rina ANC visit korlam")
    assert result.response_text == "How many people or items?"


@pytest.mark.parametrize(
    "text",
    [
        "amar ki dose dite hobe",
        "ei ওষুধ kheye ki hobe",
        "jor hole ki korbo",
        "bachchar fever ache",
        "rokto porche ki korbo",
        "byatha komano jabe ki",
        "ki khabo ami ekhon",
        "tablet dose koto",
        "medicine kothay pabo",
        "pain khub beshi",
    ],
)
def test_clinical_questions_get_fixed_refusal(text):
    result = turn(SessionState(), text)
    assert result.ui_hint == "refusal"
    assert "ANM" in result.response_text
    assert result.new_state.phase == "IDLE"


def test_clinical_refusal_does_not_save_or_change_pending_state():
    pending = confirmed_state()
    result = turn(pending, "dose ki")
    assert result.ui_hint == "refusal"
    assert result.new_state.phase == "AWAITING_CONFIRMATION"
    assert result.entries == pending.drafts


def test_no_entries_in_idle_asks_repeat_not_save():
    result = turn(SessionState(), "hello there")
    assert result.ui_hint in ("repeat", "ask_field", "confirm")
    assert result.ui_hint != "saved"


def test_yes_in_idle_with_nothing_pending_says_nothing_to_confirm():
    result = turn(SessionState(), "hyan")
    assert result.ui_hint == "idle"
    assert result.response_text == "এখন নিশ্চিত করার কিছু নেই। কী কাজ করেছেন বলুন।"
