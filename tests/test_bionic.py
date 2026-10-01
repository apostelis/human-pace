import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "compliance"))

import bionic  # noqa: E402


class BoldLengthTest(unittest.TestCase):
    def test_should_bold_a_third_rounded_down_with_minimum_one(self):
        cases = {"a": 1, "to": 1, "the": 1, "focus": 1, "plugin": 2, "reading": 2, "patterns": 2,
                 "everybody": 3, "understand": 3, "don't": 1}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.bold_length(word), expected)


class BionicWordTest(unittest.TestCase):
    def test_should_bold_prefix_when_given_spec_examples(self):
        cases = {"the": "**t**he", "focus": "**f**ocus", "reading": "**re**ading",
                 "understand": "**und**erstand", "don't": "**d**on't", "I'm": "**I**'m"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.bionic_word(word), expected)

    def test_should_split_on_hyphen_and_skip_numbers_when_converting_text(self):
        self.assertEqual(bionic.to_bionic("Re-add the plugin 3 times."),
                         "**R**e-**a**dd **t**he **pl**ugin 3 **t**imes.")


class ScoreBionicTest(unittest.TestCase):
    def test_should_score_all_correct_when_text_is_reference_output(self):
        text = bionic.to_bionic("The build failed because the merge dropped a plugin.")
        self.assertEqual(bionic.score_bionic(text), (9, 9))

    def test_should_count_wrong_prefix_when_bolding_too_much(self):
        self.assertEqual(bionic.score_bionic("**f**ocus **readi**ng"), (1, 2))

    def test_should_count_emphasis_bold_as_wrong_when_bionic_on(self):
        self.assertEqual(bionic.score_bionic("**Note:** **f**ocus"), (1, 2))

    def test_should_ignore_code_paths_urls_headings_tables_and_identifiers(self):
        markdown = ("# Heading words\n"
                    "**f**ocus `inline code` src/app.py answerFirst e.g. https://x.io/a\n"
                    "| cell | words |\n"
                    "```\nplain words here\n```\n")
        self.assertEqual(bionic.score_bionic(markdown), (1, 1))

    def test_should_score_bullets_and_action_line_when_formatted(self):
        self.assertEqual(bionic.score_bionic("- **f**ocus\n▶ **Y**ou: **ap**prove"), (3, 3))

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
