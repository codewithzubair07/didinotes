from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.settings import get_settings


class ConfigError(ValueError):
    pass


class TaskType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    bn_label: str = Field(min_length=1)
    en_label: str = Field(min_length=1)
    required_documents: list[str] = Field(min_length=1, max_length=2)
    incentive_inr: int | None = Field(default=None, ge=0)
    verified: bool = False

    @model_validator(mode="after")
    def amount_requires_verification(self):
        if self.incentive_inr is not None and not self.verified:
            raise ValueError(f"{self.id}: incentive_inr is set but verified is false")
        return self


class IncentiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_types: list[TaskType] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_are_unique(self):
        ids = [task.id for task in self.task_types]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task type ids")
        return self


class DateWords(BaseModel):
    today: list[str]
    yesterday: list[str]
    tomorrow: list[str]
    kal: list[str]
    porshu: list[str]


class Lexicon(BaseModel):
    task_keywords: dict[str, list[str]]
    number_words: dict[int, list[str]]
    date_words: DateWords
    yes_words: list[str]
    no_words: list[str]
    correction_words: list[str]
    count_words: list[str]
    clinical_keywords: list[str]
    non_name_words: list[str]


def _read_yaml(path: Path) -> object:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_incentives(path: Path) -> list[TaskType]:
    try:
        config = IncentiveConfig.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"Invalid incentives config {path}: {exc}") from exc
    return config.task_types


def load_lexicon(path: Path) -> Lexicon:
    try:
        return Lexicon.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"Invalid lexicon config {path}: {exc}") from exc


@lru_cache
def default_lexicon() -> Lexicon:
    return load_lexicon(get_settings().config_dir / "lexicon.yaml")


@lru_cache
def default_task_types() -> list[TaskType]:
    return load_incentives(get_settings().config_dir / "incentives.yaml")


def load_strings(path: Path) -> dict[str, object]:
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid i18n config {path}: top level must be a mapping")
    return data


@lru_cache
def default_strings() -> dict[str, object]:
    return load_strings(get_settings().config_dir / "i18n.yaml")
