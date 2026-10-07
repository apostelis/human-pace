#!/usr/bin/env python3
"""SessionStart and UserPromptSubmit hook: add the enabled human-pace rules to the model's context.

The rules are sent once per session (SessionStart also fires after compaction and resume), and again
on a prompt only when /pace has changed them, so they don't appear above every reply.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Mapping, Optional, Tuple

import pace_config

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
# What to say first, then shape, then how the words look. "bionic" picks its file by approach.
FRAGMENTS = (
    ("answerFirst", "answer-first.md"),
    ("chunks", "chunks.md"),
    ("actionMarkers", "action-markers.md"),
    ("length", "length.md"),
    ("bionic", None),
)
BIONIC_FRAGMENTS = {
    "third": "bionic-third.md",
    "vowels": "bionic-vowels.md",
    "consonants": "bionic-consonants.md",
    "third+anchor": "bionic-third-anchor.md",
}
PACE_COMMAND = re.compile(r"^\s*/(human-pace:)?pace(\s|$)")
SESSION_ID = re.compile(r"^[\w-]{1,128}$")  # also keeps the id safe to use as a file name
STATE_MAX_AGE_SECONDS = 7 * 24 * 3600
UPDATED_PREFIX = "human-pace rules changed; these replace the earlier ones.\n"
OFF_NOTICE = "human-pace is now off: ignore its earlier formatting rules."
REMINDER_PREFIX = "human-pace rules still in effect:\n"


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
        if key == "bionic":
            name = BIONIC_FRAGMENTS.get(cfg.get("bionicApproach"), BIONIC_FRAGMENTS["third"])
        text = read_fragment(rules_dir, name)
        if text:
            text = text.replace("{length}", str(cfg["length"]))
            parts.append(text.replace("{anchorTrigger}", str(cfg.get("anchorTrigger", 8))))
    if cfg.get("bionic") and cfg.get("bionicGradient", "off") != "off":
        gradient = read_fragment(rules_dir, "experimental-gradient.md")
        if gradient:
            parts.append(gradient.replace("{gradient}", cfg["bionicGradient"]))
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
    # claude -p and the Agent SDK set sdk-*; their output feeds scripts, not a reader. HUMAN_PACE=1 forces on.
    if env.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk") and env.get("HUMAN_PACE") != "1":
        return True
    prompt = hook_input.get("prompt")
    return isinstance(prompt, str) and PACE_COMMAND.match(prompt) is not None


def hook_output(text: str, event: str = "UserPromptSubmit") -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def state_dir() -> Path:
    return Path(os.environ.get("HUMAN_PACE_STATE", "~/.claude/human-pace-state")).expanduser()


def _last_sent(session_id: str) -> Optional[Tuple[str, int]]:
    """Return (digest of the rules last sent, prompts since then), or None without state."""
    try:
        lines = (state_dir() / session_id).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    if not lines:
        return None
    count = lines[1] if len(lines) > 1 else ""
    # 0.5 files hold only the digest; ASCII digits only, since int("²") raises.
    return lines[0], int(count) if re.fullmatch(r"[0-9]+", count) else 0


def _remember(session_id: str, digest: str, count: int = 0) -> None:
    try:
        state_dir().mkdir(parents=True, exist_ok=True)
        (state_dir() / session_id).write_text(f"{digest}\n{count}", encoding="utf-8")
    except OSError:
        pass  # Without state every prompt re-sends the rules, which is the safe direction.


def _prune_state() -> None:
    cutoff = time.time() - STATE_MAX_AGE_SECONDS
    try:
        for entry in state_dir().iterdir():
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
    except OSError:
        pass


def rules_to_send(event: str, rules: str, session_id: object, drift_guard: int = 0) -> str:
    """Send the rules at session start, again when they change, and every drift_guard prompts."""
    if not isinstance(session_id, str) or not SESSION_ID.match(session_id):
        return rules  # Can't track this session: fall back to every prompt.
    digest = hashlib.sha256(rules.encode("utf-8")).hexdigest()
    if event == "SessionStart":
        _prune_state()
        _remember(session_id, digest)
        return rules
    last = _last_sent(session_id)
    previous, count = last if last else (None, 0)
    if previous == digest:
        count += 1
        if drift_guard and rules and count >= drift_guard:
            _remember(session_id, digest)
            return REMINDER_PREFIX + rules  # rules sent once fade over a long session
        _remember(session_id, digest, count)
        return ""
    _remember(session_id, digest)
    if previous is None:
        return rules  # Plugin installed mid-session, or state lost.
    return UPDATED_PREFIX + rules if rules else OFF_NOTICE


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
        event = "SessionStart" if hook_input.get("hook_event_name") == "SessionStart" else "UserPromptSubmit"
        cfg, error = pace_config.load_effective_config(env=env)
        text = rules_to_send(event, build_rules(cfg, config_error=error), hook_input.get("session_id"),
                             cfg["driftGuard"])
        if text:
            stdout.write(hook_output(text, event))
    except Exception:
        pass  # Never block the user's prompt.
    return 0


if __name__ == "__main__":
    sys.exit(main())
