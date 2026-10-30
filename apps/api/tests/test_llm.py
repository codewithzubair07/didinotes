import json
import logging
from datetime import date

import pytest

from app.nlu.llm import (
    FallbackExtractor,
    LLMError,
    OpenAIExtractor,
    RulesExtractor,
    to_initials,
)

TODAY = date(2026, 10, 29)
PROMPT = "Today {today}. Tasks: {task_ids}."
TASK_IDS = ["antenatal_visit", "immunization_session", "other"]


def _reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _provider(post) -> OpenAIExtractor:
    return OpenAIExtractor(
        api_key="test-key",
        model="test-model",
        base_url="https://example.invalid/v1",
        timeout=1.0,
        task_ids=TASK_IDS,
        prompt_template=PROMPT,
        post=post,
    )


def _fixed(content: str):
    def post(url, headers, body, timeout):
        return _reply(content)

    return post


def _raises(exc: Exception):
    def post(url, headers, body, timeout):
        raise exc

    return post


VALID = json.dumps(
    {
        "entries": [
            {
                "task_type": "antenatal_visit",
                "count": 1,
                "event_date": "2026-10-29",
                "beneficiary_ref": "R",
                "date_ambiguous": False,
            }
        ],
        "clinical": False,
    }
)


def test_valid_output_becomes_entries():
    result = _provider(_fixed(VALID)).extract("aaj Rina ANC visit korlam", TODAY)
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.task_type == "antenatal_visit"
    assert entry.beneficiary_ref == "R"
    assert entry.event_date == TODAY
    assert result.clinical_refusal is None


def test_clinical_flag_returns_fixed_refusal():
    content = json.dumps({"entries": [], "clinical": True})
    result = _provider(_fixed(content)).extract("ki dose dibo", TODAY)
    assert result.entries == []
    assert result.clinical_refusal is not None
    assert "ANM" in result.clinical_refusal


def test_full_name_is_reduced_to_initials():
    content = json.dumps(
        {
            "entries": [
                {
                    "task_type": "antenatal_visit",
                    "count": 1,
                    "event_date": "2026-10-29",
                    "beneficiary_ref": "Mina Begum",
                    "date_ambiguous": False,
                }
            ],
            "clinical": False,
        }
    )
    result = _provider(_fixed(content)).extract("aaj Mina Begum ANC", TODAY)
    assert result.entries[0].beneficiary_ref == "MB"


def test_invalid_json_is_a_failure():
    with pytest.raises(LLMError) as info:
        _provider(_fixed("not json at all")).extract("aaj Rina ANC", TODAY)
    assert info.value.reason == "invalid_json"


def test_timeout_is_a_failure():
    with pytest.raises(LLMError) as info:
        _provider(_raises(TimeoutError())).extract("aaj Rina ANC", TODAY)
    assert info.value.reason == "timeout"


@pytest.mark.parametrize(
    "content",
    [
        {"entries": [{"task_type": "antenatal_visit", "count": 0, "event_date": "2026-10-29"}]},
        {"entries": [], "clinical": False, "extra": "field"},
        {"entries": [{"task_type": "not_a_task", "count": 1, "event_date": "2026-10-29"}]},
    ],
)
def test_schema_violation_is_a_failure(content):
    with pytest.raises(LLMError) as info:
        _provider(_fixed(json.dumps(content))).extract("aaj Rina ANC", TODAY)
    assert info.value.reason == "schema_violation"


def test_fallback_uses_rules_and_logs_only_reason(caplog):
    secret = "aaj Rina ANC visit korlam"
    extractor = FallbackExtractor(_provider(_fixed("not json")), RulesExtractor())
    with caplog.at_level(logging.WARNING, logger="asha_diary.llm"):
        result = extractor.extract(secret, TODAY)
    assert extractor.last_source == "rules_fallback"
    assert result.entries[0].task_type == "antenatal_visit"
    assert "invalid_json" in caplog.text
    assert secret not in caplog.text
    assert "Rina" not in caplog.text


def test_fallback_on_timeout_does_not_raise():
    extractor = FallbackExtractor(_provider(_raises(TimeoutError())), RulesExtractor())
    result = extractor.extract("aaj Rina ANC visit korlam", TODAY)
    assert extractor.last_source == "rules_fallback"
    assert len(result.entries) == 1


def test_fallback_keeps_primary_when_valid():
    extractor = FallbackExtractor(_provider(_fixed(VALID)), RulesExtractor())
    extractor.extract("aaj Rina ANC visit korlam", TODAY)
    assert extractor.last_source == "openai"


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("Rina", "R"),
        ("Mina Begum", "MB"),
        ("R12", "R12"),
        ("47", "47"),
        ("RINA", "R"),
        ("", None),
        (None, None),
    ],
)
def test_to_initials(ref, expected):
    assert to_initials(ref) == expected
