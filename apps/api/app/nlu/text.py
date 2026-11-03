import re
import unicodedata

BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
TOKEN_RE = re.compile(r"[a-z]+|\d+|[\u0980-\u09ff\u200c\u200d]+")

CASE_SUFFIXES = {
    # Bengali script suffixes
    "কে",
    "র",
    "ের",
    "তে",
    "ে",
    "য়",
    "য়ে",
    "টা",
    "টি",
    "টো",
    "গুলো",
    "গুলি",
    # Latin script suffixes
    "ke",
    "er",
    "r",
    "te",
    "e",
    "ta",
    "ti",
    "to",
    "s",
}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(BENGALI_DIGITS)
    text = re.sub(r"[।.,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def tokenize(normalised: str) -> list[str]:
    return TOKEN_RE.findall(normalised)


def _token_matches(text_token: str, phrase_token: str) -> bool:
    if text_token == phrase_token:
        return True
    if text_token.startswith(phrase_token):
        remainder = text_token[len(phrase_token) :]
        if remainder in CASE_SUFFIXES:
            return True
        if remainder.startswith("-") and remainder[1:] in CASE_SUFFIXES:
            return True
    return False


def contains_phrase(normalised: str, phrase: str) -> bool:
    phrase_tokens = tokenize(normalise(phrase))
    if not phrase_tokens:
        return False
    text_tokens = tokenize(normalised)
    p_len = len(phrase_tokens)
    if len(text_tokens) < p_len:
        return False

    for i in range(len(text_tokens) - p_len + 1):
        if all(text_tokens[i + j] == phrase_tokens[j] for j in range(p_len - 1)):
            if _token_matches(text_tokens[i + p_len - 1], phrase_tokens[-1]):
                return True
    return False
