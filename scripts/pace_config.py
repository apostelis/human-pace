"""Load and save the human-pace switches."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

SWITCHES = ("bionic", "answerFirst", "chunks", "actionMarkers")
APPROACHES = ("third", "vowels", "consonants", "third+anchor")
GRADIENTS = ("off", "color", "weight", "both")
MIN_ANCHOR_TRIGGER = 2
MAX_ANCHOR_TRIGGER = 50
MAX_DRIFT_GUARD = 100
DEFAULTS = {"bionic": True, "bionicApproach": "third", "bionicGradient": "off", "anchorTrigger": 8, "answerFirst": True,
            "chunks": True, "actionMarkers": True, "length": 200, "driftGuard": 10}


def config_path() -> Path:
    return Path(os.environ.get("HUMAN_PACE_CONFIG", "~/.claude/human-pace.json")).expanduser()


def log_path() -> Path:
    return Path(os.environ.get("HUMAN_PACE_LOG", "~/.claude/human-pace-log.jsonl")).expanduser()


def defaults() -> dict:
    return dict(DEFAULTS)


def option_environment(env=None):
    """Read user-level native choices for preview and /pace subprocesses.

    Hooks receive resolved options from Claude, including managed settings.
    Bash command subprocesses do not, so user settings are a fallback there.
    """
    result = dict(os.environ if env is None else env)
    if "CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE" in result:
        return result
    try:
        settings = json.loads((Path.home() / ".claude" / "settings.json").read_text())
        options = settings["pluginConfigs"]["human-pace@human-pace"]["options"]
        for key, value in options.items():
            if key not in DEFAULTS and key != "configurationSource":
                continue
            result["CLAUDE_PLUGIN_OPTION_" + key.upper()] = value if isinstance(value, str) else json.dumps(value)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return result


def load_effective_config(path=None, env=None):
    """Native panel settings are opt-in; command settings remain untouched."""
    env = os.environ if env is None else env
    prefix = "CLAUDE_PLUGIN_OPTION_"
    if env.get(prefix + "CONFIGURATIONSOURCE") != "native":
        return load_config(path)
    values, invalid = {}, []
    for key, default in DEFAULTS.items():
        raw = env.get(prefix + key.upper())
        if raw is None:
            continue
        try:
            values[key] = json.loads(raw) if isinstance(default, (bool, int)) else raw
        except (ValueError, TypeError):
            invalid.append(key)
    cfg, rejected = validate(values)
    invalid.extend(rejected)
    error = "Native human-pace options have invalid values for: " + ", ".join(invalid) if invalid else None
    return cfg, error


def _valid_length(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_drift_guard(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_DRIFT_GUARD


def valid_anchor_trigger(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_ANCHOR_TRIGGER <= value <= MAX_ANCHOR_TRIGGER


def load_config(path: Optional[Path] = None) -> Tuple[dict, Optional[str]]:
    """Return (config, error). Missing keys and invalid values fall back to defaults."""
    path = path or config_path()
    cfg = defaults()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return cfg, None
    except UnicodeDecodeError:
        return cfg, f"{path} is not valid UTF-8"
    except OSError as e:
        return cfg, f"cannot read {path}: {e.strerror}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return cfg, f"{path} is not valid JSON (line {e.lineno})"
    if not isinstance(data, dict):
        return cfg, f"{path} must contain a JSON object"
    cfg, invalid = validate(data)
    if invalid:
        return cfg, f"{path} has invalid values for: {', '.join(invalid)}"
    return cfg, None


def validate(data: dict) -> Tuple[dict, List[str]]:
    """Merge known keys over defaults. Return (config, names of keys whose values were rejected)."""
    cfg = defaults()
    invalid = []
    for key in SWITCHES:
        if key in data:
            if isinstance(data[key], bool):
                cfg[key] = data[key]
            else:
                invalid.append(key)
    if "length" in data:
        if _valid_length(data["length"]):
            cfg["length"] = data["length"]
        else:
            invalid.append("length")
    if "bionicApproach" in data:
        if data["bionicApproach"] in APPROACHES:
            cfg["bionicApproach"] = data["bionicApproach"]
        else:
            invalid.append("bionicApproach")
    if "bionicGradient" in data:
        if data["bionicGradient"] in GRADIENTS:
            cfg["bionicGradient"] = data["bionicGradient"]
        else:
            invalid.append("bionicGradient")
    if "anchorTrigger" in data:
        if valid_anchor_trigger(data["anchorTrigger"]):
            cfg["anchorTrigger"] = data["anchorTrigger"]
        else:
            invalid.append("anchorTrigger")
    if "driftGuard" in data:
        if valid_drift_guard(data["driftGuard"]):
            cfg["driftGuard"] = data["driftGuard"]
        else:
            invalid.append("driftGuard")
    return cfg, invalid


def save_config(cfg: dict, path: Optional[Path] = None) -> None:
    # Write through a symlink (e.g. into a dotfiles repo) instead of replacing it with a file.
    path = (path or config_path()).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    known = {key: cfg[key] for key in DEFAULTS}
    # A unique temp name, so two sessions saving at once can't trip over each other's file.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(known, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
