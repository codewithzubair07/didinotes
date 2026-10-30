from app.config_loader import Lexicon, default_lexicon
from app.nlu.text import normalise, tokenize


def number_index(lexicon: Lexicon) -> dict[str, int]:
    return {
        normalise(word): value
        for value, words in lexicon.number_words.items()
        for word in words
    }


def parse_number(text: str, lexicon: Lexicon | None = None) -> int | None:
    index = number_index(lexicon or default_lexicon())
    for token in tokenize(normalise(text)):
        if token.isdigit():
            return int(token)
        if token in index:
            return index[token]
    return None
