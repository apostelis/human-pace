# human-pace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that injects toggleable reply-format rules (bionic reading, answer-first, short chunks, action markers, length cap) on every prompt, with a `/pace` command, a rating log, and a compliance harness.

**Architecture:** A `UserPromptSubmit` hook runs `scripts/inject.py`, which reads switches from `~/.claude/human-pace.json`, joins the markdown rule fragments for enabled switches, and returns them as `additionalContext`. `/pace` is a command file whose `!` line runs `scripts/pace.py` deterministically. A separate `compliance/` harness sends fixed prompts through `claude -p --plugin-dir` and scores replies against a reference bionic algorithm.

**Tech Stack:** Python 3.9+ standard library only (`unittest`, `json`, `re`, `subprocess`), Claude Code plugin format (`.claude-plugin/plugin.json`, `marketplace.json`, `hooks/hooks.json`, `commands/*.md`).

**Spec:** `docs/superpowers/specs/2026-09-30-human-pace-design.md`

## Global Constraints

- Python 3.9+ standard library only; no third-party packages. Put `from __future__ import annotations` at the top of every module; no `match`, and no `X | Y` types evaluated at runtime.
- State lives outside the plugin: config at `~/.claude/human-pace.json`, log at `~/.claude/human-pace-log.jsonl`. `${CLAUDE_PLUGIN_ROOT}` is replaced on every plugin update.
- Env overrides for tests and the harness: `HUMAN_PACE_CONFIG` (config path), `HUMAN_PACE_LOG` (log path). Kill switch: `HUMAN_PACE=0` means inject nothing.
- Defaults: `{"bionic": true, "answerFirst": true, "chunks": true, "actionMarkers": true, "length": 200}`; `length` 0 means no cap.
- Bionic: bold `max(1, ceil(letters / 3))` letters of each prose word. Apostrophes are inside words but not counted as letters; hyphens split words.
- Formatting applies to chat replies only. Never to commits, PR bodies, files, tool inputs, or text written for others. Never inside code, paths, URLs, identifiers, or tables.
- All rule fragments together: at most 700 characters (about 150 tokens).
- `inject.py` always exits 0 and never blocks a prompt.
- **Deviation from the spec:** the spec's `evals/` directory is named `compliance/`, because `claude plugin eval` treats a plugin's `evals/` directory as its own eval cases.
- Test command, run from the repo root: `python3 -m unittest discover -s tests -v`
- Test naming: `test_should_<do_x>_when_<y>`.

## Review Focus

Failure modes the spec implies but doesn't spell out. Each has a test in the task that owns it.

1. A hand-edited config with wrong-typed values (`"length": "150"`, `"bionic": "yes"`) must not crash, and must not treat `"yes"` as on. It keeps that key's default and reports the problem. Tested in Task 1.
2. A rating note containing an apostrophe (`didn't help`) must be recorded intact. `$ARGUMENTS` is double-quoted in the command file for exactly this reason. Tested in Task 4.
3. Hook stdin that is empty or not JSON must still inject the rules, not silently skip them. Tested in Task 2.
4. Only real `/pace` invocations skip the rules. `/pacemaker` or `please /pace` must still get them, and leading spaces before `/pace` still count as a `/pace` invocation. Tested in Task 2.
5. A log with a truncated or corrupt line (for example after a crash mid-write) must not break `/pace report`. The bad line is skipped. Tested in Task 4.

---

### Task 1: Plugin manifest, marketplace, and config module

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `.gitignore`
- Create: `scripts/pace_config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `pace_config.SWITCHES: tuple[str, ...]` = `("bionic", "answerFirst", "chunks", "actionMarkers")`
  - `pace_config.DEFAULTS: dict`, `pace_config.defaults() -> dict` (a fresh copy)
  - `pace_config.config_path() -> Path`, `pace_config.log_path() -> Path` (read env overrides at call time)
  - `pace_config.load_config(path: Optional[Path] = None) -> tuple[dict, Optional[str]]` returns `(config, error)`. `error` is None unless the file exists and is invalid.
  - `pace_config.save_config(cfg: dict, path: Optional[Path] = None) -> None` writes only known keys, creates parent dirs, replaces the file atomically.

- [ ] **Step 1: Write the plugin manifest, marketplace and gitignore**

`.claude-plugin/plugin.json`:
```json
{
  "name": "human-pace",
  "version": "0.1.0",
  "description": "Human-paced replies: bionic reading, answer first, short chunks, action markers and a length cap, each toggleable with /pace.",
  "author": { "name": "a.palogos" }
}
```

`.claude-plugin/marketplace.json`:
```json
{
  "name": "human-pace",
  "description": "Marketplace for the human-pace plugin",
  "owner": { "name": "a.palogos" },
  "plugins": [
    {
      "name": "human-pace",
      "description": "Human-paced replies: bionic reading, answer first, short chunks, action markers and a length cap, each toggleable with /pace.",
      "version": "0.1.0",
      "source": "./"
    }
  ]
}
```

`.gitignore`:
```
__pycache__/
*.pyc
```

- [ ] **Step 2: Validate the manifest**

Run: `claude plugin validate .`
Expected: validation passes. If it reports an error, fix the named field before continuing.

- [ ] **Step 3: Write the failing tests**

`tests/test_config.py`:
```python
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pace_config as pc  # noqa: E402


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "human-pace.json"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")

    def test_should_return_defaults_when_file_missing(self):
        cfg, error = pc.load_config(self.path)
        self.assertEqual(cfg, pc.DEFAULTS)
        self.assertIsNone(error)

    def test_should_merge_known_keys_over_defaults_when_file_valid(self):
        self.write(json.dumps({"bionic": False, "length": 150}))
        cfg, error = pc.load_config(self.path)
        self.assertFalse(cfg["bionic"])
        self.assertEqual(cfg["length"], 150)
        self.assertTrue(cfg["chunks"])
        self.assertIsNone(error)

    def test_should_ignore_unknown_keys_when_present(self):
        self.write(json.dumps({"theme": "dark"}))
        cfg, error = pc.load_config(self.path)
        self.assertEqual(cfg, pc.DEFAULTS)
        self.assertIsNone(error)

    def test_should_return_defaults_and_error_when_json_malformed(self):
        self.write("{bionic: false")
        cfg, error = pc.load_config(self.path)
        self.assertEqual(cfg, pc.DEFAULTS)
        self.assertIn("not valid JSON", error)

    def test_should_return_error_when_top_level_is_not_an_object(self):
        self.write("[1, 2]")
        cfg, error = pc.load_config(self.path)
        self.assertEqual(cfg, pc.DEFAULTS)
        self.assertIn("JSON object", error)

    def test_should_keep_defaults_and_report_keys_when_values_have_wrong_type(self):
        self.write(json.dumps({"bionic": "yes", "length": "150", "chunks": False}))
        cfg, error = pc.load_config(self.path)
        self.assertTrue(cfg["bionic"])
        self.assertEqual(cfg["length"], 200)
        self.assertFalse(cfg["chunks"])
        self.assertIn("bionic", error)
        self.assertIn("length", error)

    def test_should_reject_length_when_negative_or_boolean(self):
        for bad in (-5, True):
            with self.subTest(bad=bad):
                self.write(json.dumps({"length": bad}))
                cfg, error = pc.load_config(self.path)
                self.assertEqual(cfg["length"], 200)
                self.assertIn("length", error)

    def test_should_read_env_override_when_resolving_paths(self):
        with mock.patch.dict(os.environ, {"HUMAN_PACE_CONFIG": str(self.path),
                                          "HUMAN_PACE_LOG": str(self.path) + ".log"}):
            self.assertEqual(pc.config_path(), self.path)
            self.assertEqual(pc.log_path(), Path(str(self.path) + ".log"))

    def test_should_return_independent_copy_when_asked_for_defaults(self):
        cfg = pc.defaults()
        cfg["bionic"] = False
        self.assertTrue(pc.DEFAULTS["bionic"])


class SaveConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def test_should_create_parent_directory_and_round_trip_when_saving(self):
        path = Path(self.dir.name) / "fresh-home" / ".claude" / "human-pace.json"
        cfg = pc.defaults()
        cfg["bionic"] = False
        pc.save_config(cfg, path)
        self.assertEqual(pc.load_config(path), (cfg, None))

    def test_should_drop_unknown_keys_when_saving(self):
        path = Path(self.dir.name) / "human-pace.json"
        pc.save_config({**pc.defaults(), "extra": 1}, path)
        self.assertNotIn("extra", json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: ERROR with `ModuleNotFoundError: No module named 'pace_config'`

- [ ] **Step 5: Write the implementation**

`scripts/pace_config.py`:
```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all 11 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin .gitignore scripts/pace_config.py tests/test_config.py
git commit -m "feat: plugin manifest, marketplace and config module"
```

---

### Task 2: Rule fragments, inject hook, and hooks.json

**Files:**
- Create: `rules/common.md`, `rules/answer-first.md`, `rules/chunks.md`, `rules/action-markers.md`, `rules/length.md`, `rules/bionic.md`
- Create: `scripts/inject.py`
- Create: `hooks/hooks.json`
- Test: `tests/test_inject.py`

**Interfaces:**
- Consumes: `pace_config.load_config()`, `pace_config.DEFAULTS`, `pace_config.defaults()`
- Produces:
  - `inject.build_rules(cfg: dict, rules_dir: Path = RULES_DIR, config_error: Optional[str] = None) -> str` returns `""` when no rule is enabled and there is no error.
  - `inject.should_skip(hook_input: dict, env: Mapping[str, str]) -> bool`
  - `inject.main(stdin=sys.stdin, stdout=sys.stdout, env=os.environ) -> int` always returns 0.

- [ ] **Step 1: Write the rule fragments**

Each file holds exactly the text shown, followed by one trailing newline.

`rules/common.md`:
```
human-pace format. Apply to this chat reply only, never to commits, PRs, files, tool inputs or text for others. Leave code, paths, URLs, identifiers and tables unformatted.
```

`rules/answer-first.md`:
```
Line 1: the answer or outcome in one sentence.
```

`rules/chunks.md`:
```
At most 3 sentences per paragraph; steps and options as lists.
```

`rules/action-markers.md`:
```
Put anything the user must do last, on a line starting "▶ You:".
```

`rules/length.md`:
```
Under {length} prose words (code excluded); offer more rather than add it.
```

`rules/bionic.md`:
```
Bionic reading: bold the first third of every prose word, rounded up, min 1 letter: **t**he **fo**cus **rea**ding **R**e-**a**dd. Numbers, headings and tables stay plain. No other bold.
```

- [ ] **Step 2: Write the hook registration**

`hooks/hooks.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/inject.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

`|| true` makes a missing `python3` fail open: exit 0 with no output, so no rules are added.

- [ ] **Step 3: Write the failing tests**

`tests/test_inject.py`:
```python
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import inject  # noqa: E402
import pace_config as pc  # noqa: E402


def cfg(**overrides):
    return {**pc.defaults(), **overrides}


class BuildRulesTest(unittest.TestCase):
    def test_should_include_every_fragment_in_order_when_all_defaults(self):
        rules = inject.build_rules(cfg())
        order = ["human-pace format", "Line 1:", "3 sentences", "▶ You:", "Under 200", "Bionic reading"]
        positions = [rules.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))

    def test_should_omit_fragment_when_switch_off(self):
        rules = inject.build_rules(cfg(bionic=False))
        self.assertNotIn("Bionic reading", rules)
        self.assertIn("Line 1:", rules)

    def test_should_substitute_length_when_set(self):
        self.assertIn("Under 150 prose words", inject.build_rules(cfg(length=150)))

    def test_should_omit_length_fragment_when_length_zero(self):
        self.assertNotIn("prose words", inject.build_rules(cfg(length=0)))

    def test_should_return_empty_when_everything_off(self):
        off = cfg(bionic=False, answerFirst=False, chunks=False, actionMarkers=False, length=0)
        self.assertEqual(inject.build_rules(off), "")

    def test_should_append_warning_when_config_error_given(self):
        rules = inject.build_rules(cfg(), config_error="x.json is not valid JSON (line 1)")
        self.assertTrue(rules.endswith("Also tell the user: x.json is not valid JSON (line 1); human-pace is using defaults."))

    def test_should_skip_fragment_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "chunks.md").write_text("CHUNKS\n", encoding="utf-8")
            self.assertEqual(inject.build_rules(cfg(), Path(tmp)), "CHUNKS")

    def test_should_stay_within_budget_when_all_defaults(self):
        self.assertLessEqual(len(inject.build_rules(cfg())), 700)


class ShouldSkipTest(unittest.TestCase):
    def test_should_skip_when_kill_switch_set(self):
        self.assertTrue(inject.should_skip({"prompt": "hi"}, {"HUMAN_PACE": "0"}))

    def test_should_skip_when_prompt_is_pace_command(self):
        for prompt in ("/pace", "/pace bionic off", "  /pace", "/human-pace:pace report"):
            with self.subTest(prompt=prompt):
                self.assertTrue(inject.should_skip({"prompt": prompt}, {}))

    def test_should_not_skip_when_prompt_only_resembles_pace(self):
        for hook_input in ({"prompt": "/pacemaker"}, {"prompt": "please /pace"}, {"prompt": ""}, {}):
            with self.subTest(hook_input=hook_input):
                self.assertFalse(inject.should_skip(hook_input, {}))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"HUMAN_PACE_CONFIG": str(Path(self.dir.name) / "absent.json")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()

    def run_main(self, stdin_text, env=None):
        out = io.StringIO()
        code = inject.main(io.StringIO(stdin_text), out, env or {})
        return code, out.getvalue()

    def test_should_emit_hook_json_when_prompt_is_normal(self):
        code, out = self.run_main(json.dumps({"prompt": "explain rebase"}))
        self.assertEqual(code, 0)
        payload = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(payload["hookEventName"], "UserPromptSubmit")
        self.assertIn("Bionic reading", payload["additionalContext"])

    def test_should_still_inject_when_stdin_empty_or_not_json(self):
        for stdin_text in ("", "not json", "[1]"):
            with self.subTest(stdin_text=stdin_text):
                code, out = self.run_main(stdin_text)
                self.assertEqual(code, 0)
                self.assertIn("additionalContext", out)

    def test_should_emit_nothing_when_pace_command(self):
        self.assertEqual(self.run_main(json.dumps({"prompt": "/pace"})), (0, ""))

    def test_should_emit_nothing_and_exit_zero_when_build_fails(self):
        with mock.patch.object(inject, "build_rules", side_effect=RuntimeError("boom")):
            self.assertEqual(self.run_main(json.dumps({"prompt": "hi"})), (0, ""))

    def test_should_warn_when_config_malformed(self):
        Path(os.environ["HUMAN_PACE_CONFIG"]).write_text("{oops", encoding="utf-8")
        _, out = self.run_main(json.dumps({"prompt": "hi"}))
        self.assertIn("Also tell the user", json.loads(out)["hookSpecificOutput"]["additionalContext"])


class ScriptTest(unittest.TestCase):
    def run_script(self, extra_env):
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "HUMAN_PACE"}
            env.update({"HUMAN_PACE_CONFIG": str(Path(tmp) / "absent.json"), **extra_env})
            return subprocess.run([sys.executable, str(ROOT / "scripts" / "inject.py")],
                                  input=json.dumps({"prompt": "hi"}), capture_output=True, text=True, env=env)

    def test_should_exit_zero_with_valid_json_when_run_as_script(self):
        result = self.run_script({})
        self.assertEqual(result.returncode, 0)
        self.assertIn("additionalContext", json.loads(result.stdout)["hookSpecificOutput"])

    def test_should_print_nothing_when_kill_switch_set(self):
        result = self.run_script({"HUMAN_PACE": "0"})
        self.assertEqual((result.returncode, result.stdout), (0, ""))


class HooksJsonTest(unittest.TestCase):
    def test_should_register_fail_open_prompt_hook(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/inject.py", command)
        self.assertTrue(command.endswith("|| true"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: `test_inject` ERRORs with `ModuleNotFoundError: No module named 'inject'`. The Task 1 tests still pass.

- [ ] **Step 5: Write the implementation**

`scripts/inject.py`:
```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS. If `test_should_stay_within_budget_when_all_defaults` fails, shorten fragment wording. Do not raise the limit.

- [ ] **Step 7: Commit**

```bash
git add rules scripts/inject.py hooks tests/test_inject.py
git commit -m "feat: inject enabled rules on every prompt via UserPromptSubmit hook"
```

---

### Task 3: `/pace` show, toggle, length and reset

**Files:**
- Create: `scripts/pace.py`
- Create: `commands/pace.md`
- Test: `tests/test_pace.py`

**Interfaces:**
- Consumes: `pace_config.load_config()`, `save_config()`, `defaults()`, `config_path()`, `SWITCHES`
- Produces:
  - `pace.USAGE: str`
  - `pace.describe(cfg: dict) -> str`, e.g. `"bionic on · answerFirst on · chunks on · actionMarkers on · length 200"`; length 0 renders as `length no cap`.
  - `pace.run(args: list[str], now: Optional[datetime] = None) -> str`
  - `pace.main(argv: Optional[list[str]] = None) -> int` joins argv, splits on whitespace, prints `run(...)`, returns 0.
  - Task 4 adds `rate` and `report` to `run`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pace.py`:
```python
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pace  # noqa: E402
import pace_config as pc  # noqa: E402


class PaceTestBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.config = Path(self.dir.name) / "home" / ".claude" / "human-pace.json"
        self.log = Path(self.dir.name) / "home" / ".claude" / "human-pace-log.jsonl"
        self.env = mock.patch.dict(os.environ, {"HUMAN_PACE_CONFIG": str(self.config),
                                                "HUMAN_PACE_LOG": str(self.log)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()


class ShowAndChangeTest(PaceTestBase):
    def test_should_show_defaults_when_no_config(self):
        self.assertEqual(pace.run([]),
                         "human-pace: bionic on · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_persist_switch_when_toggled_off(self):
        out = pace.run(["bionic", "off"])
        self.assertIn("bionic off", out)
        self.assertIn("Applies from your next prompt.", out)
        self.assertFalse(pc.load_config()[0]["bionic"])

    def test_should_accept_any_case_when_toggling(self):
        pace.run(["ANSWERFIRST", "Off"])
        self.assertFalse(pc.load_config()[0]["answerFirst"])

    def test_should_set_length_when_number_given(self):
        pace.run(["length", "150"])
        self.assertEqual(pc.load_config()[0]["length"], 150)

    def test_should_show_no_cap_when_length_zero(self):
        self.assertIn("length no cap", pace.run(["length", "0"]))

    def test_should_restore_defaults_when_reset(self):
        pace.run(["bionic", "off"])
        pace.run(["reset"])
        self.assertEqual(pc.load_config(), (pc.DEFAULTS, None))

    def test_should_print_usage_and_change_nothing_when_input_invalid(self):
        for args in (["length", "abc"], ["length", "-3"], ["bionic", "maybe"], ["bionic"],
                     ["frobnicate"], ["reset", "now"]):
            with self.subTest(args=args):
                self.assertEqual(pace.run(args), pace.USAGE)
                self.assertFalse(self.config.exists())

    def test_should_flag_and_rewrite_when_config_malformed(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text("{oops", encoding="utf-8")
        self.assertIn("Config was invalid", pace.run([]))
        pace.run(["chunks", "off"])
        self.assertEqual(pc.load_config()[1], None)


class MainTest(PaceTestBase):
    def test_should_split_single_quoted_argument_when_called_from_command_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pace.main(["bionic off"])
        self.assertEqual(code, 0)
        self.assertIn("bionic off", out.getvalue())

    def test_should_show_status_when_argument_empty(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pace.main([""])
        self.assertTrue(out.getvalue().startswith("human-pace: bionic on"))


class CommandFileTest(unittest.TestCase):
    def test_should_run_script_with_double_quoted_arguments(self):
        text = (ROOT / "commands" / "pace.md").read_text(encoding="utf-8")
        self.assertIn('!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pace.py" "$ARGUMENTS"`', text)
        self.assertIn("allowed-tools: Bash(python3:*)", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: `test_pace` ERRORs with `ModuleNotFoundError: No module named 'pace'`.

- [ ] **Step 3: Write the command file**

`commands/pace.md`:
```markdown
---
description: Show or change human-pace switches, rate the current setting, or see the report
argument-hint: "[<switch> on|off | length <n> | reset | rate <1-5> [note] | report]"
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pace.py" "$ARGUMENTS"`

Reply with the output above exactly as written. Add nothing and apply no formatting.
```

`$ARGUMENTS` is double-quoted so that apostrophes in notes survive the shell. Double quotes, backticks and `$` in arguments are unsupported, and `USAGE` says so.

- [ ] **Step 4: Write the implementation**

`scripts/pace.py`:
```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/pace.py commands/pace.md tests/test_pace.py
git commit -m "feat: /pace command to show, toggle, cap length and reset"
```

---

### Task 4: `/pace rate` and `/pace report`

**Files:**
- Modify: `scripts/pace.py` (add imports and `rate()`/`report()`, and route them in `run()`)
- Test: `tests/test_pace.py` (add `RateTest` and `ReportTest`)

**Interfaces:**
- Consumes: `pace.describe`, `pace.USAGE`, `pace_config.log_path()`, `pace_config.DEFAULTS`, the `PaceTestBase` fixture
- Produces:
  - `pace.rate(cfg: dict, rest: list[str], now: datetime) -> str` appends `{"ts", "switches", "score", "note"}` as one JSON line.
  - `pace.report() -> str` has one line per switch combination, sorted by mean score descending, formatted `"<mean:.1f> avg · <n> rating(s) · <describe>"`.

- [ ] **Step 1: Write the failing tests**

Add this import at the top of `tests/test_pace.py`, next to the others:
```python
from datetime import datetime, timezone
```

Then add these classes before `if __name__ == "__main__":`:
```python
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


class RateTest(PaceTestBase):
    def entries(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_should_append_entry_with_current_switches_when_rating_valid(self):
        pace.run(["bionic", "off"])
        out = pace.run(["rate", "4", "easier", "to", "scan"], now=NOW)
        self.assertEqual(out, "Logged 4/5 for: bionic off · answerFirst on · chunks on · actionMarkers on · length 200")
        self.assertEqual(self.entries(), [{"ts": "2026-10-01T09:00:00+00:00",
                                           "switches": {**pc.DEFAULTS, "bionic": False},
                                           "score": 4, "note": "easier to scan"}])

    def test_should_keep_apostrophe_when_note_arrives_through_command_file(self):
        with contextlib.redirect_stdout(io.StringIO()):
            pace.main(["rate 2 didn't help"])
        self.assertEqual(self.entries()[0]["note"], "didn't help")

    def test_should_print_usage_and_log_nothing_when_score_invalid(self):
        for args in (["rate"], ["rate", "0"], ["rate", "6"], ["rate", "x"]):
            with self.subTest(args=args):
                self.assertEqual(pace.run(args, now=NOW), pace.USAGE)
                self.assertFalse(self.log.exists())

    def test_should_not_create_config_when_rating(self):
        pace.run(["rate", "3"], now=NOW)
        self.assertFalse(self.config.exists())

    def test_should_report_error_when_log_unwritable(self):
        self.log.mkdir(parents=True)  # a directory where the file should be
        self.assertTrue(pace.run(["rate", "3"], now=NOW).startswith("Could not write rating log"))


class ReportTest(PaceTestBase):
    def write_log(self, lines):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def entry(self, score, **switches):
        return json.dumps({"ts": "t", "switches": {**pc.DEFAULTS, **switches}, "score": score, "note": ""})

    def test_should_say_no_ratings_when_log_missing(self):
        self.assertEqual(pace.run(["report"]), "No ratings yet. Use /pace rate <1-5> [note].")

    def test_should_group_by_setting_and_sort_by_mean_when_log_has_entries(self):
        self.write_log([self.entry(2, bionic=False), self.entry(4), self.entry(5)])
        self.assertEqual(pace.run(["report"]).splitlines(), [
            "4.5 avg · 2 ratings · bionic on · answerFirst on · chunks on · actionMarkers on · length 200",
            "2.0 avg · 1 rating · bionic off · answerFirst on · chunks on · actionMarkers on · length 200",
        ])

    def test_should_skip_corrupt_lines_when_reporting(self):
        self.write_log([self.entry(4), '{"ts": "t", "swi', "[]", '{"switches": {}, "score": "5"}', self.entry(2)])
        self.assertEqual(pace.run(["report"]),
                         "3.0 avg · 2 ratings · bionic on · answerFirst on · chunks on · actionMarkers on · length 200")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: the `RateTest` and `ReportTest` cases FAIL, because `run` returns `USAGE` for `rate` and `report`.

- [ ] **Step 3: Write the implementation**

In `scripts/pace.py`, change the docstring and imports to:
```python
"""/pace: show and change the human-pace switches, and log and report ratings."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pace_config
```

Add these two functions after `_save`:
```python
def rate(cfg: dict, rest: List[str], now: datetime) -> str:
    if not rest or not rest[0].isdigit() or not 1 <= int(rest[0]) <= 5:
        return USAGE
    entry = {"ts": now.isoformat(timespec="seconds"), "switches": cfg,
             "score": int(rest[0]), "note": " ".join(rest[1:])}
    path = pace_config.log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        return f"Could not write rating log {path}: {e.strerror}"
    return f"Logged {entry['score']}/5 for: {describe(cfg)}"


def report() -> str:
    path = pace_config.log_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
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
```

In `run()`, add these two lines directly before the final `return USAGE`:
```python
    if command == "rate":
        return rate(cfg, rest, now or datetime.now(timezone.utc))
    if command == "report" and not rest:
        return report()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/pace.py tests/test_pace.py
git commit -m "feat: /pace rate and /pace report for the personal experiment log"
```

---

### Task 5: Reference bionic algorithm

**Files:**
- Create: `compliance/bionic.py`
- Test: `tests/test_bionic.py`

**Interfaces:**
- Produces:
  - `bionic.bold_length(word: str) -> int`
  - `bionic.bionic_word(word: str) -> str`, e.g. `"reading"` → `"**rea**ding"`
  - `bionic.to_bionic(text: str) -> str` applies `bionic_word` to every prose word in plain text.
  - `bionic.prose_only(markdown: str) -> str` removes fenced code, inline code, URLs, heading lines and table lines.
  - `bionic.score_bionic(markdown: str) -> tuple[int, int]` returns `(correct, total)` over prose words.
  - `bionic.bold_in_code(markdown: str) -> bool`

- [ ] **Step 1: Write the failing tests**

`tests/test_bionic.py`:
```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "compliance"))

import bionic  # noqa: E402


class BoldLengthTest(unittest.TestCase):
    def test_should_bold_a_third_rounded_up_with_minimum_one(self):
        cases = {"a": 1, "the": 1, "focus": 2, "plugin": 2, "reading": 3, "understand": 4, "don't": 2}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.bold_length(word), expected)


class BionicWordTest(unittest.TestCase):
    def test_should_bold_prefix_when_given_spec_examples(self):
        cases = {"the": "**t**he", "focus": "**fo**cus", "reading": "**rea**ding",
                 "understand": "**unde**rstand", "don't": "**do**n't", "I'm": "**I**'m"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.bionic_word(word), expected)

    def test_should_split_on_hyphen_and_skip_numbers_when_converting_text(self):
        self.assertEqual(bionic.to_bionic("Re-add the plugin 3 times."),
                         "**R**e-**a**dd **t**he **pl**ugin 3 **ti**mes.")


class ScoreBionicTest(unittest.TestCase):
    def test_should_score_all_correct_when_text_is_reference_output(self):
        text = bionic.to_bionic("The build failed because the merge dropped a plugin.")
        self.assertEqual(bionic.score_bionic(text), (9, 9))

    def test_should_count_wrong_prefix_when_bolding_too_much(self):
        self.assertEqual(bionic.score_bionic("**fo**cus **readi**ng"), (1, 2))

    def test_should_count_emphasis_bold_as_wrong_when_bionic_on(self):
        self.assertEqual(bionic.score_bionic("**Note:** **fo**cus"), (1, 2))

    def test_should_ignore_code_paths_urls_headings_tables_and_identifiers(self):
        markdown = ("# Heading words\n"
                    "**fo**cus `inline code` src/app.py answerFirst e.g. https://x.io/a\n"
                    "| cell | words |\n"
                    "```\nplain words here\n```\n")
        self.assertEqual(bionic.score_bionic(markdown), (1, 1))

    def test_should_score_bullets_and_action_line_when_formatted(self):
        self.assertEqual(bionic.score_bionic("- **fo**cus\n▶ **Y**ou: **app**rove"), (3, 3))

    def test_should_return_zero_total_when_no_prose(self):
        self.assertEqual(bionic.score_bionic("```\ncode\n```"), (0, 0))


class BoldInCodeTest(unittest.TestCase):
    def test_should_detect_bold_inside_fenced_or_inline_code(self):
        self.assertTrue(bionic.bold_in_code("```\n**fi**x: retry\n```"))
        self.assertTrue(bionic.bold_in_code("run `**gi**t push`"))

    def test_should_pass_when_bold_only_in_prose(self):
        self.assertFalse(bionic.bold_in_code("**fo**cus `git push`\n```\nfix: retry\n```"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: `test_bionic` ERRORs with `ModuleNotFoundError: No module named 'bionic'`.

- [ ] **Step 3: Write the implementation**

`compliance/bionic.py`:
```python
"""Reference bionic algorithm (spec §3), shared by the tests and the compliance harness."""
from __future__ import annotations

import math
import re
from typing import Tuple

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")          # letters, internal apostrophes allowed
FENCE = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")
PATH_LIKE = re.compile(r"[/\\@]|\w[.:]\w")                 # src/app.py, e.g., user@host
CAMEL = re.compile(r"[a-z][A-Z]")                         # answerFirst: an identifier, not prose
SEPARATORS = re.compile(r"[\s\-–—]+")                     # whitespace and hyphens split words


def bold_length(word: str) -> int:
    letters = sum(1 for c in word if c.isalpha())
    return max(1, math.ceil(letters / 3))


def bionic_word(word: str) -> str:
    target, seen = bold_length(word), 0
    for i, c in enumerate(word):
        if c.isalpha():
            seen += 1
            if seen == target:
                return f"**{word[:i + 1]}**{word[i + 1:]}"
    return word


def to_bionic(text: str) -> str:
    return WORD.sub(lambda m: bionic_word(m.group(0)), text)


def prose_only(markdown: str) -> str:
    """Drop what bionic never applies to: code, URLs, headings and tables."""
    text = INLINE_CODE.sub("", FENCE.sub("", markdown))
    text = URL.sub("", text)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", "|")))


def score_bionic(markdown: str) -> Tuple[int, int]:
    """Return (correct, total) prose words, judged against bionic_word."""
    correct = total = 0
    for chunk in SEPARATORS.split(prose_only(markdown)):
        if not chunk or PATH_LIKE.search(chunk.replace("**", "")):
            continue
        actual = re.sub(r"[^\w*'’]", "", chunk).strip("'’")
        plain = actual.replace("**", "")
        if not WORD.fullmatch(plain) or CAMEL.search(plain):
            continue
        total += 1
        correct += actual == bionic_word(plain)
    return correct, total


def bold_in_code(markdown: str) -> bool:
    spans = FENCE.findall(markdown) + INLINE_CODE.findall(FENCE.sub("", markdown))
    return any("**" in span for span in spans)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS. If one fails, fix the algorithm, not the expected values: every expected value follows `max(1, ceil(letters / 3))`.

- [ ] **Step 5: Commit**

```bash
git add compliance/bionic.py tests/test_bionic.py
git commit -m "feat: reference bionic algorithm and scorer"
```

---

### Task 6: Compliance scorer, prompts and runner

**Files:**
- Create: `compliance/score.py`
- Create: `compliance/prompts.txt`
- Create: `compliance/run.py`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `bionic.prose_only`, `bionic.score_bionic`, `bionic.bold_in_code`, `bionic.to_bionic`, `pace_config.defaults()`
- Produces:
  - `score.first_line_one_sentence(reply: str) -> bool`
  - `score.paragraphs_within(reply: str, limit: int = 3) -> bool`
  - `score.within_length(reply: str, limit: int) -> bool` (`limit` 0 means always True)
  - `score.action_line_last(reply: str) -> bool`
  - `score.bionic_ok(reply: str) -> bool` (at least 90% correct; True when there is no prose)
  - `score.score_reply(reply: str, cfg: dict) -> dict[str, bool]`, keyed by rule label, only for enabled switches
  - `run.load_prompts(path: Path = PROMPTS) -> list[str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_score.py`:
```python
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "compliance"))

import pace_config as pc  # noqa: E402
import run  # noqa: E402
import score  # noqa: E402
from bionic import to_bionic  # noqa: E402

GOOD = to_bionic(
    "The build failed because the merge dropped a plugin.\n\n"
    "Re-add it from the dev branch. Then run the tests.\n\n"
    "▶ You: approve the fix."
)


class ScoreReplyTest(unittest.TestCase):
    def test_should_pass_every_rule_when_reply_follows_them(self):
        self.assertEqual(set(score.score_reply(GOOD, pc.defaults()).values()), {True})

    def test_should_only_score_enabled_switches(self):
        cfg = {**pc.defaults(), "bionic": False, "length": 0}
        self.assertEqual(set(score.score_reply(GOOD, cfg)), {"answer first", "short paragraphs", "action line last"})


class FirstLineTest(unittest.TestCase):
    def test_should_fail_when_first_line_has_two_sentences(self):
        self.assertFalse(score.first_line_one_sentence("It failed. The merge broke it.\n\nMore."))

    def test_should_fail_when_reply_opens_with_heading(self):
        self.assertFalse(score.first_line_one_sentence("# Summary\nIt failed."))

    def test_should_pass_when_first_line_is_one_bionic_sentence(self):
        self.assertTrue(score.first_line_one_sentence("**I**t **fai**led.\n\nMore here. And here."))


class ParagraphsTest(unittest.TestCase):
    def test_should_fail_when_paragraph_has_four_sentences(self):
        self.assertFalse(score.paragraphs_within("One. Two. Three. Four."))

    def test_should_judge_each_list_item_on_its_own(self):
        self.assertTrue(score.paragraphs_within("- One. Two.\n- Three. Four.\n- Five."))

    def test_should_ignore_code_blocks(self):
        self.assertTrue(score.paragraphs_within("Done.\n\n```\na. b. c. d. e.\n```"))


class LengthTest(unittest.TestCase):
    def test_should_fail_when_over_limit(self):
        self.assertFalse(score.within_length("one two three four five", 4))

    def test_should_not_count_code_or_bold_markers(self):
        self.assertTrue(score.within_length("**on**e **tw**o\n```\nlots of code words here\n```", 2))

    def test_should_pass_when_limit_is_zero(self):
        self.assertTrue(score.within_length("word " * 500, 0))


class ActionLineTest(unittest.TestCase):
    def test_should_pass_when_marker_absent(self):
        self.assertTrue(score.action_line_last("Nothing to do."))

    def test_should_pass_when_marker_is_last_even_if_bionic(self):
        self.assertTrue(score.action_line_last("Done.\n\n▶ **Y**ou: **app**rove."))

    def test_should_fail_when_marker_is_followed_by_prose(self):
        self.assertFalse(score.action_line_last("▶ You: approve.\n\nAlso, more detail."))


class BionicOkTest(unittest.TestCase):
    def test_should_fail_when_under_ninety_percent(self):
        self.assertFalse(score.bionic_ok("**fo**cus plain words here"))

    def test_should_pass_when_no_prose(self):
        self.assertTrue(score.bionic_ok("```\ncode\n```"))


class PromptsTest(unittest.TestCase):
    def test_should_load_ten_prompts_without_comments(self):
        prompts = run.load_prompts()
        self.assertEqual(len(prompts), 10)
        self.assertFalse(any(p.startswith("#") for p in prompts))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: `test_score` ERRORs with `ModuleNotFoundError: No module named 'run'` or `'score'`.

- [ ] **Step 3: Write the scorer**

`compliance/score.py`:
```python
"""Score one reply against the enabled human-pace rules (spec §6.2)."""
from __future__ import annotations

import re
from typing import Dict, List

from bionic import bold_in_code, prose_only, score_bionic

SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
ENDS_CLOSED = re.compile(r"[.!?]['\")’]*$")
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s")
MARKER = "▶ You:"
BIONIC_THRESHOLD = 0.9


def _lines(text: str) -> List[str]:
    return [line for line in text.splitlines() if line.strip()]


def _sentences(text: str) -> int:
    text = text.replace("**", "").strip()
    if not text:
        return 0
    ends = len(SENTENCE_END.findall(text))
    return ends if ENDS_CLOSED.search(text) else ends + 1


def first_line_one_sentence(reply: str) -> bool:
    lines = _lines(reply)
    if not lines or lines[0].lstrip().startswith(("#", "```", "|")):
        return False
    return _sentences(lines[0]) <= 1


def paragraphs_within(reply: str, limit: int = 3) -> bool:
    for block in re.split(r"\n\s*\n", prose_only(reply)):
        prose = []
        for line in block.splitlines():
            if LIST_ITEM.match(line):
                if _sentences(line) > limit:
                    return False
            else:
                prose.append(line)
        if _sentences(" ".join(prose)) > limit:
            return False
    return True


def within_length(reply: str, limit: int) -> bool:
    if not limit:
        return True
    return len(prose_only(reply).replace("**", "").split()) <= limit


def action_line_last(reply: str) -> bool:
    lines = [line.replace("**", "") for line in _lines(reply)]
    marked = [i for i, line in enumerate(lines) if MARKER in line]
    return not marked or all(MARKER in line for line in lines[marked[0]:])


def bionic_ok(reply: str) -> bool:
    correct, total = score_bionic(reply)
    return total == 0 or correct / total >= BIONIC_THRESHOLD


def score_reply(reply: str, cfg: dict) -> Dict[str, bool]:
    results: Dict[str, bool] = {}
    if cfg.get("answerFirst"):
        results["answer first"] = first_line_one_sentence(reply)
    if cfg.get("chunks"):
        results["short paragraphs"] = paragraphs_within(reply)
    if cfg.get("length"):
        results["within length"] = within_length(reply, cfg["length"])
    if cfg.get("actionMarkers"):
        results["action line last"] = action_line_last(reply)
    if cfg.get("bionic"):
        results["bionic >= 90%"] = bionic_ok(reply)
        results["no bold in code"] = not bold_in_code(reply)
    return results
```

- [ ] **Step 4: Write the prompts**

`compliance/prompts.txt`:
```
# One prompt per line. Knowledge questions only, so claude -p answers without tools.
# The commit and Slack prompts check that text written for others stays unformatted.
Explain what a git rebase does.
Which command shows the process listening on port 8080 on macOS?
Should I use a list or a set in Python to de-duplicate items, and why?
Write a commit message for a change that adds retry logic to an HTTP client. Put it in a code block.
Summarise the trade-offs between REST and gRPC.
My Maven build fails with "package does not exist" after a merge. What should I check?
Give me the steps to rename a git branch locally and on the remote.
What is the difference between a process and a thread?
Draft a short Slack message telling my team the deploy is delayed until tomorrow. Put it in a code block.
Explain how HTTP caching headers work.
```

- [ ] **Step 5: Write the runner**

`compliance/run.py`:
```python
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


def main() -> int:
    cfg = pace_config.defaults()
    results: Dict[str, List[bool]] = {}
    prompts = load_prompts()
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if k != "HUMAN_PACE"}  # the kill switch must be off
        env["HUMAN_PACE_CONFIG"] = str(Path(tmp) / "absent.json")         # defaults, not your own switches
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
```

The runner uses a temporary working directory, so no project `CLAUDE.md` affects the replies. Your global `~/.claude/CLAUDE.md` still applies. If `human-pace` is also installed globally, the rules are injected twice. That is harmless, but run this before installing, or with the plugin disabled.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add compliance/score.py compliance/prompts.txt compliance/run.py tests/test_score.py
git commit -m "feat: compliance harness scoring replies against the rules"
```

---

### Task 7: README, end-to-end verification, and install

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything above. This task writes no new code, only verification against the real Claude Code.

- [ ] **Step 1: Write the README**

`README.md`:
````markdown
# human-pace

A Claude Code plugin that makes replies easier to follow: bionic reading, answer first, short
chunks, marked action items and a length cap. Every part can be switched on or off.

## Install

```
/plugin marketplace add <path-or-git-url-of-this-repo>
/plugin install human-pace@human-pace
```

Requires `python3` (3.9+). Without it the plugin does nothing, and your prompts are never blocked.

## Use

| Command | Effect |
|---|---|
| `/pace` | Show switches |
| `/pace <switch> on\|off` | `bionic`, `answerFirst`, `chunks`, `actionMarkers` |
| `/pace length <n>` | Prose word cap, `0` = no cap |
| `/pace reset` | Restore defaults |
| `/pace rate <1-5> [note]` | Log how the current setting feels |
| `/pace report` | Average rating per setting |

Changes apply from your next prompt. Settings live in `~/.claude/human-pace.json`, and ratings in
`~/.claude/human-pace-log.jsonl`.

Set `HUMAN_PACE=0` to turn the plugin off for scripts and CI that call `claude -p`.

## Develop

```
python3 -m unittest discover -s tests -v     # unit tests
python3 compliance/run.py                    # score real replies (calls claude -p, costs a few cents)
```

Rule wording lives in `rules/*.md`. Keep all fragments together under 700 characters.
````

- [ ] **Step 2: Validate the plugin and check its token cost**

Run: `claude plugin validate . && claude plugin details .`
Expected: validation passes, and the inventory lists the `UserPromptSubmit` hook and the `pace` command. If `details` rejects a path argument, run it after Step 7 as `claude plugin details human-pace`.

- [ ] **Step 3: Smoke-test the hook headless**

Run: `HUMAN_PACE_CONFIG="$PWD/.absent.json" claude -p --plugin-dir . "Explain what a git rebase does."`
Expected: a reply whose first line is one sentence, with words bolded on their first third (e.g. `**reb**ase`).

- [ ] **Step 4: Smoke-test the kill switch**

Run: `HUMAN_PACE=0 claude -p --plugin-dir . "Explain what a git rebase does."`
Expected: a normal reply with no bionic bolding. If it is still bionic, the hook is not inheriting Claude Code's environment. Stop and report this, because the spec's kill switch depends on it.

- [ ] **Step 5: Smoke-test `/pace` headless**

Run: `HUMAN_PACE_CONFIG="$PWD/.absent.json" claude -p --plugin-dir . "/human-pace:pace"`
Expected: `human-pace: bionic on · answerFirst on · chunks on · actionMarkers on · length 200`, unformatted.

- [ ] **Step 6: Run the compliance harness**

Run: `python3 compliance/run.py`
Expected: a pass count for each of the 6 rules. Record the table in the commit message below. A bionic pass rate under 7/10 is a finding to report to the user, not something to fix by loosening the threshold.

- [ ] **Step 7: Install from the local marketplace (ask the user first; this changes their global Claude Code settings)**

```bash
claude plugin marketplace add ~/IdeaProjects/human-pace
claude plugin install human-pace@human-pace
```
Expected: both commands succeed. In a new interactive session, `/pace` shows the switches, and a normal prompt gets a bionic reply.

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: README with install, usage and development

Compliance run (defaults): <paste the table printed in Step 6>"
```
