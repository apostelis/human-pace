#!/usr/bin/env python3
"""UserPromptSubmit hook: add the enabled human-pace rules to the model's context."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping, Optional

import pace_config

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
# What to say first, then shape, then how the words look.
FRAGMENTS = (
    ("answerFirst", "answer-first.md"),
    ("chunks", "chunks.md"),
    ("actionMarkers", "action-markers.md"),
    ("length", "length.md"),
    ("bionic", "bionic.md"),
)
PACE_COMMAND = re.compile(r"^\s*/(human-pace:)?pace(\s|$)")


def read_fragment(rules_dir: Path, name: str) -> Optional[str]:
    try:
        return (rules_dir / name).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def build_rules(cfg: dict, rules_dir: Path = RULES_DIR, config_error: Optional[str] = None) -> str:
    parts = []
    for key, name in FRAGMENTS:
        if not cfg.get(key):
            continue
        text = read_fragment(rules_dir, name)
        if text:
            parts.append(text.replace("{length}", str(cfg["length"])))
    if parts:
        common = read_fragment(rules_dir, "common.md")
        if common:
            parts.insert(0, common)
    if config_error:
        parts.append(f"Also tell the user: {config_error}; human-pace is using defaults.")
    return "\n".join(parts)


def should_skip(hook_input: dict, env: Mapping[str, str]) -> bool:
    if env.get("HUMAN_PACE") == "0":
        return True
    prompt = hook_input.get("prompt")
    return isinstance(prompt, str) and PACE_COMMAND.match(prompt) is not None


def hook_output(rules: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": rules}})


def main(stdin=sys.stdin, stdout=sys.stdout, env: Mapping[str, str] = os.environ) -> int:
    try:
        try:
            hook_input = json.loads(stdin.read() or "{}")
        except ValueError:
            hook_input = {}
        if not isinstance(hook_input, dict):
            hook_input = {}
        if should_skip(hook_input, env):
            return 0
        cfg, error = pace_config.load_config()
        rules = build_rules(cfg, config_error=error)
        if rules:
            stdout.write(hook_output(rules))
    except Exception:
        pass  # Never block the user's prompt.
    return 0


if __name__ == "__main__":
    sys.exit(main())
