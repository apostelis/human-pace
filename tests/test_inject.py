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
