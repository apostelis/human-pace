"""Reference bionic approaches (bionic approaches spec §2), shared by the tests and the compliance harness."""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, List, Tuple

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")          # letters, internal apostrophes allowed
FENCE = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")
PATH_LIKE = re.compile(r"[/\\@]|\w[.:]\w")                 # src/app.py, e.g., user@host
CAMEL = re.compile(r"[a-z][A-Z]")                         # answerFirst: an identifier, not prose
SEPARATORS = re.compile(r"[\s\-–—]+")                     # whitespace and hyphens split words


def bold_length(word: str) -> int:
    letters = sum(1 for c in word if c.isalpha())
    third = -(-letters // 3) if letters <= 5 else letters // 3  # short words round up, longer ones down
    return max(1, third)


APPROACHES = ("third", "vowels", "consonants", "third+anchor")
VOWELS = frozenset("aeiouy")


def is_vowel(c: str) -> bool:
    return c.isalpha() and unicodedata.normalize("NFD", c)[0].lower() in VOWELS


def _render(word: str, marks: List[bool]) -> str:
    """Wrap each run of marked characters in ** so adjacent bold letters form one span."""
    out, bold = [], False
    for c, marked in zip(word, marks):
        if marked != bold:
            out.append("**")
            bold = marked
        out.append(c)
    if bold:
        out.append("**")
    return "".join(out)


def _third_marks(word: str) -> List[bool]:
    target, seen, marks = bold_length(word), 0, []
    for c in word:
        if c.isalpha() and seen < target:
            seen += 1
            marks.append(True)
        else:
            marks.append(False)
    return marks


def third_word(word: str) -> str:
    return _render(word, _third_marks(word))


def vowels_word(word: str) -> str:
    return _render(word, [is_vowel(c) for c in word])


def consonants_word(word: str) -> str:
    return _render(word, [c.isalpha() and not is_vowel(c) for c in word])


def anchor_word(word: str, anchor_trigger: int = 8) -> str:
    marks = _third_marks(word)
    letters = [i for i, c in enumerate(word) if c.isalpha()]
    if len(letters) >= anchor_trigger:
        consonants = [i for i in letters if not is_vowel(word[i])]
        nth_from_end = 1 if is_vowel(word[letters[-1]]) else 2
        if len(consonants) >= nth_from_end:
            marks[consonants[-nth_from_end]] = True
    return _render(word, marks)


def word_function(approach: str = "third", anchor_trigger: int = 8) -> Callable[[str], str]:
    if approach == "vowels":
        return vowels_word
    if approach == "consonants":
        return consonants_word
    if approach == "third+anchor":
        return lambda word: anchor_word(word, anchor_trigger)
    return third_word


def to_bionic(text: str, approach: str = "third", anchor_trigger: int = 8) -> str:
    fn = word_function(approach, anchor_trigger)
    return WORD.sub(lambda m: fn(m.group(0)), text)


def prose_only(markdown: str) -> str:
    """Drop what bionic never applies to: code, URLs, headings and tables."""
    text = INLINE_CODE.sub("", FENCE.sub("", markdown))
    text = URL.sub("", text)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", "|")))


def score_bionic(markdown: str, approach: str = "third", anchor_trigger: int = 8) -> Tuple[int, int]:
    """Return (correct, total) prose words, judged against the chosen approach."""
    expected = word_function(approach, anchor_trigger)
    correct = total = 0
    for chunk in SEPARATORS.split(prose_only(markdown)):
        if not chunk or PATH_LIKE.search(chunk.replace("**", "")):
            continue
        actual = re.sub(r"[^\w*'’]", "", chunk).strip("'’")
        plain = actual.replace("**", "")
        if not WORD.fullmatch(plain) or CAMEL.search(plain):
            continue
        total += 1
        correct += actual == expected(plain)
    return correct, total


def bold_in_code(markdown: str) -> bool:
    spans = FENCE.findall(markdown) + INLINE_CODE.findall(FENCE.sub("", markdown))
    return any("**" in span for span in spans)
