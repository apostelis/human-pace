#!/usr/bin/env python3
"""Render explicitly supplied plain prose as an experimental HTML fragment."""
from __future__ import annotations

import argparse
import html
import re
import sys

MODES = ("color", "weight", "both")
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def render(text: str, mode: str = "both") -> str:
    if mode not in MODES:
        raise ValueError("mode must be color, weight, or both")

    def word(match):
        token = match.group()
        count = sum(c.isalpha() for c in token)
        prefix = max(1, -(-count // 3) if count <= 5 else count // 3)
        chars, index = [], 0
        for c in token:
            weight = round(800 - 400 * index / max(count - 1, 1)) if c.isalpha() else 400
            if mode == "color":
                weight = 800 if c.isalpha() and index < prefix else 400
            chars.append(f'<span style="font-weight:{weight}">{html.escape(c)}</span>')
            if c.isalpha():
                index += 1
        if mode == "color":
            # Apostrophes do not count toward the prefix.
            split = next((i for i in range(len(token)) if sum(c.isalpha() for c in token[:i]) >= prefix), len(token))
            return '<span class="hp-word"><span class="hp-color">' + ''.join(chars[:split]) + '</span>' + ''.join(chars[split:]) + '</span>'
        cls = "hp-word hp-both" if mode == "both" else "hp-word"
        return f'<span class="{cls}">' + ''.join(chars) + '</span>'

    pieces, end = [], 0
    for match in WORD.finditer(text):
        pieces.extend((html.escape(text[end:match.start()]), word(match)))
        end = match.end()
    pieces.append(html.escape(text[end:]))
    return '''<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto+Flex:wght@100..1000&display=swap');
.hp-gradient {color-scheme:light dark;--hp-ink:light-dark(#202124,#eeeeee);--hp-purple:light-dark(#7839aa,#d0a0ff);--hp-blue:light-dark(#1767aa,#80c8ff);color:var(--hp-ink);font-family:'Roboto Flex',sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;font-kerning:none;font-variant-ligatures:none}
.hp-gradient .hp-word {display:inline-block}
@supports (background-clip:text) {
.hp-gradient .hp-color,.hp-gradient .hp-both {background:linear-gradient(90deg,var(--hp-purple),var(--hp-blue));background-clip:text;color:transparent}
.hp-gradient .hp-both {background-image:linear-gradient(90deg,var(--hp-purple),var(--hp-blue) 40%,var(--hp-ink) 85%)}
}
</style>
<div class="hp-gradient">''' + ''.join(pieces) + '</div>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="both")
    args = parser.parse_args()
    sys.stdout.write(render(sys.stdin.read(), args.mode))


if __name__ == "__main__":
    main()
