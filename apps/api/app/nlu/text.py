import re
import unicodedata

BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
TOKEN_RE = re.compile(r"[a-z]+|\d+|[\u0980-\u09ff\u200c\u200d]+")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(BENGALI_DIGITS)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def tokenize(normalised: str) -> list[str]:
    return TOKEN_RE.findall(normalised)


def contains_phrase(normalised: str, phrase: str) -> bool:
    phrase_tokens = tokenize(normalise(phrase))
    if not phrase_tokens:
        return False
    return f" {' '.join(phrase_tokens)} " in f" {' '.join(tokenize(normalised))} "
