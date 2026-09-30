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
