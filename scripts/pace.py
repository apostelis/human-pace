#!/usr/bin/env python3
"""/pace: show and change the human-pace switches."""
from __future__ import annotations

import sys
from datetime import datetime
from typing import List, Optional

import pace_config

USAGE = """Usage:
  /pace                        show switches
  /pace <switch> on|off        switches: bionic, answerFirst, chunks, actionMarkers
  /pace length <n>             prose word cap, 0 = no cap
  /pace reset                  restore defaults
  /pace rate <1-5> [note]      log how the current setting feels
  /pace report                 average rating per setting
Notes cannot contain double quotes, backticks or $."""

SWITCH_NAMES = {name.lower(): name for name in pace_config.SWITCHES}


def describe(cfg: dict) -> str:
    parts = [f"{name} {'on' if cfg[name] else 'off'}" for name in pace_config.SWITCHES]
    parts.append(f"length {cfg['length'] or 'no cap'}")
    return " · ".join(parts)


def _save(cfg: dict) -> str:
    try:
        pace_config.save_config(cfg)
    except OSError as e:
        return f"Could not save {pace_config.config_path()}: {e.strerror}"
    return f"human-pace: {describe(cfg)}\nApplies from your next prompt."


def run(args: List[str], now: Optional[datetime] = None) -> str:
    cfg, error = pace_config.load_config()
    if not args:
        warning = f"\n(Config was invalid: {error}. Showing defaults; any change rewrites it.)" if error else ""
        return f"human-pace: {describe(cfg)}{warning}"
    command, rest = args[0].lower(), args[1:]
    if command in SWITCH_NAMES and len(rest) == 1 and rest[0].lower() in ("on", "off"):
        cfg[SWITCH_NAMES[command]] = rest[0].lower() == "on"
        return _save(cfg)
    if command == "length" and len(rest) == 1 and rest[0].isdigit():
        cfg["length"] = int(rest[0])
        return _save(cfg)
    if command == "reset" and not rest:
        return _save(pace_config.defaults())
    return USAGE


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(run(" ".join(argv).split()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
