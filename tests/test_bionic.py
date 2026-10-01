import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "compliance"))

import bionic  # noqa: E402


class BoldLengthTest(unittest.TestCase):
    def test_should_round_up_to_five_letters_and_down_above_with_minimum_one(self):
        cases = {"a": 1, "to": 1, "the": 1, "word": 2, "focus": 2, "about": 2, "plugin": 2, "reading": 2,
                 "patterns": 2, "everybody": 3, "understand": 3, "don't": 2}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.bold_length(word), expected)


class BionicWordTest(unittest.TestCase):
    def test_should_bold_prefix_when_given_spec_examples(self):
        cases = {"the": "**t**he", "focus": "**fo**cus", "reading": "**re**ading",
                 "understand": "**und**erstand", "don't": "**do**n't", "I'm": "**I**'m"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.third_word(word), expected)

    def test_should_split_on_hyphen_and_skip_numbers_when_converting_text(self):
        self.assertEqual(bionic.to_bionic("Re-add the plugin 3 times."),
                         "**R**e-**a**dd **t**he **pl**ugin 3 **ti**mes.")


class VowelTest(unittest.TestCase):
    def test_should_count_y_and_accented_and_upper_case_vowels(self):
        for c in "aeiouyAEIOUYéÉÿæœÆŒ":
            with self.subTest(c=c):
                self.assertTrue(bionic.is_vowel(c))
        for c in "bcdzBZçñ'":
            with self.subTest(c=c):
                self.assertFalse(bionic.is_vowel(c))


class ApproachWordTest(unittest.TestCase):
    def test_should_bold_every_vowel_run_when_vowels(self):
        cases = {"understand": "**u**nd**e**rst**a**nd", "easy": "**ea**s**y**", "rhythm": "rh**y**thm",
                 "École": "**É**c**o**l**e**", "YES": "**YE**S", "don't": "d**o**n't"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.vowels_word(word), expected)

    def test_should_bold_every_consonant_run_when_consonants(self):
        cases = {"understand": "u**nd**e**rst**a**nd**", "easy": "ea**s**y", "a": "a",
                 "don't": "**d**o**n**'**t**"}
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(bionic.consonants_word(word), expected)

    def test_should_never_emit_four_asterisks(self):
        for fn in (bionic.vowels_word, bionic.consonants_word, bionic.third_word,
                   lambda w: bionic.anchor_word(w, 2)):
            for word in ("understand", "easy", "queueing", "strengths", "don't"):
                with self.subTest(fn=fn, word=word):
                    self.assertNotIn("****", fn(word))


class LigatureTest(unittest.TestCase):
    def test_should_treat_ligatures_as_vowels(self):
        self.assertEqual(bionic.vowels_word("Æsop"), "**Æ**s**o**p")
        self.assertEqual(bionic.consonants_word("œuvre"), "œu**vr**e")


class AnchorWordTest(unittest.TestCase):
    def test_should_bold_last_consonant_when_long_word_ends_in_vowel(self):
        self.assertEqual(bionic.anchor_word("experience"), "**exp**erien**c**e")
        self.assertEqual(bionic.anchor_word("everybody"), "**eve**rybo**d**y")

    def test_should_bold_second_to_last_consonant_when_long_word_ends_in_consonant(self):
        self.assertEqual(bionic.anchor_word("understand"), "**und**ersta**n**d")

    def test_should_bold_as_third_when_shorter_than_trigger(self):
        self.assertEqual(bionic.anchor_word("reading"), "**re**ading")
        self.assertEqual(bionic.anchor_word("reading", 7), "**re**adi**n**g")

    def test_should_skip_anchor_right_after_prefix(self):
        # "planter": 7 letters, trigger 7, prefix "pl", ends in r -> t, not next to the prefix.
        self.assertEqual(bionic.anchor_word("planter", 7), "**pl**an**t**er")
        # "abbey": prefix "ab", ends in y (vowel) -> last consonant is the 2nd b, right after the prefix.
        self.assertEqual(bionic.anchor_word("abbey", 2), "**ab**bey")
        # "ebb": prefix "e", ends in b -> second-to-last consonant is the 1st b, right after the prefix.
        self.assertEqual(bionic.anchor_word("ebb", 2), "**e**bb")

    def test_should_bold_as_third_when_anchor_inside_prefix_or_missing(self):
        # "queue": prefix "qu", ends in a vowel -> last consonant is q, already bold.
        self.assertEqual(bionic.anchor_word("queue", 2), "**qu**eue")
        # "aeiouaei": no consonant at all.
        self.assertEqual(bionic.anchor_word("aeiouaei", 8), "**ae**iouaei")

    def test_should_skip_apostrophe_when_counting_and_bolding(self):
        # shouldn't: 8 letters, ends in t -> second-to-last consonant is n.
        self.assertEqual(bionic.anchor_word("shouldn't"), "**sh**ould**n**'t")
        # can't: 4 letters, under the trigger.
        self.assertEqual(bionic.anchor_word("can't"), "**ca**n't")


class WordFunctionTest(unittest.TestCase):
    def test_should_return_matching_function_for_every_approach(self):
        self.assertEqual(bionic.APPROACHES, ("third", "vowels", "consonants", "third+anchor"))
        self.assertEqual(bionic.word_function("vowels")("easy"), "**ea**s**y**")
        self.assertEqual(bionic.word_function("third+anchor", 7)("reading"), "**re**adi**n**g")

    def test_should_score_against_chosen_approach(self):
        text = bionic.to_bionic("The build failed because the merge dropped a plugin.", "vowels")
        self.assertEqual(bionic.score_bionic(text, "vowels"), (9, 9))
        self.assertLess(bionic.score_bionic(text)[0], 9)


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
        self.assertEqual(bionic.score_bionic("- **fo**cus\n▶ **Y**ou: **ap**prove"), (3, 3))

    def test_should_return_zero_total_when_no_prose(self):
        self.assertEqual(bionic.score_bionic("```\ncode\n```"), (0, 0))


RULES = Path(__file__).resolve().parent.parent / "rules"
RULE_FILES = {"third": "bionic-third.md", "vowels": "bionic-vowels.md", "consonants": "bionic-consonants.md",
              "third+anchor": "bionic-third-anchor.md"}


class RuleExamplesTest(unittest.TestCase):
    def rule(self, approach):
        return (RULES / RULE_FILES[approach]).read_text(encoding="utf-8").replace("{anchorTrigger}", "8")

    def test_should_match_checker_for_every_bold_example_in_rule_fragments(self):
        for approach in bionic.APPROACHES:
            examples = [part.strip(".,:;") for token in self.rule(approach).split()
                        for part in token.split("-") if "**" in part]
            self.assertTrue(examples, approach)
            for example in examples:
                with self.subTest(approach=approach, example=example):
                    self.assertEqual(bionic.word_function(approach)(example.replace("**", "")), example)

    def test_should_say_accented_vowels_are_vowels_in_letter_rules(self):
        for approach in ("vowels", "consonants"):
            with self.subTest(approach=approach):
                self.assertIn("accented", self.rule(approach))

    def test_should_show_anchor_that_differs_from_the_letter_before_the_last_consonant(self):
        # In "understand" the letter before the last consonant and the anchor are both "n".
        self.assertIn("**inf**orma**t**ion", self.rule("third+anchor"))


class BoldInCodeTest(unittest.TestCase):
    def test_should_detect_bold_inside_fenced_or_inline_code(self):
        self.assertTrue(bionic.bold_in_code("```\n**fi**x: retry\n```"))
        self.assertTrue(bionic.bold_in_code("run `**gi**t push`"))

    def test_should_pass_when_bold_only_in_prose(self):
        self.assertFalse(bionic.bold_in_code("**fo**cus `git push`\n```\nfix: retry\n```"))


if __name__ == "__main__":
    unittest.main()
