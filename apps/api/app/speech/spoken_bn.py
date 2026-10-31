"""Bengali spoken number conversion for TTS (Timbre).

Converts digits into spoken Bengali words to ensure proper pronunciation.
# NEEDS NATIVE SPEAKER REVIEW: Regional Bengali (West Bengal / Kolkata) usage
# for colloquial vs formal numbers (e.g. বিশ vs কুড়ি, নিরানব্বই vs উনশতক, একশত vs একশ).
"""

import re

BN_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Numbers 0 to 100 in Bengali words.
# NEEDS NATIVE SPEAKER REVIEW: Check 11-99 colloquial forms in rural Bengal.
WORDS_0_TO_100: dict[int, str] = {
    0: "শূন্য",
    1: "এক",
    2: "দুই",
    3: "তিন",
    4: "চার",
    5: "পাঁচ",
    6: "ছয়",
    7: "সাত",
    8: "আট",
    9: "নয়",
    10: "দশ",
    11: "এগারো",
    12: "বারো",
    13: "তেরো",
    14: "চৌদ্দ",
    15: "পনেরো",
    16: "ষোলো",
    17: "সতেরো",
    18: "আঠারো",
    19: "উনিশ",
    20: "বিশ",
    21: "একুশ",
    22: "বাইশ",
    23: "তেইশ",
    24: "চব্বিশ",
    25: "পঁচিশ",
    26: "ছাব্বিশ",
    27: "সাতাশ",
    28: "আঠাশ",
    29: "ঊনত্রিশ",
    30: "ত্রিশ",
    31: "একত্রিশ",
    32: "বত্রিশ",
    33: "তেত্রিশ",
    34: "চৌত্রিশ",
    35: "পঁয়ত্রিশ",
    36: "ছত্রিশ",
    37: "সাঁইত্রিশ",
    38: "আটত্রিশ",
    39: "ঊনচল্লিশ",
    40: "চল্লিশ",
    41: "একচল্লিশ",
    42: "বিয়াল্লিশ",
    43: "তেতাল্লিশ",
    44: "চুয়াল্লিশ",
    45: "পঁয়তাল্লিশ",
    46: "ছেচল্লিশ",
    47: "সাতচল্লিশ",
    48: "আটচল্লিশ",
    49: "ঊনপঞ্চাশ",
    50: "পঞ্চাশ",
    51: "একান্ন",
    52: "বায়ান্ন",
    53: "তিপ্পান্ন",
    54: "চুয়ান্ন",
    55: "পঞ্চান্ন",
    56: "ছাপ্পান্ন",
    57: "সাতান্ন",
    58: "আটান্ন",
    59: "ঊনষাট",
    60: "ষাট",
    61: "একষট্টি",
    62: "বাষট্টি",
    63: "তেষট্টি",
    64: "চৌষট্টি",
    65: "পঁয়ষট্টি",
    66: "ছেষট্টি",
    67: "সাতষট্টি",
    68: "আটষট্টি",
    69: "ঊনসত্তর",
    70: "সত্তর",
    71: "একাত্তর",
    72: "বাহাত্তর",
    73: "তিয়াত্তর",
    74: "চুয়াত্তর",
    75: "পঁচাত্তর",
    76: "ছিয়াত্তর",
    77: "সাতাত্তর",
    78: "আটাত্তর",
    79: "ঊনআশি",
    80: "আশি",
    81: "একাশি",
    82: "বিরাশি",
    83: "তিরাশি",
    84: "চুরাশি",
    85: "পঁচাশি",
    86: "ছিয়াশি",
    87: "সাতাশি",
    88: "আটাশি",
    89: "ঊননব্বই",
    90: "নব্বই",
    91: "একানব্বই",
    92: "বিরানব্বই",
    93: "তিরানব্বই",
    94: "চুরানব্বই",
    95: "পঁচানব্বই",
    96: "ছিয়ানব্বই",
    97: "সাতানব্বই",
    98: "আটানব্বই",
    99: "নিরানব্বই",
    100: "একশত",
}


def int_to_spoken_bn(n: int) -> str:
    """Convert an integer to Bengali spoken words."""
    if n in WORDS_0_TO_100:
        return WORDS_0_TO_100[n]

    if n < 0:
        return f"মাইনাস {int_to_spoken_bn(-n)}"

    if 101 <= n < 1000:
        hundreds = n // 100
        rem = n % 100
        prefix = f"{int_to_spoken_bn(hundreds)}শত"
        if rem == 0:
            return prefix
        return f"{prefix} {int_to_spoken_bn(rem)}"

    if 1000 <= n < 100_000:
        thousands = n // 1000
        rem = n % 1000
        t_word = f"{int_to_spoken_bn(thousands)} হাজার"
        if rem == 0:
            return t_word
        return f"{t_word} {int_to_spoken_bn(rem)}"

    if 100_000 <= n < 10_000_000:
        lakhs = n // 100_000
        rem = n % 100_000
        l_word = f"{int_to_spoken_bn(lakhs)} লাখ"
        if rem == 0:
            return l_word
        return f"{l_word} {int_to_spoken_bn(rem)}"

    # For larger numbers, speak digits individually as fallback
    # NEEDS NATIVE SPEAKER REVIEW
    return " ".join(WORDS_0_TO_100.get(int(d), d) for d in str(n))


def _parse_digits(digits_str: str) -> int:
    ascii_digits = digits_str.translate(BN_TO_ASCII)
    return int(ascii_digits)


def number_to_spoken_bn(text: str) -> str:
    """Replace numbers and currency amounts in text with spoken Bengali words.

    Non-numeric text is left strictly untouched.
    """
    if not text:
        return text

    # Currency replacements:
    # 1. ₹200 or ₹ 200 -> "দুইশত টাকা"
    result = re.sub(
        r"₹\s*([0-9০-৯]+)",
        lambda m: f"{int_to_spoken_bn(_parse_digits(m.group(1)))} টাকা",
        text,
    )
    # 2. 200 taka or 200 TAKA -> "দুইশত টাকা"
    result = re.sub(
        r"\b([0-9০-৯]+)\s*taka\b",
        lambda m: f"{int_to_spoken_bn(_parse_digits(m.group(1)))} টাকা",
        result,
        flags=re.IGNORECASE,
    )
    # 3. 200 টাকা -> "দুইশত টাকা"
    result = re.sub(
        r"([0-9০-৯]+)\s*টাকা\b",
        lambda m: f"{int_to_spoken_bn(_parse_digits(m.group(1)))} টাকা",
        result,
    )

    # General number replacement (dates, ordinals, counts, years)
    result = re.sub(
        r"([0-9০-৯]+)",
        lambda m: int_to_spoken_bn(_parse_digits(m.group(1))),
        result,
    )

    return result

