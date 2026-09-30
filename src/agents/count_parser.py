"""Deterministic test-case count extraction from the user query."""
import re
from typing import Optional

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}

def _number_word_pattern():
    return "|".join(sorted(NUMBER_WORDS.keys(), key=len, reverse=True))


TYPE_REGEX = (
    r"(functional|function|integration|"
    r"e[\s\-]?2[\s\-]?e|end[\s\-]*to[\s\-]*end|end2end|"
    r"edge(?:\s*cases?)?)"
)

TC_WORD = r"(?:manual\s+)?(?:test[\s\-]*cases?|testcases?|scenarios?)"


def _to_int(raw) -> int:
    if raw is None:
        return 0
    text = str(raw).strip().lower()
    if text.isdigit():
        return int(text)
    return NUMBER_WORDS.get(text, 0)


def _canonical_type(raw) -> Optional[str]:
    key = re.sub(r"\s+", " ", str(raw or "").strip().lower())
    key = key.replace("-", " ")
    if key in {"functional", "function"}:
        return "functional"
    if key.startswith("edge"):
        return "edge"
    if key == "integration":
        return "integration"
    if "end to end" in key or "end2end" in key or re.sub(r"[\s\-]", "", key) in {"e2e"}:
        return "e2e"
    return None


def parse_user_testcase_request(user_input: str):
    """Parse explicit test-case quantities from the user query.

    Returns (overall_count, types) where types is a list of
    {"type": canonical, "count": n}. overall_count is 0 when unspecified.
    """
    text = user_input or ""
    if not text.strip():
        return 0, []

    per_type = {}
    type_pattern = re.compile(
        rf"\b(?P<num>\d+|{_number_word_pattern()})\s+(?P<typ>{TYPE_REGEX})"
        rf"(?:\s+{TC_WORD})?",
        re.IGNORECASE,
    )
    for match in type_pattern.finditer(text):
        n = _to_int(match.group("num"))
        key = _canonical_type(match.group("typ"))
        if n > 0 and key:
            per_type[key] = per_type.get(key, 0) + n

    type_after = re.compile(
        rf"\b(?P<typ>{TYPE_REGEX})\s*(?:[:x]|of)?\s*(?P<num>\d+|{_number_word_pattern()})\b",
        re.IGNORECASE,
    )
    for match in type_after.finditer(text):
        n = _to_int(match.group("num"))
        key = _canonical_type(match.group("typ"))
        if n > 0 and key and key not in per_type:
            per_type[key] = n

    types = [{"type": key, "count": n} for key, n in per_type.items()]
    if types:
        return sum(item["count"] for item in types), types

    overall = 0
    overall_pattern = re.compile(
        rf"\b(?:generate|create|give|write|make|need|want|prepare|produce)\s+"
        rf"(?:(?:a|an|only|exactly|about|around)\s+)?"
        rf"(?P<num>\d+|{_number_word_pattern()})\s+{TC_WORD}\b",
        re.IGNORECASE,
    )
    match = overall_pattern.search(text)
    if match:
        overall = _to_int(match.group("num"))
    if overall <= 0:
        bare = re.compile(
            rf"\b(?P<num>\d+|{_number_word_pattern()})\s+{TC_WORD}\b",
            re.IGNORECASE,
        )
        match = bare.search(text)
        if match:
            overall = _to_int(match.group("num"))
    if overall <= 0:
        single = re.compile(
            rf"\b(?:a|an|one|single)\s+(?:manual\s+)?(?:test[\s\-]*case|testcase|scenario)\b",
            re.IGNORECASE,
        )
        if single.search(text):
            overall = 1
    return overall, []
