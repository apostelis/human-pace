"""Load and save the human-pace switches."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

SWITCHES = ("bionic", "answerFirst", "chunks", "actionMarkers")
DEFAULTS = {"bionic": True, "answerFirst": True, "chunks": True, "actionMarkers": True, "length": 200}


def config_path() -> Path:
    return Path(os.environ.get("HUMAN_PACE_CONFIG", "~/.claude/human-pace.json")).expanduser()


def log_path() -> Path:
    return Path(os.environ.get("HUMAN_PACE_LOG", "~/.claude/human-pace-log.jsonl")).expanduser()


def defaults() -> dict:
    return dict(DEFAULTS)


def _valid_length(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


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
