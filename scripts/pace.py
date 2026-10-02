#!/usr/bin/env python3
"""/pace: show and change the human-pace switches, and log and report ratings."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pace_config

USAGE = """Usage:
  /pace                        show switches
  /pace <switch> on|off        switches: bionic, answerFirst, chunks, actionMarkers
  /pace bionic <approach>      approaches: third, vowels, consonants, third+anchor
  /pace experimental gradient off|color|weight|both  HTML-capable reply surfaces only
  /pace anchor-trigger <n>     third+anchor bolds an extra consonant in words of n+ letters (2-50)
  /pace length <n>             prose word cap, 0 = no cap
  /pace drift-guard <n>        resend the rules every n prompts, 0 = off (max 100)
  /pace preset focus|light|off focus: all on · light: no bionic, 300 words · off: all off
  /pace on | /pace off         same as preset focus | preset off
  /pace reset                  restore defaults
  /pace rate <1-5> [note]      log how the current setting feels
  /pace report                 average rating per setting
Notes cannot contain double quotes, backticks or $."""

SWITCH_NAMES = {name.lower(): name for name in pace_config.SWITCHES}
PRESET_KEYS = (*pace_config.SWITCHES, "length")
PRESETS = {
    "focus": {key: pace_config.DEFAULTS[key] for key in PRESET_KEYS},
    "light": {**{key: pace_config.DEFAULTS[key] for key in PRESET_KEYS}, "bionic": False, "length": 300},
    # length 0 too: a cap alone would still send the length rule.
    "off": {**{name: False for name in pace_config.SWITCHES}, "length": 0},
}
SHORTCUTS = {"on": "focus", "off": "off"}
NUMBER = re.compile(r"[0-9]+")  # ASCII only: "²".isdigit() is True but int("²") raises


def _bionic_label(cfg: dict) -> str:
    if not cfg["bionic"]:
        return "bionic off"
    if cfg.get("legacyRounding"):
        return "bionic on (third, 0.4 rounding)"
    if cfg["bionicApproach"] == "third+anchor":
        return f"bionic on (third+anchor, {cfg['anchorTrigger']}+ letters)"
    return f"bionic on ({cfg['bionicApproach']})"


def describe(cfg: dict) -> str:
    parts = [_bionic_label(cfg)]
    if cfg.get("bionicGradient", "off") != "off":
        parts.append(f"experimental gradient {cfg['bionicGradient']} (HTML only)")
    parts += [f"{name} {'on' if cfg[name] else 'off'}" for name in pace_config.SWITCHES if name != "bionic"]
    parts.append(f"length {cfg['length'] or 'no cap'}")
    return " · ".join(parts)


def status(cfg: dict) -> str:
    """describe() plus settings that change delivery, not formatting (kept out of ratings)."""
    guard = f"every {cfg['driftGuard']} prompts" if cfg["driftGuard"] else "off"
    return f"{describe(cfg)} · drift guard {guard}"


def _save(cfg: dict) -> str:
    try:
        pace_config.save_config(cfg)
    except OSError as e:
        return f"Could not save {pace_config.config_path()}: {e.strerror}"
    return f"human-pace: {status(cfg)}\nApplies from your next prompt."


def _ends_with_newline(path) -> bool:
    with path.open("rb") as log:
        log.seek(-1, 2)
        return log.read(1) == b"\n"


def _valid_score(score) -> bool:
    return isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5


def rate(cfg: dict, rest: List[str], now: datetime) -> str:
    if not rest or not NUMBER.fullmatch(rest[0]) or not _valid_score(int(rest[0])):
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


def effective_setting(setting: dict) -> dict:
    """Drop settings that change nothing, so they don't split report groups."""
    effective = dict(setting)
    del effective["driftGuard"]  # changes delivery, not formatting
    if not effective["bionic"]:
        del effective["bionicApproach"], effective["anchorTrigger"], effective["bionicGradient"]
    elif effective["bionicApproach"] != "third+anchor":
        del effective["anchorTrigger"]
    return effective


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
        if not isinstance(switches, dict) or not _valid_score(score):
            continue
        setting, invalid = pace_config.validate(switches)
        if invalid:
            continue  # hand-edited into something /pace rate never writes
        if setting["bionic"] and "bionicApproach" not in switches:
            setting["legacyRounding"] = True  # rated before 0.5: third rounded up for every word length
        key = json.dumps(effective_setting(setting), sort_keys=True)
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
        return f"human-pace: {status(cfg)}{warning}"
    command, rest = args[0].lower(), args[1:]
    if command in SWITCH_NAMES and len(rest) == 1 and rest[0].lower() in ("on", "off"):
        cfg[SWITCH_NAMES[command]] = rest[0].lower() == "on"
        return _save(cfg)
    if command == "bionic" and len(rest) == 1 and rest[0].lower() in pace_config.APPROACHES:
        cfg["bionic"], cfg["bionicApproach"] = True, rest[0].lower()
        return _save(cfg)
    if command == "experimental" and len(rest) == 2 and rest[0].lower() == "gradient" \
            and rest[1].lower() in pace_config.GRADIENTS:
        cfg["bionicGradient"] = rest[1].lower()
        if cfg["bionicGradient"] != "off":
            cfg["bionic"] = True
        return _save(cfg)
    if command == "anchor-trigger" and len(rest) == 1 and NUMBER.fullmatch(rest[0]) \
            and pace_config.valid_anchor_trigger(int(rest[0])):
        cfg["anchorTrigger"] = int(rest[0])
        return _save(cfg)
    if command == "drift-guard" and len(rest) == 1 and NUMBER.fullmatch(rest[0]) \
            and pace_config.valid_drift_guard(int(rest[0])):
        cfg["driftGuard"] = int(rest[0])
        return _save(cfg)
    if command == "length" and len(rest) == 1 and NUMBER.fullmatch(rest[0]):
        cfg["length"] = int(rest[0])
        return _save(cfg)
    if command == "preset" and len(rest) == 1 and rest[0].lower() in PRESETS:
        return _save({**cfg, **PRESETS[rest[0].lower()]})
    if command in SHORTCUTS and not rest:
        return _save({**cfg, **PRESETS[SHORTCUTS[command]]})
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
