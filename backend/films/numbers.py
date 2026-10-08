"""Turn numbers written in different ways into digits, so searches match
however a number is written: "twelve angry men" / "12 angry men",
"rocky ii" / "rocky 2", "second act" / "2nd act". Used only on the normalised
search text, never on titles shown to users."""

import re

UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}  # fmt: skip
TEENS = {
    "zero": 0, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}  # fmt: skip
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip

# Ordinal words mean the same as their numbers for searching: "first" = "one".
ORDINALS = {
    "first": "one", "second": "two", "third": "three", "fourth": "four",
    "fifth": "five", "sixth": "six", "seventh": "seven", "eighth": "eight",
    "ninth": "nine", "tenth": "ten", "eleventh": "eleven", "twelfth": "twelve",
    "thirteenth": "thirteen", "fourteenth": "fourteen", "fifteenth": "fifteen",
    "sixteenth": "sixteen", "seventeenth": "seventeen",
    "eighteenth": "eighteen", "nineteenth": "nineteen",
    "twentieth": "twenty", "thirtieth": "thirty", "fortieth": "forty",
    "fiftieth": "fifty", "sixtieth": "sixty", "seventieth": "seventy",
    "eightieth": "eighty", "ninetieth": "ninety",
    "hundredth": "hundred", "thousandth": "thousand",
}  # fmt: skip

# "1st", "22nd", "3rd", "4th" -> "1", "22", "3", "4".
DIGIT_ORDINAL = re.compile(r"^(\d+)(?:st|nd|rd|th)$")

# Roman numerals from II to XXXIX. A lone "i" is left alone: it's usually the
# word "I" ("10 Things I Hate About You"), and "Part I" titles are rare.
ROMAN = re.compile(r"^(x{0,3})(ix|iv|v?i{0,3})$")
ROMAN_VALUES = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
                "viii": 8, "ix": 9, "": 0}  # fmt: skip

# Which kind of number may follow which, within one number.
# e.g. "twenty" then "one" (21), but not "one" then "twenty".
CAN_FOLLOW = {
    "unit": {None, "tens", "hundred", "thousand"},
    "teen": {None, "hundred", "thousand"},
    "tens": {None, "hundred", "thousand"},
    "hundred": {None, "unit", "teen"},
    "thousand": {None, "unit", "teen", "tens", "hundred"},
}


def roman_to_int(word):
    match = ROMAN.match(word)
    if not match or word == "i" or not word:
        return None
    return 10 * len(match[1]) + ROMAN_VALUES[match[2]]


def standardise(word):
    """Rewrite a word so every spelling of a number reads the same way:
    ordinals become cardinals, and Roman numerals and "21st" become digits."""
    word = ORDINALS.get(word, word)
    if match := DIGIT_ORDINAL.match(word):
        return match[1]
    if (value := roman_to_int(word)) is not None:
        return str(value)
    return word


def _kind(word):
    """The kind of number a word is, or None if it isn't one."""
    if word in UNITS:
        return "unit"
    if word in TEENS:
        return "teen"
    if word in TENS:
        return "tens"
    if word in ("hundred", "thousand"):
        return word
    if word.isdigit() and len(word) <= 2:
        value = int(word)
        # So "50 first dates" (-> "50 one") and "fifty first dates" both give 51.
        if value < 10:
            return "unit"
        if value < 20:
            return "teen"
        if value % 10 == 0:
            return "tens"
    return None


def _value(word):
    if word.isdigit():
        return int(word)
    return UNITS.get(word) or TEENS.get(word) or TENS.get(word) or 0


class _Number:
    def __init__(self):
        self.total = 0  # thousands already counted
        self.current = 0  # the part below a thousand
        self.last = None
        self.seen_thousand = False
        self.all_digits = True  # made only of digits, e.g. "50"

    def can_take(self, kind):
        if kind == "thousand" and self.seen_thousand:
            return False
        return self.last in CAN_FOLLOW[kind]

    def take(self, word, kind):
        if not word.isdigit():
            self.all_digits = False
        if kind in ("unit", "teen", "tens"):
            self.current += _value(word)
        elif kind == "hundred":
            self.current = (self.current or 1) * 100
        else:  # thousand
            self.total += (self.current or 1) * 1000
            self.current = 0
            self.seen_thousand = True
        self.last = kind


def words_to_digits(words):
    """['twelve', 'angry', 'men'] -> ['12', 'angry', 'men'];
    ['two', 'thousand', 'and', 'one'] -> ['2001'];
    ['nineteen', 'eighty', 'four'] -> ['1984'];
    ['rocky', 'ii'] -> ['rocky', '2']."""
    words = [standardise(word) for word in words]
    out = []  # (word, value if it was a spelled-out number else None)
    number = None

    def flush():
        value = number.total + number.current
        spelled_out = not number.all_digits
        # Years said as two numbers: "nineteen eighty four", "twenty twenty".
        if spelled_out and out and out[-1][1] is not None:
            previous = out[-1][1]
            if 10 <= previous <= 99 and 10 <= value <= 99 and not number.seen_thousand:
                out[-1] = (str(previous * 100 + value), None)
                return
        out.append((str(value), value if spelled_out else None))

    for i, word in enumerate(words):
        kind = _kind(word)
        next_kind = _kind(words[i + 1]) if i + 1 < len(words) else None
        # "and" joins parts of a number: "one hundred and one" -> 101.
        if (
            word == "and"
            and number
            and number.last in ("hundred", "thousand")
            and next_kind in ("unit", "teen", "tens")
        ):
            continue
        if kind and number and number.can_take(kind):
            number.take(word, kind)
            continue
        if number:
            flush()
            number = None
        if kind:
            number = _Number()
            number.take(word, kind)
        else:
            out.append((word, None))
    if number:
        flush()
    return [word for word, _ in out]
