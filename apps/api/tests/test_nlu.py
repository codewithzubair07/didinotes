from datetime import date, timedelta

import pytest

from app.dialogue.manager import SessionState, handle
from app.nlu.dates import parse_date
from app.nlu.extract import CLINICAL_REFUSAL, extract
from app.nlu.numbers import parse_number
from app.nlu.text import normalise

TODAY = date(2026, 10, 29)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("  Aaj   ", "aaj"),
        ("ANC", "anc"),
        ("২ জন", "2 জন"),
        ("\u0995\u09cd\u09b7", "\u0995\u09cd\u09b7"),
        ("  ০১২৩৪৫৬৭৮৯  ", "0123456789"),
    ],
)
def test_normalise(text, expected):
    assert normalise(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2", 2),
        ("২", 2),
        ("2 jon", 2),
        ("2 জন", 2),
        ("3 ta", 3),
        ("৩ টা", 3),
        ("ek", 1),
        ("এক", 1),
        ("dui", 2),
        ("দুই", 2),
        ("tin", 3),
        ("তিন", 3),
        ("char", 4),
        ("চার", 4),
        ("panch", 5),
        ("পাঁচ", 5),
        ("chhoy", 6),
        ("ছয়", 6),
        ("shat", 7),
        ("সাত", 7),
        ("aat", 8),
        ("আট", 8),
        ("noy", 9),
        ("নয়", 9),
        ("dosh", 10),
        ("দশ", 10),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_parse_number_none_when_absent():
    assert parse_number("anc visit korlam") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("২ জন।", 2),
        ("duijon", 2),
        ("দুইজন", 2),
        ("ekjon", 1),
        ("একজন", 1),
        ("tinjon", 3),
        ("তিনজন", 3),
        ("doshjon", 10),
        ("দশজন", 10),
        ("2.", 2),
        ("2,", 2),
    ],
)
def test_parse_number_compounds_and_punctuation(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("aaj", TODAY),
        ("আজ", TODAY),
        ("gotokal", date(2026, 10, 28)),
        ("গতকাল", date(2026, 10, 28)),
        ("agamikal", date(2026, 10, 30)),
        ("আগামীকাল", date(2026, 10, 30)),
    ],
)
def test_parse_date_unambiguous_words(text, expected):
    result = parse_date(text, TODAY)
    assert result.date == expected
    assert result.ambiguous is False


@pytest.mark.parametrize("text", ["kal", "কাল"])
def test_kal_is_ambiguous_and_defaults_to_past(text):
    result = parse_date(text, TODAY)
    assert result.ambiguous is True
    assert result.date == date(2026, 10, 28)
    assert set(result.candidates) == {date(2026, 10, 28), date(2026, 10, 30)}


@pytest.mark.parametrize("text", ["porshu", "পরশু"])
def test_porshu_is_ambiguous_and_defaults_to_past(text):
    result = parse_date(text, TODAY)
    assert result.ambiguous is True
    assert result.date == date(2026, 10, 27)
    assert set(result.candidates) == {date(2026, 10, 27), date(2026, 10, 31)}


def test_no_date_word_returns_none():
    result = parse_date("ANC visit", TODAY)
    assert result.date is None
    assert result.ambiguous is False


def test_completed_work_never_defaults_to_future():
    for text in ["kal", "কাল", "porshu", "পরশু"]:
        assert parse_date(text, TODAY).date <= TODAY


def test_extract_bengali_multi_entry_sentence():
    result = extract("aaj Rina-r ANC visit korlam, 2 jon baccha-r teeka dilam", TODAY)
    assert len(result.entries) == 2
    anc, teeka = result.entries
    assert anc.task_type == "antenatal_visit"
    assert anc.event_date == TODAY
    assert anc.beneficiary_ref == "R"
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 2
    assert teeka.event_date == TODAY


def test_extract_bengali_script_task_words():
    result = extract("আজ গর্ভকালীন পরীক্ষা করলাম", TODAY)
    assert result.entries[0].task_type == "antenatal_visit"
    assert result.entries[0].event_date == TODAY


def test_extract_english_task_words_inside_bengali_grammar():
    result = extract("gotokal 3 ta checkup korlam", TODAY)
    entry = result.entries[0]
    assert entry.task_type == "antenatal_visit"
    assert entry.count == 3
    assert entry.event_date == date(2026, 10, 28)


def test_extract_bengali_digits_count():
    result = extract("আজ ২ জন টিকা দিলাম", TODAY)
    assert result.entries[0].count == 2


def test_extract_number_word_count():
    result = extract("aaj dui jon teeka dilam", TODAY)
    assert result.entries[0].count == 2
    assert result.entries[0].task_type == "immunization_session"


def test_extract_kal_marks_entry_ambiguous():
    result = extract("kal ANC korlam", TODAY)
    entry = result.entries[0]
    assert entry.date_ambiguous is True
    assert entry.event_date == date(2026, 10, 28)
    assert date(2026, 10, 30) in entry.date_candidates


def test_extract_second_entry_inherits_date():
    result = extract("gotokal ANC korlam, teeka dilam", TODAY)
    assert [e.event_date for e in result.entries] == [date(2026, 10, 28)] * 2


def test_extract_full_name_reduced_to_initials():
    result = extract("Sunita Devi ANC visit korlam", TODAY)
    entry = result.entries[0]
    assert entry.beneficiary_ref == "SD"
    assert "Sunita" not in entry.notes
    assert "Devi" not in entry.notes


def test_extract_id_used_as_reference_and_name_removed_from_notes():
    result = extract("Sunita Devi ID 123 ANC", TODAY)
    entry = result.entries[0]
    assert entry.beneficiary_ref == "123"
    assert "Sunita" not in entry.notes


def test_extract_no_name_gives_no_ref():
    result = extract("ANC visit korlam", TODAY)
    assert result.entries[0].beneficiary_ref is None


def test_extract_clinical_question_refused():
    result = extract("ei rogir ki dose dibo?", TODAY)
    assert result.clinical_refusal == CLINICAL_REFUSAL
    assert result.entries == []


def test_extract_clinical_question_in_bengali_refused():
    result = extract("জ্বর হলে কী খাব", TODAY)
    assert result.clinical_refusal == CLINICAL_REFUSAL


def test_extract_empty_text_gives_no_entries():
    assert extract("   ", TODAY).entries == []


def test_extract_unknown_task_falls_back_to_other_with_low_confidence():
    result = extract("Rina gelam", TODAY)
    entry = result.entries[0]
    assert entry.task_type == "other"
    assert entry.field_confidence["task_type"] < 0.5


def test_extract_confidence_is_min_of_fields():
    entry = extract("aaj Rina-r ANC visit korlam", TODAY).entries[0]
    assert entry.confidence == min(entry.field_confidence.values())


@pytest.mark.parametrize(
    "text, expected",
    [
        ("দুজনকে", 2),
        ("তিনজনকে", 3),
        ("একজনকে", 1),
        ("duijonke", 2),
        ("dujonke", 2),
        ("tinjonke", 3),
        ("ekjonke", 1),
        ("দুজনের", 2),
        ("duijoner", 2),
        ("তিনজনের", 3),
        ("একজনের", 1),
        ("duto", 2),
        ("dutoke", 2),
        ("ektake", 1),
        ("2জনকে", 2),
        ("2jonke", 2),
        ("২জনকে", 2),
    ],
)
def test_parse_number_compounds_with_suffixes(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize(
    "text, expected_task, expected_count, expected_date",
    [
        # 1. Prompt example: Bengali + English loanword
        ("আজ দুজনকে vaccination দিলাম।", "immunization_session", 2, TODAY),
        # 2. Latin task word with Bengali case suffix (hyphenated)
        ("আজকে ৩ জনকে vaccination-ke নিয়ে বললাম", "immunization_session", 3, TODAY),
        # 3. Latin acronym with Bengali case suffix (ANC-এর) and checkup
        ("আজকে ANC-এর ২ জনের চেকআপ করলাম", "antenatal_visit", 2, TODAY),
        # 4. Bengali script with English keywords (antenatal checkup)
        ("গতকাল একজনকে checkup করালাম", "antenatal_visit", 1, TODAY - timedelta(days=1)),
        # 5. Bengali script spelling of English loanword (ভ্যাকসিনেশন)
        ("আজ তিনজনকে ভ্যাকসিনেশন দিলাম", "immunization_session", 3, TODAY),
        # 6. Latin task with Bengali case suffix (delivery-র)
        (
            "আজকে একজনকে delivery-র জন্য হাসপাতালে নিয়ে গেলাম",
            "institutional_delivery_accompaniment",
            1,
            TODAY,
        ),
        # 7. Benglish with Romanised count suffix (duijonke) + home visit
        ("aaj duijonke newborn home visit korlam", "newborn_home_visit", 2, TODAY),
        # 8. Bengali script spelling of acronym (এএনসি)
        ("আজ দুজনকে এএনসি করালাম", "antenatal_visit", 2, TODAY),
        # 9. Bengali script spelling of acronym (পিএনসি) + Bengali script loanword (হোম ভিজিট)
        ("আজ তিনজনকে পিএনসি হোম ভিজিট দিলাম", "newborn_home_visit", 3, TODAY),
        # 10. Multi-word Latin task in Bengali sentence
        (
            "আজকে ৪ জনকে family planning counselling দিলাম",
            "family_planning_counselling",
            4,
            TODAY,
        ),
        # 11. Romanised count suffix (tinjonke) + English loanword
        ("aaj tinjonke vaccination dilam", "immunization_session", 3, TODAY),
        # 12. Romanised count with classifier (dujonke) + immunization
        (
            "gotokal dujonke immunization korlam",
            "immunization_session",
            2,
            TODAY - timedelta(days=1),
        ),
    ],
)
def test_extract_mixed_script_sentences(text, expected_task, expected_count, expected_date):
    result = extract(text, TODAY)
    assert len(result.entries) >= 1
    entry = result.entries[0]
    assert entry.task_type == expected_task
    assert entry.count == expected_count
    assert entry.event_date == expected_date
    assert entry.confidence >= 0.9


def test_dialogue_mixed_script_prompt_example():
    result = handle(SessionState(), "আজ দুজনকে vaccination দিলাম।", TODAY)
    assert result.ui_hint == "confirm"
    assert result.new_state.phase == "AWAITING_CONFIRMATION"
    assert len(result.entries) == 1
    draft = result.entries[0]
    assert draft.task_type == "immunization_session"
    assert draft.count == 2
    assert draft.event_date == TODAY
    assert "টিকাদান" in result.response_text
    assert "২ জন" in result.response_text
    assert "আমি শুনেছি" in result.response_text


@pytest.mark.parametrize(
    "text, expected_task, expected_date",
    [
        # 1. Prompt example: filler words before (সারদিনিয়ার), between (-এর), after (করলাম)
        (
            "আজ সারদিনিয়ার newborn-এর home visit করলাম",
            "newborn_home_visit",
            TODAY,
        ),
        # 2. Filler words before (অনেক দূর গিয়ে গ্রামে পৌঁছে) and between (bacchar ekta)
        (
            "আজকে অনেক দূর গিয়ে গ্রামে পৌঁছে newborn bacchar ekta home visit korlam, 1 jon",
            "newborn_home_visit",
            TODAY,
        ),
        # 3. Filler words before (হাসপাতালে গিয়ে) and between (clinic-e)
        (
            "গতকাল হাসপাতালে গিয়ে antenatal clinic-e checkup korlam, 2 jon",
            "antenatal_visit",
            TODAY - timedelta(days=1),
        ),
        # 4. Filler words between (niye bishesh) multi-word task keywords
        (
            "আজ ৩ জনকে family planning niye bishesh counselling dilam",
            "family_planning_counselling",
            TODAY,
        ),
        # 5. Filler words between (boro hospital-e) in institutional delivery
        (
            "আজকে ১ জনকে institutional boro hospital-e delivery koralam",
            "institutional_delivery_accompaniment",
            TODAY,
        ),
        # 6. Bengali script: filler words between (জন্য একটি সুন্দর) and after (সম্পন্ন করলাম)
        (
            "আজ নবজাতকের জন্য একটি সুন্দর বাড়ি ভিজিট সম্পন্ন করলাম",
            "newborn_home_visit",
            TODAY,
        ),
    ],
)
def test_filler_words_do_not_block_task_matching(text, expected_task, expected_date):
    result = extract(text, TODAY)
    assert len(result.entries) >= 1
    entry = result.entries[0]
    assert entry.task_type == expected_task
    assert entry.event_date == expected_date


def test_dialogue_filler_words_prompt_example():
    asked = handle(SessionState(), "আজ সারদিনিয়ার newborn-এর home visit করলাম", TODAY)
    assert asked.ui_hint == "ask_field"
    assert asked.new_state.field == "count"
    assert len(asked.entries) == 1
    assert asked.entries[0].task_type == "newborn_home_visit"

    confirmed = handle(asked.new_state, "১ জন", TODAY)
    assert confirmed.ui_hint == "confirm"
    assert confirmed.entries[0].task_type == "newborn_home_visit"
    assert confirmed.entries[0].count == 1
    assert "নবজাতকের বাড়ি ভিজিট" in confirmed.response_text


def test_extract_multi_task_prompt_example():
    # Example: "aaj ekta ANC ar duijon-ke vaccination dilam"
    result = extract("aaj ekta ANC ar duijon-ke vaccination dilam", TODAY)
    assert len(result.entries) == 2
    anc, teeka = result.entries
    assert anc.task_type == "antenatal_visit"
    assert anc.count == 1
    assert anc.event_date == TODAY
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 2
    assert teeka.event_date == TODAY


def test_extract_two_tasks_with_counts():
    result = extract("gotokal 1 ta checkup ebong 3 ta teeka dilam", TODAY)
    assert len(result.entries) == 2
    checkup, teeka = result.entries
    assert checkup.task_type == "antenatal_visit"
    assert checkup.count == 1
    assert checkup.event_date == TODAY - timedelta(days=1)
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 3
    assert teeka.event_date == TODAY - timedelta(days=1)


def test_dialogue_two_tasks_without_counts_follow_up():
    t1 = handle(SessionState(), "aaj ANC ebong teeka dilam", TODAY)
    assert t1.ui_hint == "ask_field"
    assert t1.new_state.phase == "AWAITING_FIELD"
    assert t1.new_state.field == "count"
    assert len(t1.entries) == 2
    assert t1.entries[0].task_type == "antenatal_visit"
    assert t1.entries[0].count is None
    assert t1.entries[1].task_type == "immunization_session"
    assert t1.entries[1].count is None

    # Follow-up for first task count
    t2 = handle(t1.new_state, "1 ta", TODAY)
    assert t2.ui_hint == "ask_field"
    assert t2.new_state.phase == "AWAITING_FIELD"
    assert t2.new_state.field == "count"
    assert t2.entries[0].count == 1
    assert t2.entries[1].count is None

    # Follow-up for second task count
    t3 = handle(t2.new_state, "2 jon", TODAY)
    assert t3.ui_hint == "confirm"
    assert t3.new_state.phase == "AWAITING_CONFIRMATION"
    assert t3.entries[0].count == 1
    assert t3.entries[1].count == 2
    # Read-back card lists both tasks
    assert "গর্ভকালীন পরীক্ষা" in t3.response_text
    assert "টিকাদান" in t3.response_text

    # YES confirms and saves all tasks
    t4 = handle(t3.new_state, "হ্যাঁ", TODAY)
    assert t4.ui_hint in ("saved", "offer_checklist")
    assert len(t4.entries) == 2
    assert t4.entries[0].task_type == "antenatal_visit"
    assert t4.entries[0].count == 1
    assert t4.entries[1].task_type == "immunization_session"
    assert t4.entries[1].count == 2


def test_extract_date_shared_by_both():
    # Date in second clause ('gotokal') is shared with the first clause
    result = extract("ekta ANC o duita teeka dilam gotokal", TODAY)
    assert len(result.entries) == 2
    anc, teeka = result.entries
    assert anc.task_type == "antenatal_visit"
    assert anc.count == 1
    assert anc.event_date == TODAY - timedelta(days=1)
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 2
    assert teeka.event_date == TODAY - timedelta(days=1)


def test_extract_single_task_sentence_unchanged():
    result = extract("aaj Rina-r ANC visit korlam, 1 jon", TODAY)
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.task_type == "antenatal_visit"
    assert entry.count == 1
    assert entry.event_date == TODAY
    assert entry.beneficiary_ref == "R"


def test_extract_clinical_question_unchanged():
    result = extract("ei rogir ki dose dibo?", TODAY)
    assert result.clinical_refusal == CLINICAL_REFUSAL
    assert result.entries == []


def test_extract_keyword_phrase_with_conjunction_stays_one_task():
    result = extract("aaj 2 jon family planning and counselling dilam", TODAY)
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.task_type == "family_planning_counselling"
    assert entry.count == 2
    assert entry.event_date == TODAY


@pytest.mark.parametrize(
    "conj",
    ["ar", "ebong", "o", "and", "tarpor", "আর", "এবং", "তারপর", "ও"],
)
def test_extract_conjunctions_clause_splitting(conj):
    text = f"aaj 1 ta ANC {conj} 2 ta teeka dilam"
    result = extract(text, TODAY)
    assert len(result.entries) == 2
    assert result.entries[0].task_type == "antenatal_visit"
    assert result.entries[0].count == 1
    assert result.entries[1].task_type == "immunization_session"
    assert result.entries[1].count == 2


def test_extract_misheard_particle_transcript():
    # Prompt bug transcript: "আজ একটা ANC এর দুইজনকে vaccination দিলাম।"
    result = extract("আজ একটা ANC এর দুইজনকে vaccination দিলাম।", TODAY)
    assert len(result.entries) == 2
    anc, teeka = result.entries
    assert anc.task_type == "antenatal_visit"
    assert anc.count == 1
    assert anc.event_date == TODAY
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 2
    assert teeka.event_date == TODAY


def test_extract_misheard_particle_latin():
    # Latin script equivalent
    result = extract("aaj ekta ANC er duijonke vaccination dilam", TODAY)
    assert len(result.entries) == 2
    anc, teeka = result.entries
    assert anc.task_type == "antenatal_visit"
    assert anc.count == 1
    assert anc.event_date == TODAY
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 2
    assert teeka.event_date == TODAY


@pytest.mark.parametrize(
    "text",
    [
        "আজ একটা ANC এর দুইজনকে vaccination দিলাম",
        "আজ একটা ANC ও দুইজনকে vaccination দিলাম",
        "আজ একটা ANC আর দুইজনকে vaccination দিলাম",
        "আজ একটা ANC দুইজনকে vaccination দিলাম",
    ],
)
def test_extract_misheard_particle_variants(text):
    result = extract(text, TODAY)
    assert len(result.entries) == 2
    anc, teeka = result.entries
    assert anc.task_type == "antenatal_visit"
    assert anc.count == 1
    assert anc.event_date == TODAY
    assert teeka.task_type == "immunization_session"
    assert teeka.count == 2
    assert teeka.event_date == TODAY


def test_extract_same_task_sentence_stays_one_entry():
    # Both keywords belong to antenatal_visit -> do not split
    result = extract("আজকে ANC-এর ২ জনের চেকআপ করলাম", TODAY)
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.task_type == "antenatal_visit"
    assert entry.count == 2
    assert entry.event_date == TODAY


def test_extract_clinical_question_stays_refusal():
    result = extract("ei rogir ki dose dibo?", TODAY)
    assert result.clinical_refusal == CLINICAL_REFUSAL
    assert result.entries == []



