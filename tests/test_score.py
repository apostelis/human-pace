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


class HarnessEnvTest(unittest.TestCase):
    def test_should_force_plugin_on_with_default_config_when_run_headless(self):
        env = run.harness_env("/scratch")
        self.assertEqual(env["HUMAN_PACE"], "1")
        self.assertEqual(env["HUMAN_PACE_CONFIG"], str(Path("/scratch") / "absent.json"))


class PromptsTest(unittest.TestCase):
    def test_should_load_ten_prompts_without_comments(self):
        prompts = run.load_prompts()
        self.assertEqual(len(prompts), 10)
        self.assertFalse(any(p.startswith("#") for p in prompts))


if __name__ == "__main__":
    unittest.main()
