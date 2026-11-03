import re
import unicodedata

BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
TOKEN_RE = re.compile(r"[a-z]+|\d+|[\u0980-\u09ff\u200c\u200d]+")

CASE_SUFFIXES = {
    # Bengali script suffixes
    "কে",
    "র",
    "ের",
    "এর",
    "তে",
    "ে",
    "এ",
    "য়",
    "য়ে",
    "দের",
    "দেরকে",
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
        stripped = remainder.lstrip("-–—")
        if stripped in CASE_SUFFIXES:
            return True
    return False


def contains_phrase(normalised: str, phrase: str, max_gap: int = 3) -> bool:
    phrase_tokens = tokenize(normalise(phrase))
    if not phrase_tokens:
        return False
    text_tokens = tokenize(normalised)
    p_len = len(phrase_tokens)
    if len(text_tokens) < p_len:
        return False

    if p_len == 1:
        target = phrase_tokens[0]
        return any(_token_matches(t, target) for t in text_tokens)

    for i in range(len(text_tokens)):
        if _token_matches(text_tokens[i], phrase_tokens[0]):
            curr_pos = i
            matched = True
            for p_idx in range(1, p_len):
                target = phrase_tokens[p_idx]
                found = False
                for next_pos in range(curr_pos + 1, min(curr_pos + max_gap + 2, len(text_tokens))):
                    if _token_matches(text_tokens[next_pos], target):
                        curr_pos = next_pos
                        found = True
                        break
                if not found:
                    matched = False
                    break
            if matched:
                return True
    return False
