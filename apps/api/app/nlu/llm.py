import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.config_loader import default_task_types
from app.nlu.extract import CLINICAL_REFUSAL, ExtractedEntry, Extraction, extract
from app.settings import Settings

logger = logging.getLogger("asha_diary.llm")

# Initials (1-3 capitals) or an ID containing a digit. Anything else is reduced to initials.
INITIALS_PATTERN = re.compile(r"^(?:[A-Z]{1,3}|(?=.*\d)[A-Za-z0-9]{1,16})$")
PROMPT_FILE = "prompts/extract_entries.txt"


class LLMError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LLMEntry(BaseModel):
    model_config = {"extra": "forbid"}

    task_type: str
    count: int = Field(ge=1, le=99)
    event_date: date
    beneficiary_ref: str | None = None
    date_ambiguous: bool = False


class LLMOutput(BaseModel):
    model_config = {"extra": "forbid"}

    entries: list[LLMEntry] = Field(max_length=10)
    clinical: bool = False


class Extractor(Protocol):
    name: str

    def extract(self, text: str, today: date) -> Extraction: ...


def to_initials(ref: str | None) -> str | None:
    # Full names become initials. Short IDs such as "R12" pass through unchanged.
    if ref is None:
        return None
    ref = ref.strip()
    if INITIALS_PATTERN.match(ref):
        return ref
    words = re.findall(r"[^\W\d_]+", ref)
    initials = "".join(word[0].upper() for word in words)[:16]
    return initials or None


class RulesExtractor:
    name = "rules"

    def extract(self, text: str, today: date) -> Extraction:
        return extract(text, today)


class OpenAIExtractor:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float,
        task_ids: list[str],
        prompt_template: str,
        post: Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.task_ids = task_ids
        self.prompt_template = prompt_template
        self.post = post or _post_json

    def _system_prompt(self, today: date) -> str:
        return (
            self.prompt_template.replace("{today}", today.isoformat())
            .replace("{task_ids}", ", ".join(self.task_ids))
        )

    def extract(self, text: str, today: date) -> Extraction:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt(today)},
                {"role": "user", "content": text},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            response = self.post(self.url, headers, body, self.timeout)
            content = response["choices"][0]["message"]["content"]
        except TimeoutError as exc:
            raise LLMError("timeout") from exc
        except LLMError:
            raise
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("bad_response") from exc
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMError("invalid_json") from exc
        try:
            output = LLMOutput.model_validate(payload)
        except ValidationError as exc:
            raise LLMError("schema_violation") from exc
        return self._to_extraction(output, today)

    def _to_extraction(self, output: LLMOutput, today: date) -> Extraction:
        if output.clinical:
            return Extraction(entries=[], clinical_refusal=CLINICAL_REFUSAL)
        entries = []
        for item in output.entries:
            if item.task_type not in self.task_ids:
                raise LLMError("schema_violation")
            ambiguous = item.date_ambiguous or item.event_date > today
            entries.append(
                ExtractedEntry(
                    task_type=item.task_type,
                    count=item.count,
                    event_date=item.event_date,
                    beneficiary_ref=to_initials(item.beneficiary_ref),
                    notes="",
                    field_confidence={
                        "task_type": 0.9,
                        "count": 0.9,
                        "event_date": 0.5 if ambiguous else 0.9,
                    },
                    confidence=0.5 if ambiguous else 0.8,
                    date_ambiguous=ambiguous,
                    date_candidates=[item.event_date],
                )
            )
        return Extraction(entries=entries)


def _post_json(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise LLMError("timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise LLMError("timeout") from exc
        raise LLMError("network") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("bad_response") from exc


class FallbackExtractor:
    # Tries the primary extractor and falls back to rules, logging only the reason.
    def __init__(self, primary: Extractor, fallback: Extractor) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.last_source = primary.name

    def extract(self, text: str, today: date) -> Extraction:
        try:
            result = self.primary.extract(text, today)
            self.last_source = self.primary.name
            return result
        except LLMError as exc:
            reason = exc.reason
        except Exception as exc:  # any provider failure must not break a turn
            reason = type(exc).__name__
        logger.warning("LLM extraction failed (%s); using rules fallback", reason)
        self.last_source = "rules_fallback"
        return self.fallback.extract(text, today)


def get_extractor(settings: Settings) -> Extractor:
    rules = RulesExtractor()
    if settings.llm_provider != "openai":
        return rules
    if not settings.openai_api_key:
        logger.warning("LLM_PROVIDER=openai but no OPENAI_API_KEY; using rules")
        return rules
    prompt = (settings.config_dir / PROMPT_FILE).read_text(encoding="utf-8")
    primary = OpenAIExtractor(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        timeout=settings.llm_timeout_seconds,
        task_ids=[task.id for task in default_task_types()],
        prompt_template=prompt,
    )
    return FallbackExtractor(primary, rules)


class TimedExtractor:
    # Records the latency of the last extraction for the /api/turn timings.
    def __init__(self, inner: Extractor) -> None:
        self.inner = inner
        self.name = inner.name
        self.last_ms = 0.0

    @property
    def last_source(self) -> str:
        return getattr(self.inner, "last_source", self.inner.name)

    def extract(self, text: str, today: date) -> Extraction:
        started = time.perf_counter()
        try:
            return self.inner.extract(text, today)
        finally:
            self.last_ms = round((time.perf_counter() - started) * 1000, 1)


__all__ = [
    "Extractor",
    "FallbackExtractor",
    "LLMError",
    "OpenAIExtractor",
    "RulesExtractor",
    "get_extractor",
    "TimedExtractor",
    "to_initials",
]
