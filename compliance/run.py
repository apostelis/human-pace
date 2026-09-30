#!/usr/bin/env python3
"""Send the compliance prompts through `claude -p` with this plugin and print per-rule pass rates."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPTS = HERE / "prompts.txt"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import pace_config  # noqa: E402
from score import score_reply  # noqa: E402


def load_prompts(path: Path = PROMPTS) -> List[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def ask(prompt: str, env: Dict[str, str], cwd: str) -> str:
    result = subprocess.run(["claude", "-p", "--plugin-dir", str(ROOT), prompt],
                            capture_output=True, text=True, env=env, cwd=cwd, timeout=300)
    return result.stdout


def harness_env(tmp: str) -> Dict[str, str]:
    env = dict(os.environ)
    env["HUMAN_PACE"] = "1"                                    # claude -p is headless: force the plugin on
    env["HUMAN_PACE_CONFIG"] = str(Path(tmp) / "absent.json")  # defaults, not your own switches
    return env


def main() -> int:
    cfg = pace_config.defaults()
    results: Dict[str, List[bool]] = {}
    prompts = load_prompts()
    with tempfile.TemporaryDirectory() as tmp:
        env = harness_env(tmp)
        for n, prompt in enumerate(prompts, 1):
            print(f"[{n}/{len(prompts)}] {prompt[:70]}", file=sys.stderr)
            scores = score_reply(ask(prompt, env, tmp), cfg)
            failed = [rule for rule, ok in scores.items() if not ok]
            if failed:
                print(f"    failed: {', '.join(failed)}", file=sys.stderr)
            for rule, ok in scores.items():
                results.setdefault(rule, []).append(ok)
    for rule, oks in results.items():
        print(f"{rule:<20} {sum(oks)}/{len(oks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
