import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
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
                         "human-pace: bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200"
                         " · drift guard every 10 prompts")

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


class PresetTest(PaceTestBase):
    def test_should_turn_everything_on_when_focus_preset(self):
        pace.run(["bionic", "off"])
        pace.run(["preset", "focus"])
        self.assertEqual(pc.load_config(), (pc.DEFAULTS, None))

    def test_should_drop_only_bionic_and_raise_cap_when_light_preset(self):
        out = pace.run(["preset", "light"])
        self.assertIn("Applies from your next prompt.", out)
        self.assertEqual(pc.load_config()[0], {**pc.DEFAULTS, "bionic": False, "length": 300})

    def test_should_turn_everything_off_including_cap_when_off_preset(self):
        pace.run(["preset", "off"])
        cfg = pc.load_config()[0]
        self.assertFalse(any(cfg[name] for name in pc.SWITCHES))
        self.assertEqual(cfg["length"], 0)

    def test_should_match_presets_when_on_and_off_shortcuts_used(self):
        pace.run(["off"])
        cfg = pc.load_config()[0]
        self.assertEqual({key: cfg[key] for key in pace.PRESETS["off"]}, pace.PRESETS["off"])
        pace.run(["ON"])
        self.assertEqual(pc.load_config()[0], pc.DEFAULTS)

    def test_should_print_usage_and_change_nothing_when_preset_unknown(self):
        for args in (["preset"], ["preset", "turbo"], ["preset", "off", "now"], ["off", "now"]):
            with self.subTest(args=args):
                self.assertEqual(pace.run(args), pace.USAGE)
                self.assertFalse(self.config.exists())

    def test_should_list_presets_in_usage_and_command_hint(self):
        hint = (ROOT / "commands" / "pace.md").read_text(encoding="utf-8")
        for name in pace.PRESETS:
            with self.subTest(preset=name):
                self.assertIn(name, pace.USAGE)
                self.assertIn(name, hint)


class ApproachTest(PaceTestBase):
    def test_should_set_approach_and_turn_bionic_on(self):
        pace.run(["bionic", "off"])
        out = pace.run(["bionic", "Vowels"])
        self.assertIn("bionic on (vowels)", out)
        cfg = pc.load_config()[0]
        self.assertTrue(cfg["bionic"])
        self.assertEqual(cfg["bionicApproach"], "vowels")

    def test_should_accept_every_approach(self):
        for approach in pc.APPROACHES:
            with self.subTest(approach=approach):
                pace.run(["bionic", approach])
                self.assertEqual(pc.load_config()[0]["bionicApproach"], approach)

    def test_should_show_trigger_only_for_third_anchor(self):
        self.assertIn("bionic on (third+anchor, 8+ letters)", pace.run(["bionic", "third+anchor"]))
        self.assertIn("bionic on (third+anchor, 10+ letters)", pace.run(["anchor-trigger", "10"]))
        self.assertIn("bionic on (consonants) ·", pace.run(["bionic", "consonants"]))

    def test_should_set_trigger_without_changing_approach(self):
        pace.run(["bionic", "vowels"])
        pace.run(["anchor-trigger", "5"])
        cfg = pc.load_config()[0]
        self.assertEqual((cfg["bionicApproach"], cfg["anchorTrigger"]), ("vowels", 5))

    def test_should_print_usage_and_change_nothing_when_approach_or_trigger_invalid(self):
        for args in (["bionic", "bold"], ["anchor-trigger"], ["anchor-trigger", "1"], ["anchor-trigger", "51"],
                     ["anchor-trigger", "x"], ["anchor-trigger", "8", "9"], ["bionic", "vowels", "now"]):
            with self.subTest(args=args):
                self.assertEqual(pace.run(args), pace.USAGE)
                self.assertFalse(self.config.exists())

    def test_should_keep_approach_and_trigger_when_preset_applied(self):
        pace.run(["bionic", "third+anchor"])
        pace.run(["anchor-trigger", "6"])
        for name in ("light", "off", "focus"):
            with self.subTest(preset=name):
                pace.run(["preset", name])
                cfg = pc.load_config()[0]
                self.assertEqual((cfg["bionicApproach"], cfg["anchorTrigger"]), ("third+anchor", 6))

    def test_should_restore_approach_and_trigger_when_reset(self):
        pace.run(["bionic", "vowels"])
        pace.run(["anchor-trigger", "5"])
        pace.run(["reset"])
        self.assertEqual(pc.load_config(), (pc.DEFAULTS, None))

    def test_should_list_approaches_and_trigger_in_usage_and_command_hint(self):
        hint = (ROOT / "commands" / "pace.md").read_text(encoding="utf-8")
        for word in (*pc.APPROACHES, "anchor-trigger"):
            with self.subTest(word=word):
                self.assertIn(word, pace.USAGE)
                self.assertIn(word, hint)


class DriftGuardTest(PaceTestBase):
    def test_should_set_interval_and_show_it(self):
        self.assertIn("drift guard every 25 prompts", pace.run(["drift-guard", "25"]))
        self.assertEqual(pc.load_config()[0]["driftGuard"], 25)

    def test_should_turn_off_when_zero(self):
        self.assertIn("drift guard off", pace.run(["drift-guard", "0"]))
        self.assertEqual(pc.load_config()[0]["driftGuard"], 0)

    def test_should_print_usage_and_change_nothing_when_interval_invalid(self):
        for args in (["drift-guard"], ["drift-guard", "101"], ["drift-guard", "x"], ["drift-guard", "5", "6"]):
            with self.subTest(args=args):
                self.assertEqual(pace.run(args), pace.USAGE)
                self.assertFalse(self.config.exists())

    def test_should_keep_interval_when_preset_applied_and_restore_on_reset(self):
        pace.run(["drift-guard", "4"])
        for name in ("off", "light", "focus"):
            with self.subTest(preset=name):
                pace.run(["preset", name])
                self.assertEqual(pc.load_config()[0]["driftGuard"], 4)
        pace.run(["reset"])
        self.assertEqual(pc.load_config()[0]["driftGuard"], 10)

    def test_should_leave_drift_guard_out_of_rating_text(self):
        pace.run(["drift-guard", "4"])
        self.assertNotIn("drift guard", pace.run(["rate", "3"], now=NOW))

    def test_should_list_drift_guard_in_usage_and_command_hint(self):
        self.assertIn("drift-guard", pace.USAGE)
        self.assertIn("drift-guard", (ROOT / "commands" / "pace.md").read_text(encoding="utf-8"))


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

    def test_should_print_usage_when_number_uses_non_ascii_digits(self):
        for args in (["length", "²"], ["rate", "²"], ["length", "١٥٠"]):
            with self.subTest(args=args):
                self.assertEqual(pace.run(args, now=NOW), pace.USAGE)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.config.exists())

    def test_should_not_create_config_when_rating(self):
        pace.run(["rate", "3"], now=NOW)
        self.assertFalse(self.config.exists())

    def test_should_start_new_line_when_log_ends_mid_line(self):
        self.log.parent.mkdir(parents=True)
        self.log.write_text('{"ts": "t", "swi', encoding="utf-8")  # crash mid-write, no newline
        pace.run(["rate", "5"], now=NOW)
        self.assertEqual(pace.run(["report"]),
                         "5.0 avg · 1 rating · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200")

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
            "4.5 avg · 2 ratings · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200",
            "2.0 avg · 1 rating · bionic off · answerFirst on · chunks on · actionMarkers on · length 200",
        ])

    def test_should_skip_line_cut_inside_multibyte_character_when_reporting(self):
        self.log.parent.mkdir(parents=True)
        self.log.write_bytes(self.entry(4).encode() + b'\n{"note": "caf\xc3\n' + self.entry(2).encode() + b"\n")
        self.assertEqual(pace.run(["report"]),
                         "3.0 avg · 2 ratings · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_skip_hand_edited_entries_when_values_invalid(self):
        bad_score = json.dumps({"ts": "t", "switches": pc.DEFAULTS, "score": 99, "note": ""})
        bad_switch = json.dumps({"ts": "t", "switches": {**pc.DEFAULTS, "bionic": "no"}, "score": 1, "note": ""})
        bad_length = json.dumps({"ts": "t", "switches": {**pc.DEFAULTS, "length": "long"}, "score": 1, "note": ""})
        self.write_log([self.entry(4), bad_score, bad_switch, bad_length])
        self.assertEqual(pace.run(["report"]),
                         "4.0 avg · 1 rating · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_skip_corrupt_lines_when_reporting(self):
        self.write_log([self.entry(4), '{"ts": "t", "swi', "[]", '{"switches": {}, "score": "5"}', self.entry(2)])
        self.assertEqual(pace.run(["report"]),
                         "3.0 avg · 2 ratings · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_keep_old_rounding_ratings_apart_from_new_third(self):
        old = {"bionic": True, "answerFirst": True, "chunks": True, "actionMarkers": True, "length": 200}
        self.write_log([json.dumps({"ts": "t", "switches": old, "score": 2, "note": ""}), self.entry(4)])
        self.assertEqual(pace.run(["report"]).splitlines(), [
            "4.0 avg · 1 rating · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200",
            "2.0 avg · 1 rating · bionic on (third, 0.4 rounding) · answerFirst on · chunks on · actionMarkers on · length 200",
        ])

    def test_should_group_old_entries_with_bionic_off_like_new_ones(self):
        old = {"bionic": False, "answerFirst": True, "chunks": True, "actionMarkers": True, "length": 200}
        self.write_log([json.dumps({"ts": "t", "switches": old, "score": 2, "note": ""}), self.entry(4, bionic=False)])
        self.assertEqual(pace.run(["report"]),
                         "3.0 avg · 2 ratings · bionic off · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_ignore_settings_without_effect_when_grouping(self):
        self.write_log([self.entry(4, bionicApproach="vowels", anchorTrigger=5),
                        self.entry(2, bionicApproach="vowels", anchorTrigger=9),
                        self.entry(5, bionic=False, bionicApproach="consonants"),
                        self.entry(3, bionic=False)])
        self.assertEqual(pace.run(["report"]).splitlines(), [
            "4.0 avg · 2 ratings · bionic off · answerFirst on · chunks on · actionMarkers on · length 200",
            "3.0 avg · 2 ratings · bionic on (vowels) · answerFirst on · chunks on · actionMarkers on · length 200",
        ])

    def test_should_ignore_drift_guard_when_grouping(self):
        self.write_log([self.entry(4, driftGuard=10), self.entry(2, driftGuard=0)])
        self.assertEqual(pace.run(["report"]),
                         "3.0 avg · 2 ratings · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_split_groups_by_trigger_when_third_anchor(self):
        self.write_log([self.entry(4, bionicApproach="third+anchor", anchorTrigger=6),
                        self.entry(2, bionicApproach="third+anchor", anchorTrigger=9)])
        self.assertEqual(len(pace.run(["report"]).splitlines()), 2)


if __name__ == "__main__":
    unittest.main()


from analytics_test_support import isolated_analytics
setUpModule, tearDownModule = isolated_analytics()
