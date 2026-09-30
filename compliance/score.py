"""Score one reply against the enabled human-pace rules (spec §6.2)."""
from __future__ import annotations

import re
from typing import Dict, List

from bionic import bold_in_code, prose_only, score_bionic

SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
ENDS_CLOSED = re.compile(r"[.!?]['\")’]*$")
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s")
MARKER = "▶ You:"
BIONIC_THRESHOLD = 0.9


def _lines(text: str) -> List[str]:
    return [line for line in text.splitlines() if line.strip()]


def _sentences(text: str) -> int:
    text = text.replace("**", "").strip()
    if not text:
        return 0
    ends = len(SENTENCE_END.findall(text))
    return ends if ENDS_CLOSED.search(text) else ends + 1


def first_line_one_sentence(reply: str) -> bool:
    lines = _lines(reply)
    if not lines or lines[0].lstrip().startswith(("#", "```", "|")):
        return False
    return _sentences(lines[0]) <= 1


def paragraphs_within(reply: str, limit: int = 3) -> bool:
    for block in re.split(r"\n\s*\n", prose_only(reply)):
        prose = []
        for line in block.splitlines():
            if LIST_ITEM.match(line):
                if _sentences(line) > limit:
                    return False
            else:
                prose.append(line)
        if _sentences(" ".join(prose)) > limit:
            return False
    return True


def within_length(reply: str, limit: int) -> bool:
    if not limit:
        return True
    return len(prose_only(reply).replace("**", "").split()) <= limit


def action_line_last(reply: str) -> bool:
    lines = [line.replace("**", "") for line in _lines(reply)]
    marked = [i for i, line in enumerate(lines) if MARKER in line]
    return not marked or all(MARKER in line for line in lines[marked[0]:])


def bionic_ok(reply: str) -> bool:
    correct, total = score_bionic(reply)
    return total == 0 or correct / total >= BIONIC_THRESHOLD


def score_reply(reply: str, cfg: dict) -> Dict[str, bool]:
    results: Dict[str, bool] = {}
    if cfg.get("answerFirst"):
        results["answer first"] = first_line_one_sentence(reply)
    if cfg.get("chunks"):
        results["short paragraphs"] = paragraphs_within(reply)
    if cfg.get("length"):
        results["within length"] = within_length(reply, cfg["length"])
    if cfg.get("actionMarkers"):
        results["action line last"] = action_line_last(reply)
    if cfg.get("bionic"):
        results["bionic >= 90%"] = bionic_ok(reply)
        results["no bold in code"] = not bold_in_code(reply)
    return results
