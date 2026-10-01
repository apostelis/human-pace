# Bionic Approaches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user switch the bionic bolding between four approaches (`third`, `vowels`, `consonants`, `third+anchor`), make `third` round down, and compare approaches through `/pace report`.

**Architecture:** `compliance/bionic.py` is the reference algorithm: one word function per approach, built on a shared "mark letters, then wrap runs in `**`" renderer. `scripts/pace_config.py` gains two config keys, `scripts/pace.py` the commands, status text and report grouping, and `scripts/inject.py` picks one rule fragment per approach. The compliance harness scores whichever approach it is told to.

**Tech Stack:** Python 3.9+ standard library only (`unittest`, `unicodedata`, `argparse`). No third-party packages.

**Spec:** `docs/superpowers/specs/2026-10-01-bionic-approaches-design.md`

## Global Constraints

- Python 3.9+ standard library only; the macOS system `python3` is 3.9.
- Approach names, exactly: `third`, `vowels`, `consonants`, `third+anchor`. User-facing term: "approach".
- Config keys, exactly: `bionicApproach` (default `"third"`), `anchorTrigger` (default `8`, integer ≥ 2).
- Commands, exactly: `/pace bionic <approach>`, `/pace anchor-trigger <n>`.
- `third` bold length: `max(1, floor(letters / 3))`.
- Vowels: base letter after Unicode NFD is one of `a e i o u y`, either case. Every other letter is a consonant. Apostrophes are neither.
- Adjacent bold letters form one span; output never contains `****`.
- All enabled rule fragments together stay at or under 700 characters, for every approach.
- `bionic` stays a boolean. Existing config files and rating logs must keep working.
- Rules apply to chat replies only; nothing here changes what is sent for commits, PRs or files.

## Review Focus

1. Upper-case and accented words (`École`, `YES`) under `vowels`/`consonants`: case and accents must not change which letters are vowels. Test in Task 2.
2. Apostrophes in `third+anchor` (`shouldn't`): the apostrophe is not a letter, does not count toward the trigger, and ends a bold run. Test in Task 2.
3. A hand-edited config with `"bionicApproach": "Vowels"` (wrong case): falls back to `third` with the invalid-value warning, never crashes the hook. Test in Task 3.
4. A rating log written by 0.4 (no new keys) mixed with new `third` ratings: they land in one report group. Test in Task 4.
5. Changing the approach mid-session: the next prompt re-sends the rules with "these replace the earlier ones". Test in Task 5.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `compliance/bionic.py` | Reference algorithm and scorer | Floor rounding; word function per approach; `approach` and `anchor_trigger` parameters |
| `scripts/pace_config.py` | Config load, validate, save | `APPROACHES`, two new keys and their validation |
| `scripts/pace.py` | `/pace` command | `bionic <approach>`, `anchor-trigger <n>`, status text, presets keep approach, report grouping |
| `scripts/inject.py` | Hook that sends the rules | One fragment per approach, `{anchorTrigger}` substitution |
| `rules/bionic-*.md` | Rule wording | `bionic.md` becomes four files |
| `compliance/score.py`, `compliance/run.py` | Harness | Pass approach through; `--approach`, `--anchor-trigger` flags |
| `commands/pace.md`, `README.md`, `CHANGELOG.md` | Docs | New commands; README re-formatted with floor rounding |

Run every test from the repo root: `python3 -m unittest discover -s tests -v`.

---

### Task 1: `third` rounds down

**Files:**
- Modify: `compliance/bionic.py` (`bold_length`)
- Modify: `rules/bionic.md`
- Test: `tests/test_bionic.py`

**Interfaces:**
- Produces: `bionic.bold_length(word: str) -> int` returning `max(1, floor(letters / 3))`.

- [ ] **Step 1: Update the tests to the floor table**

In `tests/test_bionic.py`, replace `BoldLengthTest` and the first test of `BionicWordTest`, and fix the expected text in `test_should_split_on_hyphen_and_skip_numbers_when_converting_text`:

```python
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
```

Also in `ScoreBionicTest`, the hand-written strings use the old rounding. Replace them:

```python
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
```

In `tests/test_score.py`, `BionicOkTest.test_should_fail_when_under_ninety_percent` uses `"**fo**cus plain words here"`; it still fails the threshold (now 0 of 4 correct), so leave it. `ParagraphsTest`/`LengthTest` strings are not scored for bionic; leave them. In `FirstLineTest`, `"**I**t **fai**led."` is only sentence-counted; leave it. In `ActionLineTest`, `"▶ **Y**ou: **app**rove."` is only checked for the marker; leave it.

- [ ] **Step 2: Run the bionic tests to see them fail**

Run: `python3 -m unittest tests.test_bionic -v`
Expected: FAIL in `test_should_bold_a_third_rounded_down_with_minimum_one` (e.g. `focus` gives 2, expected 1) and the other updated cases.

- [ ] **Step 3: Round down**

In `compliance/bionic.py`:

```python
def bold_length(word: str) -> int:
    letters = sum(1 for c in word if c.isalpha())
    return max(1, letters // 3)
```

Remove `import math` (no longer used).

- [ ] **Step 4: Update the rule wording**

Replace the whole of `rules/bionic.md` with (one line):

```
Bionic reading: bold the first third of every prose word, rounded down, min 1 letter: **t**he **f**ocus **re**ading **R**e-**a**dd. Numbers, headings and tables stay plain. No other bold.
```

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS (the budget test still passes: the fragment is 187 characters, total 605).

- [ ] **Step 6: Commit**

```bash
git add compliance/bionic.py rules/bionic.md tests/test_bionic.py
git commit -m "feat: third rounds the bold length down"
```

---

### Task 2: Word functions for every approach

**Files:**
- Modify: `compliance/bionic.py`
- Test: `tests/test_bionic.py`

**Interfaces:**
- Consumes: `bold_length` from Task 1.
- Produces:
  - `bionic.APPROACHES: Tuple[str, ...] = ("third", "vowels", "consonants", "third+anchor")`
  - `bionic.is_vowel(c: str) -> bool`
  - `bionic.third_word(word: str) -> str` (replaces `bionic_word`)
  - `bionic.vowels_word(word: str) -> str`
  - `bionic.consonants_word(word: str) -> str`
  - `bionic.anchor_word(word: str, anchor_trigger: int = 8) -> str`
  - `bionic.word_function(approach: str = "third", anchor_trigger: int = 8) -> Callable[[str], str]`
  - `bionic.to_bionic(text: str, approach: str = "third", anchor_trigger: int = 8) -> str`
  - `bionic.score_bionic(markdown: str, approach: str = "third", anchor_trigger: int = 8) -> Tuple[int, int]`

- [ ] **Step 1: Write the failing tests**

In `tests/test_bionic.py`, rename `bionic.bionic_word` to `bionic.third_word` in `BionicWordTest`, then add:

```python
class VowelTest(unittest.TestCase):
    def test_should_count_y_and_accented_and_upper_case_vowels(self):
        for c in "aeiouyAEIOUYéÉÿ":
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


class AnchorWordTest(unittest.TestCase):
    def test_should_bold_last_consonant_when_long_word_ends_in_vowel(self):
        self.assertEqual(bionic.anchor_word("experience"), "**exp**erien**c**e")
        self.assertEqual(bionic.anchor_word("everybody"), "**eve**rybo**d**y")

    def test_should_bold_second_to_last_consonant_when_long_word_ends_in_consonant(self):
        self.assertEqual(bionic.anchor_word("understand"), "**und**ersta**n**d")

    def test_should_bold_as_third_when_shorter_than_trigger(self):
        self.assertEqual(bionic.anchor_word("reading"), "**re**ading")
        self.assertEqual(bionic.anchor_word("reading", 7), "**re**adi**n**g")

    def test_should_merge_when_anchor_follows_prefix(self):
        # "planter": 7 letters, trigger 7, prefix "pl", ends in r -> second-to-last consonant is t.
        self.assertEqual(bionic.anchor_word("planter", 7), "**pl**an**t**er")
        # "abbey": 5 letters, trigger 2, prefix "a", ends in y (vowel) -> last consonant is the 2nd b.
        self.assertEqual(bionic.anchor_word("abbey", 2), "**a**b**b**ey")
        # "ebb": 3 letters, trigger 2, prefix "e", ends in b -> second-to-last consonant is the 1st b,
        # right after the prefix: one span.
        self.assertEqual(bionic.anchor_word("ebb", 2), "**eb**b")

    def test_should_bold_as_third_when_anchor_inside_prefix_or_missing(self):
        # "queue": prefix "q", ends in a vowel -> last consonant is q, already bold.
        self.assertEqual(bionic.anchor_word("queue", 2), "**q**ueue")
        # "aeiouaei": no consonant at all.
        self.assertEqual(bionic.anchor_word("aeiouaei", 8), "**ae**iouaei")

    def test_should_skip_apostrophe_when_counting_and_bolding(self):
        # shouldn't: 8 letters, ends in t -> second-to-last consonant is n.
        self.assertEqual(bionic.anchor_word("shouldn't"), "**sh**ould**n**'t")
        # can't: 4 letters, under the trigger.
        self.assertEqual(bionic.anchor_word("can't"), "**c**an't")


class WordFunctionTest(unittest.TestCase):
    def test_should_return_matching_function_for_every_approach(self):
        self.assertEqual(bionic.APPROACHES, ("third", "vowels", "consonants", "third+anchor"))
        self.assertEqual(bionic.word_function("vowels")("easy"), "**ea**s**y**")
        self.assertEqual(bionic.word_function("third+anchor", 7)("reading"), "**re**adi**n**g")

    def test_should_score_against_chosen_approach(self):
        text = bionic.to_bionic("The build failed because the merge dropped a plugin.", "vowels")
        self.assertEqual(bionic.score_bionic(text, "vowels"), (9, 9))
        self.assertLess(bionic.score_bionic(text)[0], 9)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_bionic -v`
Expected: FAIL/ERROR with `AttributeError: module 'bionic' has no attribute 'third_word'` (and `vowels_word`, …).

- [ ] **Step 3: Implement**

In `compliance/bionic.py`, add `import unicodedata` and `from typing import Callable, List, Tuple`, then replace `bionic_word` and `to_bionic`, and extend `score_bionic`:

```python
APPROACHES = ("third", "vowels", "consonants", "third+anchor")
VOWELS = frozenset("aeiouy")


def is_vowel(c: str) -> bool:
    return c.isalpha() and unicodedata.normalize("NFD", c)[0].lower() in VOWELS


def _render(word: str, marks: List[bool]) -> str:
    """Wrap each run of marked characters in ** so adjacent bold letters form one span."""
    out, bold = [], False
    for c, marked in zip(word, marks):
        if marked != bold:
            out.append("**")
            bold = marked
        out.append(c)
    if bold:
        out.append("**")
    return "".join(out)


def _third_marks(word: str) -> List[bool]:
    target, seen, marks = bold_length(word), 0, []
    for c in word:
        if c.isalpha() and seen < target:
            seen += 1
            marks.append(True)
        else:
            marks.append(False)
    return marks


def third_word(word: str) -> str:
    return _render(word, _third_marks(word))


def vowels_word(word: str) -> str:
    return _render(word, [is_vowel(c) for c in word])


def consonants_word(word: str) -> str:
    return _render(word, [c.isalpha() and not is_vowel(c) for c in word])


def anchor_word(word: str, anchor_trigger: int = 8) -> str:
    marks = _third_marks(word)
    letters = [i for i, c in enumerate(word) if c.isalpha()]
    if len(letters) >= anchor_trigger:
        consonants = [i for i in letters if not is_vowel(word[i])]
        nth_from_end = 1 if is_vowel(word[letters[-1]]) else 2
        if len(consonants) >= nth_from_end:
            marks[consonants[-nth_from_end]] = True
    return _render(word, marks)


def word_function(approach: str = "third", anchor_trigger: int = 8) -> Callable[[str], str]:
    if approach == "vowels":
        return vowels_word
    if approach == "consonants":
        return consonants_word
    if approach == "third+anchor":
        return lambda word: anchor_word(word, anchor_trigger)
    return third_word


def to_bionic(text: str, approach: str = "third", anchor_trigger: int = 8) -> str:
    fn = word_function(approach, anchor_trigger)
    return WORD.sub(lambda m: fn(m.group(0)), text)
```

`_third_marks` must keep today's behaviour for apostrophes: for `I'm` (2 letters, target 1) the marks are `[True, False, False]` → `**I**'m`; for `don't` (4 letters, target 1) → `**d**on't`. The loop above already does this because the apostrophe is not a letter and `seen` reaches the target on the first letter.

In `score_bionic`, add the parameters and compare against the chosen function:

```python
def score_bionic(markdown: str, approach: str = "third", anchor_trigger: int = 8) -> Tuple[int, int]:
    """Return (correct, total) prose words, judged against the chosen approach."""
    expected = word_function(approach, anchor_trigger)
    correct = total = 0
    for chunk in SEPARATORS.split(prose_only(markdown)):
        if not chunk or PATH_LIKE.search(chunk.replace("**", "")):
            continue
        actual = re.sub(r"[^\w*'’]", "", chunk).strip("'’")
        plain = actual.replace("**", "")
        if not WORD.fullmatch(plain) or CAMEL.search(plain):
            continue
        total += 1
        correct += actual == expected(plain)
    return correct, total
```

Update the module docstring to `"""Reference bionic approaches (bionic approaches spec §2), shared by the tests and the compliance harness."""`.

- [ ] **Step 4: Run the suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS. If anything outside `tests/test_bionic.py` still calls `bionic_word`, rename it to `third_word` (`grep -rn bionic_word .` must print nothing).

- [ ] **Step 5: Commit**

```bash
git add compliance/bionic.py tests/test_bionic.py
git commit -m "feat: vowels, consonants and third+anchor word functions"
```

---

### Task 3: Config keys

**Files:**
- Modify: `scripts/pace_config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `pace_config.APPROACHES: Tuple[str, ...]` — same four names as `bionic.APPROACHES`.
  - `pace_config.DEFAULTS` gains `"bionicApproach": "third"` and `"anchorTrigger": 8`.
  - `pace_config.MIN_ANCHOR_TRIGGER = 2`.
  - `validate(data)` validates both keys; `save_config` writes them (it already writes every `DEFAULTS` key).

- [ ] **Step 1: Write the failing tests**

Append to `LoadConfigTest` in `tests/test_config.py`:

```python
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
                          ({"anchorTrigger": True}, "anchorTrigger"),
                          ({"anchorTrigger": "8"}, "anchorTrigger")):
            with self.subTest(data=data):
                self.write(json.dumps(data))
                cfg, error = pc.load_config(self.path)
                self.assertEqual(cfg, pc.DEFAULTS)
                self.assertIn(key, error)

    def test_should_list_the_same_approaches_as_the_checker(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "compliance"))
        import bionic
        self.assertEqual(pc.APPROACHES, bionic.APPROACHES)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_config -v`
Expected: FAIL/ERROR (`KeyError: 'bionicApproach'`, `AttributeError: ... 'APPROACHES'`).

- [ ] **Step 3: Implement**

In `scripts/pace_config.py`:

```python
SWITCHES = ("bionic", "answerFirst", "chunks", "actionMarkers")
APPROACHES = ("third", "vowels", "consonants", "third+anchor")
MIN_ANCHOR_TRIGGER = 2
DEFAULTS = {"bionic": True, "bionicApproach": "third", "anchorTrigger": 8, "answerFirst": True,
            "chunks": True, "actionMarkers": True, "length": 200}


def valid_anchor_trigger(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= MIN_ANCHOR_TRIGGER
```

In `validate`, after the `length` block:

```python
    if "bionicApproach" in data:
        if data["bionicApproach"] in APPROACHES:
            cfg["bionicApproach"] = data["bionicApproach"]
        else:
            invalid.append("bionicApproach")
    if "anchorTrigger" in data:
        if valid_anchor_trigger(data["anchorTrigger"]):
            cfg["anchorTrigger"] = data["anchorTrigger"]
        else:
            invalid.append("anchorTrigger")
```

(`data["bionicApproach"] in APPROACHES` is safe for non-strings: `3 in ("third", …)` is `False`. An unhashable value such as a list is also just `False` for a tuple.)

- [ ] **Step 4: Run the suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: `tests.test_config` passes. `tests.test_pace` may fail where it compares whole status strings; that is fixed in Task 4. Note which tests fail and confirm they are only status-text comparisons in `tests/test_pace.py`.

- [ ] **Step 5: Commit**

```bash
git add scripts/pace_config.py tests/test_config.py
git commit -m "feat: bionicApproach and anchorTrigger config keys"
```

---

### Task 4: `/pace` commands, status and report

**Files:**
- Modify: `scripts/pace.py`
- Modify: `commands/pace.md` (`argument-hint`)
- Test: `tests/test_pace.py`

**Interfaces:**
- Consumes: `pace_config.APPROACHES`, `pace_config.valid_anchor_trigger`, the new `DEFAULTS` keys.
- Produces:
  - `pace.describe(cfg) -> str` starting with `bionic on (<approach>)`, `bionic on (third+anchor, <n>+ letters)` or `bionic off`.
  - `pace.PRESETS[name]` contains only the switches and `length`.
  - `pace.effective_setting(setting: dict) -> dict` — drops settings with no effect, used for report grouping.

- [ ] **Step 1: Update existing tests for the new status text**

In `tests/test_pace.py` replace every expected status string `"bionic on · answerFirst on"` with `"bionic on (third) · answerFirst on"`. The affected tests are `test_should_show_defaults_when_no_config`, `test_should_start_new_line_when_log_ends_mid_line`, and the first line of `test_should_group_by_setting_and_sort_by_mean_when_log_has_entries`. Strings starting `"bionic off ·"` stay as they are. `test_should_show_status_when_argument_empty` checks `startswith("human-pace: bionic on")` and still passes.

Replace `test_should_match_presets_when_on_and_off_shortcuts_used` (presets no longer hold every key):

```python
    def test_should_match_presets_when_on_and_off_shortcuts_used(self):
        pace.run(["off"])
        cfg = pc.load_config()[0]
        self.assertEqual({key: cfg[key] for key in pace.PRESETS["off"]}, pace.PRESETS["off"])
        pace.run(["ON"])
        self.assertEqual(pc.load_config()[0], pc.DEFAULTS)
```

- [ ] **Step 2: Write the failing tests**

Add a class after `PresetTest`:

```python
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
        for args in (["bionic", "bold"], ["anchor-trigger"], ["anchor-trigger", "1"],
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
```

Add to `ReportTest`:

```python
    def test_should_group_old_entries_with_new_third_entries(self):
        old = {"bionic": True, "answerFirst": True, "chunks": True, "actionMarkers": True, "length": 200}
        self.write_log([json.dumps({"ts": "t", "switches": old, "score": 2, "note": ""}), self.entry(4)])
        self.assertEqual(pace.run(["report"]),
                         "3.0 avg · 2 ratings · bionic on (third) · answerFirst on · chunks on · actionMarkers on · length 200")

    def test_should_ignore_settings_without_effect_when_grouping(self):
        self.write_log([self.entry(4, bionicApproach="vowels", anchorTrigger=5),
                        self.entry(2, bionicApproach="vowels", anchorTrigger=9),
                        self.entry(5, bionic=False, bionicApproach="consonants"),
                        self.entry(3, bionic=False)])
        self.assertEqual(pace.run(["report"]).splitlines(), [
            "4.0 avg · 2 ratings · bionic off · answerFirst on · chunks on · actionMarkers on · length 200",
            "3.0 avg · 2 ratings · bionic on (vowels) · answerFirst on · chunks on · actionMarkers on · length 200",
        ])

    def test_should_split_groups_by_trigger_when_third_anchor(self):
        self.write_log([self.entry(4, bionicApproach="third+anchor", anchorTrigger=6),
                        self.entry(2, bionicApproach="third+anchor", anchorTrigger=9)])
        self.assertEqual(len(pace.run(["report"]).splitlines()), 2)
```

- [ ] **Step 3: Run them to see them fail**

Run: `python3 -m unittest tests.test_pace -v`
Expected: FAIL (status text lacks `(third)`, `bionic vowels` prints usage, report groups split).

- [ ] **Step 4: Implement**

In `scripts/pace.py`:

Usage text — add two lines after the switch line:

```python
USAGE = """Usage:
  /pace                        show switches
  /pace <switch> on|off        switches: bionic, answerFirst, chunks, actionMarkers
  /pace bionic <approach>      approaches: third, vowels, consonants, third+anchor
  /pace anchor-trigger <n>     third+anchor bolds an extra consonant in words of n+ letters (n >= 2)
  /pace length <n>             prose word cap, 0 = no cap
  /pace preset focus|light|off focus: all on · light: no bionic, 300 words · off: all off
  /pace on | /pace off         same as preset focus | preset off
  /pace reset                  restore defaults
  /pace rate <1-5> [note]      log how the current setting feels
  /pace report                 average rating per setting
Notes cannot contain double quotes, backticks or $."""
```

Presets hold only switches and length, and are applied over the current config:

```python
PRESET_KEYS = (*pace_config.SWITCHES, "length")
PRESETS = {
    "focus": {key: pace_config.DEFAULTS[key] for key in PRESET_KEYS},
    "light": {**{key: pace_config.DEFAULTS[key] for key in PRESET_KEYS}, "bionic": False, "length": 300},
    # length 0 too: a cap alone would still send the length rule.
    "off": {**{name: False for name in pace_config.SWITCHES}, "length": 0},
}
```

Status text:

```python
def _bionic_label(cfg: dict) -> str:
    if not cfg["bionic"]:
        return "bionic off"
    if cfg["bionicApproach"] == "third+anchor":
        return f"bionic on (third+anchor, {cfg['anchorTrigger']}+ letters)"
    return f"bionic on ({cfg['bionicApproach']})"


def describe(cfg: dict) -> str:
    parts = [_bionic_label(cfg)]
    parts += [f"{name} {'on' if cfg[name] else 'off'}" for name in pace_config.SWITCHES if name != "bionic"]
    parts.append(f"length {cfg['length'] or 'no cap'}")
    return " · ".join(parts)
```

Report grouping:

```python
def effective_setting(setting: dict) -> dict:
    """Drop settings that change nothing, so they don't split report groups."""
    effective = dict(setting)
    if not effective["bionic"]:
        del effective["bionicApproach"], effective["anchorTrigger"]
    elif effective["bionicApproach"] != "third+anchor":
        del effective["anchorTrigger"]
    return effective
```

In `report()`, change the key line to `key = json.dumps(effective_setting(setting), sort_keys=True)`. Keep `settings[key] = setting` (describe hides what has no effect).

In `run()`, the existing switch branch stays first so `bionic on|off` is unchanged. Add after it:

```python
    if command == "bionic" and len(rest) == 1 and rest[0].lower() in pace_config.APPROACHES:
        cfg["bionic"], cfg["bionicApproach"] = True, rest[0].lower()
        return _save(cfg)
    if command == "anchor-trigger" and len(rest) == 1 and NUMBER.fullmatch(rest[0]) \
            and pace_config.valid_anchor_trigger(int(rest[0])):
        cfg["anchorTrigger"] = int(rest[0])
        return _save(cfg)
```

Change the preset and shortcut branches to apply over the current config:

```python
    if command == "preset" and len(rest) == 1 and rest[0].lower() in PRESETS:
        return _save({**cfg, **PRESETS[rest[0].lower()]})
    if command in SHORTCUTS and not rest:
        return _save({**cfg, **PRESETS[SHORTCUTS[command]]})
```

In `commands/pace.md`, set the `argument-hint` line to:

```
argument-hint: "[<switch> on|off | bionic <approach> | anchor-trigger <n> | length <n> | preset focus|light|off | on | off | reset | rate <1-5> [note] | report]"
```

- [ ] **Step 5: Run the suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/pace.py commands/pace.md tests/test_pace.py
git commit -m "feat: /pace bionic <approach> and /pace anchor-trigger <n>"
```

---

### Task 5: One rule fragment per approach

**Files:**
- Delete: `rules/bionic.md` (via `git mv` to `rules/bionic-third.md`)
- Create: `rules/bionic-vowels.md`, `rules/bionic-consonants.md`, `rules/bionic-third-anchor.md`
- Modify: `scripts/inject.py`
- Test: `tests/test_inject.py`

**Interfaces:**
- Consumes: `cfg["bionicApproach"]`, `cfg["anchorTrigger"]`.
- Produces: `inject.BIONIC_FRAGMENTS: Dict[str, str]` mapping each approach to its file name; `build_rules` sends only the active one and replaces `{anchorTrigger}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_inject.py`, replace `test_should_stay_within_budget_when_all_defaults` and add to `BuildRulesTest`:

```python
    def test_should_stay_within_budget_for_every_approach(self):
        for approach in pc.APPROACHES:
            for trigger in (8, 99):
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
```

Add to `OncePerSessionTest`:

```python
    def test_should_resend_rules_once_when_approach_changes_mid_session(self):
        self.send("SessionStart")
        pc.save_config({**pc.defaults(), "bionicApproach": "vowels"}, self.config)
        update = self.send("UserPromptSubmit")
        self.assertTrue(update.startswith("human-pace rules changed; these replace the earlier ones."))
        self.assertIn("every vowel", update)
        self.assertIsNone(self.send("UserPromptSubmit"))
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_inject -v`
Expected: FAIL/ERROR (`AttributeError: module 'inject' has no attribute 'BIONIC_FRAGMENTS'`, missing "every vowel").

- [ ] **Step 3: Create the fragments**

```bash
git mv rules/bionic.md rules/bionic-third.md
```

`rules/bionic-third.md` keeps the Task 1 text. Create the other three, each a single line:

`rules/bionic-vowels.md`:
```
Bionic reading: bold every vowel (a e i o u y) of every prose word, adjacent ones as one span: **u**nd**e**rst**a**nd **ea**s**y**. Numbers, headings and tables stay plain. No other bold.
```

`rules/bionic-consonants.md`:
```
Bionic reading: bold every consonant (not a e i o u y) of every prose word, adjacent ones as one span: u**nd**e**rst**a**nd** ea**s**y. Numbers, headings and tables stay plain. No other bold.
```

`rules/bionic-third-anchor.md`:
```
Bionic reading: bold the first third of every prose word, rounded down, min 1. In words of {anchorTrigger}+ letters also bold the last consonant if it ends in a vowel (y counts), else the one before: **und**ersta**n**d **exp**erien**c**e. Numbers, headings, tables plain. No other bold.
```

Measured while planning: with the other default fragments the totals are 605, 605, 609 and 690 characters (691 with a two-digit trigger).

- [ ] **Step 4: Pick the fragment in `inject.py`**

```python
# What to say first, then shape, then how the words look. "bionic" picks its file by approach.
FRAGMENTS = (
    ("answerFirst", "answer-first.md"),
    ("chunks", "chunks.md"),
    ("actionMarkers", "action-markers.md"),
    ("length", "length.md"),
    ("bionic", None),
)
BIONIC_FRAGMENTS = {
    "third": "bionic-third.md",
    "vowels": "bionic-vowels.md",
    "consonants": "bionic-consonants.md",
    "third+anchor": "bionic-third-anchor.md",
}
```

In `build_rules`, inside the loop:

```python
    for key, name in FRAGMENTS:
        if not cfg.get(key):
            continue
        if key == "bionic":
            name = BIONIC_FRAGMENTS.get(cfg.get("bionicApproach"), BIONIC_FRAGMENTS["third"])
        text = read_fragment(rules_dir, name)
        if text:
            text = text.replace("{length}", str(cfg["length"]))
            parts.append(text.replace("{anchorTrigger}", str(cfg.get("anchorTrigger", 8))))
```

- [ ] **Step 5: Run the suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS. `test_should_skip_fragment_when_file_missing` builds rules from a temp dir with only `chunks.md`; it still passes because a missing bionic file is skipped.

- [ ] **Step 6: Commit**

```bash
git add rules scripts/inject.py tests/test_inject.py
git commit -m "feat: one bionic rule fragment per approach"
```

---

### Task 6: Compliance harness per approach

**Files:**
- Modify: `compliance/score.py`, `compliance/run.py`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `bionic.score_bionic(markdown, approach, anchor_trigger)` from Task 2.
- Produces: `score.bionic_ok(reply, approach="third", anchor_trigger=8) -> bool`; `run.harness_env(tmp: str, cfg: Optional[dict] = None) -> Dict[str, str]`; `run.parse_args(argv: List[str]) -> dict` returning the config to test.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_score.py`:

```python
class ApproachScoringTest(unittest.TestCase):
    def test_should_score_reply_against_configured_approach(self):
        reply = to_bionic("The build failed because the merge dropped a plugin.", "vowels")
        cfg = {**pc.defaults(), "bionicApproach": "vowels"}
        self.assertTrue(score.score_reply(reply, cfg)["bionic >= 90%"])
        self.assertFalse(score.score_reply(reply, pc.defaults())["bionic >= 90%"])


class HarnessArgsTest(unittest.TestCase):
    def test_should_return_defaults_when_no_flags(self):
        self.assertEqual(run.parse_args([]), pc.defaults())

    def test_should_set_approach_and_trigger_when_flags_given(self):
        cfg = run.parse_args(["--approach", "third+anchor", "--anchor-trigger", "6"])
        self.assertEqual((cfg["bionicApproach"], cfg["anchorTrigger"]), ("third+anchor", 6))

    def test_should_exit_when_approach_unknown(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            run.parse_args(["--approach", "bold"])

    def test_should_write_config_for_hook_when_cfg_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {**pc.defaults(), "bionicApproach": "consonants"}
            env = run.harness_env(tmp, cfg)
            self.assertEqual(pc.load_config(Path(env["HUMAN_PACE_CONFIG"])), (cfg, None))
```

Add `import contextlib`, `import io` and `import tempfile` at the top of `tests/test_score.py`. The existing `HarnessEnvTest` (no `cfg` → `absent.json`) stays unchanged.

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_score -v`
Expected: FAIL/ERROR (`run` has no `parse_args`; vowels reply fails `bionic >= 90%` under the configured approach).

- [ ] **Step 3: Implement `score.py`**

```python
def bionic_ok(reply: str, approach: str = "third", anchor_trigger: int = 8) -> bool:
    correct, total = score_bionic(reply, approach, anchor_trigger)
    return total == 0 or correct / total >= BIONIC_THRESHOLD
```

In `score_reply`:

```python
    if cfg.get("bionic"):
        results["bionic >= 90%"] = bionic_ok(reply, cfg.get("bionicApproach", "third"), cfg.get("anchorTrigger", 8))
        results["no bold in code"] = not bold_in_code(reply)
```

- [ ] **Step 4: Implement `run.py`**

Add `import argparse` and `from typing import Optional`, then:

```python
def parse_args(argv: List[str]) -> dict:
    parser = argparse.ArgumentParser(description="Score real replies against the human-pace rules.")
    parser.add_argument("--approach", choices=pace_config.APPROACHES, default="third")
    parser.add_argument("--anchor-trigger", type=int, default=pace_config.DEFAULTS["anchorTrigger"])
    args = parser.parse_args(argv)
    if not pace_config.valid_anchor_trigger(args.anchor_trigger):
        parser.error(f"--anchor-trigger must be at least {pace_config.MIN_ANCHOR_TRIGGER}")
    return {**pace_config.defaults(), "bionicApproach": args.approach, "anchorTrigger": args.anchor_trigger}


def harness_env(tmp: str, cfg: Optional[dict] = None) -> Dict[str, str]:
    env = dict(os.environ)
    env["HUMAN_PACE"] = "1"                                    # claude -p is headless: force the plugin on
    if cfg is None:
        env["HUMAN_PACE_CONFIG"] = str(Path(tmp) / "absent.json")  # defaults, not your own switches
    else:
        path = Path(tmp) / "config.json"
        pace_config.save_config(cfg, path)
        env["HUMAN_PACE_CONFIG"] = str(path)
    return env
```

`save_config` resolves the path; on macOS a temp dir under `/var` resolves to `/private/var`, so the test compares by loading the file, not by path string.

In `main`, take `argv` and use the parsed config:

```python
def main(argv: Optional[List[str]] = None) -> int:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    results: Dict[str, List[bool]] = {}
    prompts = load_prompts()
    with tempfile.TemporaryDirectory() as tmp:
        env = harness_env(tmp, cfg)
        ...  # loop unchanged
```

- [ ] **Step 5: Run the suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS. Also run `python3 compliance/run.py --help` and confirm both flags are listed (this does not call `claude`).

- [ ] **Step 6: Commit**

```bash
git add compliance/score.py compliance/run.py tests/test_score.py
git commit -m "feat: compliance harness scores a chosen bionic approach"
```

---

### Task 7: README, changelog and roadmap

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `docs/ROADMAP.md`

**Interfaces:**
- Consumes: `bionic.to_bionic` (floor rounding) from Tasks 1–2.

- [ ] **Step 1: Add the new commands to the README table**

In the `## Use` table, after the `/pace <switch> on\|off` row, add:

```
| `/pace bionic <approach>` | `third`, `vowels`, `consonants` or `third+anchor`; turns bionic on |
| `/pace anchor-trigger <n>` | Word length that gets an anchor consonant in `third+anchor` (default 8) |
```

Under the "Changes apply from your next prompt" paragraph, add this sentence in plain words (it is re-formatted in Step 2): `Approaches: third bolds the first third of each word; vowels and consonants bold those letters; third+anchor adds one consonant near the end of long words.`

- [ ] **Step 2: Re-format the README prose with floor rounding**

Save as `$CLAUDE_JOB_DIR/tmp/rebionic.py` (or any scratch path outside the repo) and run it from the repo root with `python3 <path> README.md`:

```python
"""Strip ** from README prose and re-apply the third approach, leaving code, headings and tables alone."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "compliance")
from bionic import to_bionic  # noqa: E402

PROTECTED = re.compile(r"(`[^`]*`|https?://\S+)")


def convert(line: str) -> str:
    parts = PROTECTED.split(line.replace("**", ""))
    return "".join(part if i % 2 else to_bionic(part) for i, part in enumerate(parts))


path = Path(sys.argv[1])
out, in_fence = [], False
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith("```"):
        in_fence = not in_fence
    keep = in_fence or line.startswith(("#", "|", "```")) or not line.strip()
    out.append(line if keep else convert(line))
path.write_text("\n".join(out) + "\n", encoding="utf-8")
```

Then check by eye with `git diff README.md`: only bold boundaries change in prose lines (e.g. `**fo**llow` → `**f**ollow`); code spans, table rows, headings and the License line's `LICENSE` code span are untouched; `MIT` becomes `**M**IT` like other words. Verify with:

Run: `python3 -c "import sys; sys.path.insert(0,'compliance'); import bionic; t=open('README.md').read(); print(bionic.score_bionic(t))"`
Expected: correct equals total.

- [ ] **Step 3: Changelog and roadmap**

Add at the top of `CHANGELOG.md`, under `# Changelog`:

```markdown
## Unreleased

- Bionic approaches: `/pace bionic third|vowels|consonants|third+anchor` and `/pace anchor-trigger <n>`.
- `third` rounds the bold length down: a 7-letter word gets 2 bold letters, not 3.
- `/pace report` compares approaches; ratings from earlier versions count as `third`.
- `compliance/run.py --approach <name> [--anchor-trigger <n>]` scores one approach.
```

In `docs/ROADMAP.md`, append ` (done; see the bionic approaches spec)` to the line starting `- Bionic approaches, chosen with`.

- [ ] **Step 4: Run the suite and validation**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

Run: `claude plugin validate . && claude plugin validate .claude-plugin/plugin.json`
Expected: `✔ Validation passed` twice.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md docs/ROADMAP.md
git commit -m "docs: bionic approaches in README and changelog; README re-formatted with floor rounding"
```
