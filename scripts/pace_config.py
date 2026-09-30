"""Load and save the human-pace switches."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

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
    except OSError as e:
        return cfg, f"cannot read {path}: {e.strerror}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return cfg, f"{path} is not valid JSON (line {e.lineno})"
    if not isinstance(data, dict):
        return cfg, f"{path} must contain a JSON object"

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
    if invalid:
        return cfg, f"{path} has invalid values for: {', '.join(invalid)}"
    return cfg, None


def save_config(cfg: dict, path: Optional[Path] = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    known = {key: cfg[key] for key in DEFAULTS}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(known, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
