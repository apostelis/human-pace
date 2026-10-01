"""Reference bionic algorithm (spec §3), shared by the tests and the compliance harness."""
from __future__ import annotations

import re
from typing import Tuple

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")          # letters, internal apostrophes allowed
FENCE = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")
PATH_LIKE = re.compile(r"[/\\@]|\w[.:]\w")                 # src/app.py, e.g., user@host
CAMEL = re.compile(r"[a-z][A-Z]")                         # answerFirst: an identifier, not prose
SEPARATORS = re.compile(r"[\s\-–—]+")                     # whitespace and hyphens split words


def bold_length(word: str) -> int:
    letters = sum(1 for c in word if c.isalpha())
    return max(1, letters // 3)


def bionic_word(word: str) -> str:
    target, seen = bold_length(word), 0
    for i, c in enumerate(word):
        if c.isalpha():
            seen += 1
            if seen == target:
                return f"**{word[:i + 1]}**{word[i + 1:]}"
    return word


def to_bionic(text: str) -> str:
    return WORD.sub(lambda m: bionic_word(m.group(0)), text)


def prose_only(markdown: str) -> str:
    """Drop what bionic never applies to: code, URLs, headings and tables."""
    text = INLINE_CODE.sub("", FENCE.sub("", markdown))
    text = URL.sub("", text)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", "|")))


def score_bionic(markdown: str) -> Tuple[int, int]:
    """Return (correct, total) prose words, judged against bionic_word."""
    correct = total = 0
    for chunk in SEPARATORS.split(prose_only(markdown)):
        if not chunk or PATH_LIKE.search(chunk.replace("**", "")):
            continue
        actual = re.sub(r"[^\w*'’]", "", chunk).strip("'’")
        plain = actual.replace("**", "")
        if not WORD.fullmatch(plain) or CAMEL.search(plain):
            continue
        total += 1
        correct += actual == bionic_word(plain)
    return correct, total


def bold_in_code(markdown: str) -> bool:
    spans = FENCE.findall(markdown) + INLINE_CODE.findall(FENCE.sub("", markdown))
    return any("**" in span for span in spans)
