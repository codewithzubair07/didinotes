from datetime import date, timedelta

from pydantic import BaseModel, Field

from app.config_loader import Lexicon, default_lexicon
from app.nlu.text import normalise, tokenize


class DateParse(BaseModel):
    date: date | None
    ambiguous: bool = False
    candidates: list[date] = Field(default_factory=list)


def date_index(lexicon: Lexicon) -> dict[str, str]:
    return {
        normalise(word): key
        for key, words in lexicon.date_words.model_dump().items()
        for word in words
    }


def _resolve(key: str, today: date) -> DateParse:
    if key == "today":
        return DateParse(date=today, candidates=[today])
    if key == "yesterday":
        return DateParse(date=today - timedelta(days=1), candidates=[today - timedelta(days=1)])
    if key == "tomorrow":
        return DateParse(date=today + timedelta(days=1), candidates=[today + timedelta(days=1)])
    if key == "kal":
        # Work diary: default to the past, never silently a future date.
        candidates = [today - timedelta(days=1), today + timedelta(days=1)]
        return DateParse(date=candidates[0], ambiguous=True, candidates=candidates)
    # porshu: default to the day before yesterday.
    candidates = [today - timedelta(days=2), today + timedelta(days=2)]
    return DateParse(date=candidates[0], ambiguous=True, candidates=candidates)


def parse_date(text: str, today: date, lexicon: Lexicon | None = None) -> DateParse:
    index = date_index(lexicon or default_lexicon())
    for token in tokenize(normalise(text)):
        if token in index:
            return _resolve(index[token], today)
    return DateParse(date=None)
