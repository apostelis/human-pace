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

    def test_should_return_defaults_and_error_when_file_not_utf8(self):
        self.path.write_bytes(b'{"bionic": "\xe9"}')
        cfg, error = pc.load_config(self.path)
        self.assertEqual(cfg, pc.DEFAULTS)
        self.assertIn("not valid UTF-8", error)

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

    def test_should_default_new_keys_when_config_predates_them(self):
        self.write(json.dumps({"bionic": True, "answerFirst": True, "chunks": True,
                               "actionMarkers": True, "length": 200}))
        cfg, error = pc.load_config(self.path)
        self.assertEqual(cfg["bionicApproach"], "third")
        self.assertEqual(cfg["anchorTrigger"], 8)
        self.assertIsNone(error)

    def test_should_accept_every_approach_and_trigger_from_two(self):
        for approach in pc.APPROACHES:
            with self.subTest(approach=approach):
                self.write(json.dumps({"bionicApproach": approach, "anchorTrigger": 2}))
                self.assertEqual(pc.load_config(self.path), ({**pc.DEFAULTS, "bionicApproach": approach,
                                                             "anchorTrigger": 2}, None))

    def test_should_fall_back_and_report_when_approach_or_trigger_invalid(self):
        for data, key in (({"bionicApproach": "Vowels"}, "bionicApproach"),
                          ({"bionicApproach": 3}, "bionicApproach"),
                          ({"anchorTrigger": 1}, "anchorTrigger"),
                          ({"anchorTrigger": 51}, "anchorTrigger"),
                          ({"anchorTrigger": True}, "anchorTrigger"),
                          ({"anchorTrigger": "8"}, "anchorTrigger")):
            with self.subTest(data=data):
                self.write(json.dumps(data))
                cfg, error = pc.load_config(self.path)
                self.assertEqual(cfg, pc.DEFAULTS)
                self.assertIn(key, error)

    def test_should_accept_trigger_up_to_fifty(self):
        self.write(json.dumps({"anchorTrigger": 50}))
        self.assertEqual(pc.load_config(self.path)[0]["anchorTrigger"], 50)

    def test_should_accept_drift_guard_from_zero_to_hundred(self):
        self.assertEqual(pc.DEFAULTS["driftGuard"], 10)
        for value in (0, 100):
            with self.subTest(value=value):
                self.write(json.dumps({"driftGuard": value}))
                self.assertEqual(pc.load_config(self.path), ({**pc.DEFAULTS, "driftGuard": value}, None))

    def test_should_fall_back_and_report_when_drift_guard_invalid(self):
        for bad in (-1, 101, True, "10", 2.5):
            with self.subTest(bad=bad):
                self.write(json.dumps({"driftGuard": bad}))
                cfg, error = pc.load_config(self.path)
                self.assertEqual(cfg["driftGuard"], 10)
                self.assertIn("driftGuard", error)

    def test_should_list_the_same_approaches_as_the_checker(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "compliance"))
        import bionic
        self.assertEqual(pc.APPROACHES, bionic.APPROACHES)

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

    def test_should_keep_symlink_and_update_target_when_config_is_symlinked(self):
        target = Path(self.dir.name) / "dotfiles" / "human-pace.json"
        target.parent.mkdir()
        target.write_text("{}", encoding="utf-8")
        link = Path(self.dir.name) / "human-pace.json"
        link.symlink_to(target)
        pc.save_config({**pc.defaults(), "bionic": False}, link)
        self.assertTrue(link.is_symlink())
        self.assertFalse(json.loads(target.read_text(encoding="utf-8"))["bionic"])

    def test_should_save_when_another_writer_holds_the_old_tmp_name(self):
        path = Path(self.dir.name) / "human-pace.json"
        (Path(self.dir.name) / "human-pace.json.tmp").mkdir()
        pc.save_config(pc.defaults(), path)
        self.assertEqual(pc.load_config(path), (pc.DEFAULTS, None))

    def test_should_leave_no_temp_files_when_saved(self):
        path = Path(self.dir.name) / "human-pace.json"
        pc.save_config(pc.defaults(), path)
        self.assertEqual([p.name for p in Path(self.dir.name).iterdir()], ["human-pace.json"])

    def test_should_drop_unknown_keys_when_saving(self):
        path = Path(self.dir.name) / "human-pace.json"
        pc.save_config({**pc.defaults(), "extra": 1}, path)
        self.assertNotIn("extra", json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
