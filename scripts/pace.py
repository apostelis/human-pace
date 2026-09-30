#!/usr/bin/env python3
"""/pace: show and change the human-pace switches, and log and report ratings."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

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


def _ends_with_newline(path) -> bool:
    with path.open("rb") as log:
        log.seek(-1, 2)
        return log.read(1) == b"\n"


def rate(cfg: dict, rest: List[str], now: datetime) -> str:
    if not rest or not rest[0].isdigit() or not 1 <= int(rest[0]) <= 5:
        return USAGE
    entry = {"ts": now.isoformat(timespec="seconds"), "switches": cfg,
             "score": int(rest[0]), "note": " ".join(rest[1:])}
    path = pace_config.log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            # A crash mid-write leaves no trailing newline; don't glue this entry onto that fragment.
            prefix = "\n" if log.tell() and not _ends_with_newline(path) else ""
            log.write(prefix + json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        return f"Could not write rating log {path}: {e.strerror}"
    return f"Logged {entry['score']}/5 for: {describe(cfg)}"


def report() -> str:
    path = pace_config.log_path()
    try:
        # A crash can cut a line inside a multi-byte character; that line then fails to parse and is skipped.
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        lines = []
    except OSError as e:
        return f"Could not read rating log {path}: {e.strerror}"
    scores: Dict[str, List[int]] = {}
    settings: Dict[str, dict] = {}
    for line in lines:
        try:
            entry = json.loads(line)
            switches, score = entry["switches"], entry["score"]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(switches, dict) or not isinstance(score, int) or isinstance(score, bool):
            continue
        setting = {key: switches.get(key, default) for key, default in pace_config.DEFAULTS.items()}
        key = json.dumps(setting, sort_keys=True)
        scores.setdefault(key, []).append(score)
        settings[key] = setting
    if not scores:
        return "No ratings yet. Use /pace rate <1-5> [note]."
    rows = sorted(scores.items(), key=lambda item: -sum(item[1]) / len(item[1]))
    return "\n".join(
        f"{sum(s) / len(s):.1f} avg · {len(s)} rating{'' if len(s) == 1 else 's'} · {describe(settings[k])}"
        for k, s in rows)


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
    if command == "rate":
        return rate(cfg, rest, now or datetime.now(timezone.utc))
    if command == "report" and not rest:
        return report()
    return USAGE


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(run(" ".join(argv).split()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
