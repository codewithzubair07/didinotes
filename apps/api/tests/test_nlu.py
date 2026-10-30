from datetime import date

import pytest

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
