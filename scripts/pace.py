#!/usr/bin/env python3
"""/pace: show and change the human-pace switches, and log and report ratings."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pace_config
import pace_analytics as analytics
import pace_analytics_report as analytics_report
from dataclasses import dataclass, field

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
  /pace report                 ratings and 30-day usage summary
  /pace report usage|compare [days]  local usage or configuration comparisons (1-365)
  /pace analytics               recording status and local storage details
  /pace analytics on|off        enable or stop local recording
  /pace analytics retention <days>  retain 1-365 days (default 90)
  /pace analytics export        print retained, validated events as JSONL
  /pace analytics clear         delete analytics history; preserve ratings and preferences
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


@dataclass
class CommandResult:
    text: str
    operation: str
    outcome: str = "success"
    events: List[dict] = field(default_factory=list)


def _save_result(cfg: dict, previous: dict, operation: str) -> CommandResult:
    try:
        pace_config.save_config(cfg)
    except OSError as e:
        return CommandResult(f"Could not save {pace_config.config_path()}: {e.strerror}", operation, "error",
                             [{"event": "settings_error", "category": "save_failed", "invalid_fields": []}])
    events = [{"event": "config_saved", "cfg": cfg, "previous_settings": previous}] if cfg != previous else []
    return CommandResult(f"human-pace: {status(cfg)}\nApplies from your next prompt.", operation, events=events)


def _ends_with_newline(path) -> bool:
    with path.open("rb") as log:
        log.seek(-1, 2)
        return log.read(1) == b"\n"


def _valid_score(score) -> bool:
    return isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5


def _rate_result(cfg: dict, rest: List[str], now: datetime) -> CommandResult:
    if not rest or not NUMBER.fullmatch(rest[0]) or not _valid_score(int(rest[0])):
        return CommandResult(USAGE, "rate", "invalid")
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
        return CommandResult(f"Could not write rating log {path}: {e.strerror}", "rate", "error",
                             [{"event": "settings_error", "category": "rating_failed", "invalid_fields": []}])
    return CommandResult(f"Logged {entry['score']}/5 for: {describe(cfg)}", "rate",
                         events=[{"event": "rating_submitted", "score": entry["score"]}])


def rate(cfg: dict, rest: List[str], now: datetime) -> str:
    return _rate_result(cfg, rest, now).text


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


def _dispatch(args: List[str], cfg: dict, error: Optional[str], native: bool, now: datetime) -> CommandResult:
    if native and args and args[0].lower() != "rate":
        return CommandResult("Human Pace uses native configuration. Change options in the plugin's Configure options panel, or select configuration source commands to use /pace.", "unknown", "invalid")
    if not args:
        warning = (f"\n({error}. Invalid fields use defaults; change them in Configure options.)" if native else
                   f"\n(Config was invalid: {error}. Showing defaults; any change rewrites it.)") if error else ""
        return CommandResult(f"human-pace: {status(cfg)}{warning}" + ("\nConfiguration source: native (Configure options panel)." if native else ""), "status")
    command, rest = args[0].lower(), args[1:]
    previous = dict(cfg)
    if command in SWITCH_NAMES and len(rest) == 1 and rest[0].lower() in ("on", "off"):
        cfg[SWITCH_NAMES[command]] = rest[0].lower() == "on"
        return _save_result(cfg, previous, "toggle")
    if command == "bionic" and len(rest) == 1 and rest[0].lower() in pace_config.APPROACHES:
        cfg["bionic"], cfg["bionicApproach"] = True, rest[0].lower()
        return _save_result(cfg, previous, "approach")
    if command == "experimental" and len(rest) == 2 and rest[0].lower() == "gradient" and rest[1].lower() in pace_config.GRADIENTS:
        cfg["bionicGradient"] = rest[1].lower()
        if cfg["bionicGradient"] != "off":
            cfg["bionic"] = True
        return _save_result(cfg, previous, "gradient")
    if command == "anchor-trigger" and len(rest) == 1 and NUMBER.fullmatch(rest[0]) and pace_config.valid_anchor_trigger(int(rest[0])):
        cfg["anchorTrigger"] = int(rest[0])
        return _save_result(cfg, previous, "anchor_trigger")
    if command == "drift-guard" and len(rest) == 1 and NUMBER.fullmatch(rest[0]) and pace_config.valid_drift_guard(int(rest[0])):
        cfg["driftGuard"] = int(rest[0])
        return _save_result(cfg, previous, "drift_guard")
    if command == "length" and len(rest) == 1 and NUMBER.fullmatch(rest[0]):
        cfg["length"] = int(rest[0])
        return _save_result(cfg, previous, "length")
    if command == "preset" and len(rest) == 1 and rest[0].lower() in PRESETS:
        cfg.update(PRESETS[rest[0].lower()])
        return _save_result(cfg, previous, "preset")
    if command in SHORTCUTS and not rest:
        cfg.update(PRESETS[SHORTCUTS[command]])
        return _save_result(cfg, previous, "preset")
    if command == "reset" and not rest:
        cfg.clear()
        cfg.update(pace_config.defaults())
        return _save_result(cfg, previous, "reset")
    if command == "rate":
        return _rate_result(cfg, rest, now)
    return CommandResult(USAGE, "unknown", "invalid")


def _window(rest: List[str]) -> Optional[int]:
    if not rest:
        return 30
    if len(rest) == 1 and NUMBER.fullmatch(rest[0]) and len(rest[0]) <= 3 and 1 <= int(rest[0]) <= 365:
        return int(rest[0])
    return None


def _analytics_command(rest: List[str], now: datetime) -> str:
    store = analytics.default_store()
    if not rest:
        store.maintain(now=now)
        prefs = store.preferences()
        data = store.read(now=now, days=365)
        d = data["diagnostics"]
        return (f"Local analytics: {'on' if prefs['enabled'] else 'off'}\nStorage: {store.root}\n"
                f"Retention: {prefs['retention_days']} days (lazy cleanup)\n"
                f"Retained records: {d['first'] or 'none'} to {d['last'] or 'none'}\n"
                f"Capped days: {', '.join(d['capped_days']) or 'none'}\n"
                "Coverage: Claude hook prompts; instrumented local commands/settings. Codex/ChatGPT skill usage unavailable.\n"
                "Recording is best effort and local only. Export with /pace analytics export.")
    command = rest[0].lower()
    if command in ("on", "off") and len(rest) == 1:
        store.configure(enabled=command == "on")
        store.maintain(now=now)
        return f"Local analytics recording {command}. Existing records are retained; nothing is uploaded."
    if command == "retention" and len(rest) == 2 and _window(rest[1:]) is not None:
        days = _window(rest[1:])
        store.configure(retention_days=days)
        store.maintain(now=now)
        return f"Local analytics retention: {days} days."
    if command == "clear" and len(rest) == 1:
        store.clear(now=now)
        return "Local analytics history cleared. Ratings and recording preferences preserved."
    if command == "export" and len(rest) == 1:
        store.maintain(now=now)
        return "\n".join(json.dumps(e, ensure_ascii=True) for e in store.read(now=now, days=365)["events"])
    return USAGE


def _usage_report(rest: List[str], now: datetime) -> str:
    if rest and rest[0].lower() not in ("usage", "compare"):
        return USAGE
    days = _window(rest[1:]) if rest else 30
    if days is None:
        return USAGE
    store = analytics.default_store()
    try:
        store.maintain(now=now)
        data = store.read(now=now, days=days)
        summary = analytics_report.summarize(data["events"], now=now, days=days)
        text = (analytics_report.render_compare(summary, data["diagnostics"])
                if rest and rest[0].lower() == "compare" else
                analytics_report.render_usage(summary, data["diagnostics"], compact=not rest))
    except (analytics.AnalyticsError, OSError):
        if rest:
            raise analytics.AnalyticsError("Could not read local analytics. Check /pace analytics.") from None
        text = "Local analytics unavailable. Your ratings are shown above."
    return text if rest else report() + "\n\n" + text


def run(args: List[str], now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if args and args[0].lower() == "analytics":
        return _analytics_command(args[1:], now)
    if args and args[0].lower() == "report":
        return _usage_report(args[1:], now)
    env = pace_config.option_environment()
    native = env.get("CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE") == "native"
    cfg, error = pace_config.load_effective_config(env=env)
    result = _dispatch(args, cfg, error, native, now)
    if error:
        result.events.append({"event": "settings_error", "category": "config_read_or_validation", "invalid_fields": []})
    analytics.record_action(result.operation, result.outcome, source="pace", cfg=cfg,
                            config_source="native" if native else "commands", now=now, events=result.events)
    return result.text


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        output = run(" ".join(argv).split())
    except (analytics.AnalyticsError, OSError):
        print("Could not complete the local analytics command; storage may be busy, invalid, or unwritable.", file=sys.stderr)
        return 1
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
