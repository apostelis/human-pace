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

    def test_should_stay_within_budget_for_every_approach(self):
        for approach in pc.APPROACHES:
            for trigger in (pc.MIN_ANCHOR_TRIGGER, 8, pc.MAX_ANCHOR_TRIGGER):
                with self.subTest(approach=approach, trigger=trigger):
                    rules = inject.build_rules(cfg(bionicApproach=approach, anchorTrigger=trigger))
                    self.assertLessEqual(len(rules), 700)

    def test_should_send_only_the_active_approach_fragment(self):
        markers = {"third": "first third", "vowels": "every vowel", "consonants": "every consonant",
                   "third+anchor": "also bold"}
        for approach, marker in markers.items():
            with self.subTest(approach=approach):
                rules = inject.build_rules(cfg(bionicApproach=approach))
                self.assertEqual(rules.count("Bionic reading"), 1)
                self.assertIn(marker, rules)
                for other, other_marker in markers.items():
                    # third+anchor's wording also says "first third"; every other pair must differ.
                    if other != approach and (approach, other) != ("third+anchor", "third"):
                        self.assertNotIn(other_marker, rules)

    def test_should_substitute_anchor_trigger_when_third_anchor(self):
        rules = inject.build_rules(cfg(bionicApproach="third+anchor", anchorTrigger=11))
        self.assertIn("11+ letters", rules)
        self.assertNotIn("{anchorTrigger}", rules)

    def test_should_have_a_fragment_file_for_every_approach(self):
        self.assertEqual(set(inject.BIONIC_FRAGMENTS), set(pc.APPROACHES))
        for name in inject.BIONIC_FRAGMENTS.values():
            with self.subTest(name=name):
                self.assertTrue((inject.RULES_DIR / name).is_file())


class ShouldSkipTest(unittest.TestCase):
    def test_should_skip_when_kill_switch_set(self):
        self.assertTrue(inject.should_skip({"prompt": "hi"}, {"HUMAN_PACE": "0"}))

    def test_should_skip_when_run_headless_through_the_sdk(self):
        for entrypoint in ("sdk-cli", "sdk-py", "sdk-ts"):
            with self.subTest(entrypoint=entrypoint):
                self.assertTrue(inject.should_skip({"prompt": "hi"}, {"CLAUDE_CODE_ENTRYPOINT": entrypoint}))

    def test_should_not_skip_headless_when_forced_on(self):
        env = {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "HUMAN_PACE": "1"}
        self.assertFalse(inject.should_skip({"prompt": "hi"}, env))

    def test_should_not_skip_when_interactive(self):
        self.assertFalse(inject.should_skip({"prompt": "hi"}, {"CLAUDE_CODE_ENTRYPOINT": "cli"}))

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


class OncePerSessionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.config = Path(self.dir.name) / "human-pace.json"
        self.state = Path(self.dir.name) / "state"
        self.env = mock.patch.dict(os.environ, {"HUMAN_PACE_CONFIG": str(self.config),
                                                "HUMAN_PACE_STATE": str(self.state)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()

    def send(self, event, session="s1", prompt="hi"):
        hook_input = {"hook_event_name": event, "session_id": session}
        if event == "UserPromptSubmit":
            hook_input["prompt"] = prompt
        out = io.StringIO()
        self.assertEqual(inject.main(io.StringIO(json.dumps(hook_input)), out, {}), 0)
        if not out.getvalue():
            return None
        payload = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(payload["hookEventName"], event)
        return payload["additionalContext"]

    def test_should_send_rules_when_session_starts(self):
        self.assertIn("Bionic reading", self.send("SessionStart"))

    def test_should_stay_silent_on_prompt_when_rules_unchanged_since_session_start(self):
        self.send("SessionStart")
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertIsNone(self.send("UserPromptSubmit"))

    def test_should_resend_rules_once_when_switches_change_mid_session(self):
        self.send("SessionStart")
        pc.save_config({**pc.defaults(), "bionic": False}, self.config)
        update = self.send("UserPromptSubmit")
        self.assertTrue(update.startswith("human-pace rules changed; these replace the earlier ones."))
        self.assertNotIn("Bionic reading", update)
        self.assertIsNone(self.send("UserPromptSubmit"))

    def test_should_tell_model_to_stop_when_everything_turned_off_mid_session(self):
        self.send("SessionStart")
        pc.save_config({**pc.defaults(), "bionic": False, "answerFirst": False, "chunks": False,
                        "actionMarkers": False, "length": 0}, self.config)
        self.assertEqual(self.send("UserPromptSubmit"), inject.OFF_NOTICE)
        self.assertIsNone(self.send("UserPromptSubmit"))

    def test_should_stay_silent_all_session_when_everything_off(self):
        pc.save_config({**pc.defaults(), "bionic": False, "answerFirst": False, "chunks": False,
                        "actionMarkers": False, "length": 0}, self.config)
        self.assertIsNone(self.send("SessionStart"))
        self.assertIsNone(self.send("UserPromptSubmit"))

    def test_should_resend_rules_once_when_approach_changes_mid_session(self):
        self.send("SessionStart")
        pc.save_config({**pc.defaults(), "bionicApproach": "vowels"}, self.config)
        update = self.send("UserPromptSubmit")
        self.assertTrue(update.startswith("human-pace rules changed; these replace the earlier ones."))
        self.assertIn("every vowel", update)
        self.assertIsNone(self.send("UserPromptSubmit"))

    def test_should_remind_once_every_drift_guard_prompts(self):
        pc.save_config({**pc.defaults(), "driftGuard": 3}, self.config)
        self.send("SessionStart")
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertIsNone(self.send("UserPromptSubmit"))
        reminder = self.send("UserPromptSubmit")
        self.assertTrue(reminder.startswith(inject.REMINDER_PREFIX))
        self.assertIn("Bionic reading", reminder)
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertTrue(self.send("UserPromptSubmit").startswith(inject.REMINDER_PREFIX))

    def test_should_remind_after_ten_prompts_by_default(self):
        self.send("SessionStart")
        replies = [self.send("UserPromptSubmit") for _ in range(10)]
        self.assertEqual(replies[:9], [None] * 9)
        self.assertTrue(replies[9].startswith(inject.REMINDER_PREFIX))

    def test_should_never_remind_when_drift_guard_off(self):
        pc.save_config({**pc.defaults(), "driftGuard": 0}, self.config)
        self.send("SessionStart")
        self.assertEqual([self.send("UserPromptSubmit") for _ in range(25)], [None] * 25)

    def test_should_not_remind_when_everything_off(self):
        pc.save_config({**pc.defaults(), "bionic": False, "answerFirst": False, "chunks": False,
                        "actionMarkers": False, "length": 0, "driftGuard": 2}, self.config)
        self.send("SessionStart")
        self.assertEqual([self.send("UserPromptSubmit") for _ in range(5)], [None] * 5)

    def test_should_restart_count_when_rules_change(self):
        pc.save_config({**pc.defaults(), "driftGuard": 3}, self.config)
        self.send("SessionStart")
        self.send("UserPromptSubmit")
        self.send("UserPromptSubmit")
        pc.save_config({**pc.defaults(), "driftGuard": 3, "bionic": False}, self.config)
        self.assertTrue(self.send("UserPromptSubmit").startswith("human-pace rules changed"))
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertTrue(self.send("UserPromptSubmit").startswith(inject.REMINDER_PREFIX))

    def test_should_count_from_zero_when_state_file_predates_drift_guard(self):
        pc.save_config({**pc.defaults(), "driftGuard": 2}, self.config)
        self.send("SessionStart")
        digest = (self.state / "s1").read_text(encoding="utf-8").splitlines()[0]
        (self.state / "s1").write_text(digest, encoding="utf-8")  # 0.5 format: digest only
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertTrue(self.send("UserPromptSubmit").startswith(inject.REMINDER_PREFIX))

    def test_should_count_from_zero_when_state_count_is_corrupt(self):
        pc.save_config({**pc.defaults(), "driftGuard": 2}, self.config)
        self.send("SessionStart")
        digest = (self.state / "s1").read_text(encoding="utf-8").splitlines()[0]
        (self.state / "s1").write_text(f"{digest}\n²", encoding="utf-8")
        self.assertIsNone(self.send("UserPromptSubmit"))
        self.assertTrue(self.send("UserPromptSubmit").startswith(inject.REMINDER_PREFIX))

    def test_should_resend_when_session_restarts_after_compaction(self):
        self.send("SessionStart")
        self.assertIn("Bionic reading", self.send("SessionStart"))

    def test_should_track_sessions_separately(self):
        self.send("SessionStart", session="a")
        self.assertIsNone(self.send("UserPromptSubmit", session="a"))
        self.assertIn("Bionic reading", self.send("UserPromptSubmit", session="b"))

    def test_should_send_every_prompt_when_session_id_missing_or_unsafe(self):
        for session in (None, "../escape"):
            with self.subTest(session=session):
                self.assertIn("Bionic reading", self.send("UserPromptSubmit", session=session))
                self.assertIn("Bionic reading", self.send("UserPromptSubmit", session=session))

    def test_should_fall_back_to_every_prompt_when_state_unwritable(self):
        self.state.write_text("a file where the directory should be", encoding="utf-8")
        self.assertIn("Bionic reading", self.send("SessionStart"))
        self.assertIn("Bionic reading", self.send("UserPromptSubmit"))

    def test_should_prune_state_older_than_a_week_when_session_starts(self):
        self.state.mkdir()
        old = self.state / "old-session"
        old.write_text("x", encoding="utf-8")
        os.utime(old, (0, 0))
        self.send("SessionStart")
        self.assertFalse(old.exists())
        self.assertTrue((self.state / "s1").exists())


class ScriptTest(unittest.TestCase):
    def run_script(self, extra_env):
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k not in ("HUMAN_PACE", "CLAUDE_CODE_ENTRYPOINT")}
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
    def test_should_register_fail_open_hook_for_session_start_and_prompts(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for event in ("SessionStart", "UserPromptSubmit"):
            with self.subTest(event=event):
                command = hooks["hooks"][event][0]["hooks"][0]["command"]
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/inject.py", command)
                self.assertTrue(command.endswith("|| true"))


if __name__ == "__main__":
    unittest.main()


from analytics_test_support import isolated_analytics
setUpModule, tearDownModule = isolated_analytics()
