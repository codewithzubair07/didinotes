import re

from app.config_loader import Lexicon, default_lexicon
from app.nlu.text import normalise, tokenize

CLASSIFIER_SUFFIXES = (
    r"(?:'|-|\s)?"
    r"(?:"
    r"(?:jon|জন)(?:'|-|\s)?(?:ke|কে|er|ের|র)?|"
    r"(?:ta|টা)(?:'|-|\s)?(?:ke|কে|r|র|te|তে)?|"
    r"(?:to|টো)(?:'|-|\s)?(?:ke|কে|r|র|te|তে)?|"
    r"(?:ti|টি)(?:'|-|\s)?(?:ke|কে|r|র|te|তে)?|"
    r"(?:te|টে)(?:'|-|\s)?(?:ke|কে|r|র)?|"
    r"ke|কে|er|ের|র|te|তে"
    r")?"
)

EXTRA_NUMBER_WORDS: list[tuple[str, int]] = [
    ("দুটো", 2),
    ("duto", 2),
    ("দু", 2),
    ("du", 2),
]


def number_index(lexicon: Lexicon) -> dict[str, int]:
    return {
        normalise(word): value
        for value, words in lexicon.number_words.items()
        for word in words
    }


def parse_number(text: str, lexicon: Lexicon | None = None) -> int | None:
    lex = lexicon or default_lexicon()
    norm = normalise(text)

    # 1. Direct digits in tokens
    for token in tokenize(norm):
        if token.isdigit():
            return int(token)

    # 2. Number words and compound forms with classifier suffixes (e.g. duijon, দুইজন, ekta)
    word_pairs: list[tuple[str, int]] = []
    for val, words in lex.number_words.items():
        for w in words:
            word_pairs.append((normalise(w), val))
    for alias, val in EXTRA_NUMBER_WORDS:
        if not any(w == alias for w, _ in word_pairs):
            word_pairs.append((alias, val))

    word_pairs.sort(key=lambda x: len(x[0]), reverse=True)
    for word, val in word_pairs:
        pattern = re.compile(
            rf"(?:^|[^\u0980-\u09ff\w])({re.escape(word)}){CLASSIFIER_SUFFIXES}(?=$|[^\u0980-\u09ff\w])",
            re.IGNORECASE,
        )
        if pattern.search(norm):
            return val

    # 3. Exact match in number_index
    index = number_index(lex)
    for token in tokenize(norm):
        if token in index:
            return index[token]
    return None
