# Bionic approaches — Design Spec

**Date:** 2026-10-01
**Status:** Draft, awaiting review
**Roadmap:** 0.5 Experiment, first of three items (drift guard and `/pace experiment` follow).

## 1. Purpose

Today `bionic` has one way of bolding: the first third of each word. Whether that helps is the open
question of the whole plugin, so 0.5 adds alternative approaches the user can switch between and
compare with `/pace rate` and `/pace report`.

**Decided with the user**

- Four approaches: `third` (today), `vowels`, `consonants`, `third+anchor`.
- `vowels` bolds every vowel in every word; `consonants` bolds every consonant.
- `y` counts as a vowel.
- `third+anchor` adds one bold consonant near the end of long words. A word is long at 8 or more
  letters by default, configurable.
- The anchor is the last consonant when the word ends in a vowel, and the second-to-last consonant
  when it ends in a consonant.
- The user-facing term is "approach", not "strategy"; the long-word threshold is the "anchor trigger" (`anchorTrigger`, `/pace anchor-trigger`).
- `third` rounds down from now on: `max(1, floor(letters / 3))`, so a 7-letter word gets 2 bold
  letters, not 3. This changes today's behaviour (design spec §3 rounded up).

**Success criteria**

- Existing config files and rating logs keep working unchanged.
- Each approach has rule wording within the 700-character budget and a checker the compliance
  harness can score.
- `/pace report` compares approaches without splitting groups on settings that have no effect.

## 2. Approaches

Shared definitions from the design spec §3 still hold: what a prose word is, the exclusions (code,
paths, URLs, identifiers, headings, tables), hyphens splitting words, apostrophes inside words. Only
the bold length changes, from rounding up to rounding down:

| Letters | 1–5 | 6–8 | 9–11 | 12–14 |
|---|---|---|---|---|
| Bold (was) | 1 (1–2) | 2 (2–3) | 3 (3–4) | 4 (4–5) |

- **Vowel:** a letter whose base letter, after Unicode NFD decomposition, is one of `a e i o u y`,
  in either case (`é` is a vowel). **Consonant:** any other letter. Apostrophes are neither.
- **Runs:** adjacent bold letters form one bold span, so markdown never contains `****`.
  `easy` → `**ea**s**y**`, not `**e****a**sy`. An apostrophe ends a run.

| Approach | Rule | Examples |
|---|---|---|
| `third` | First `max(1, floor(letters / 3))` letters. | `**und**erstand`, `**re**ading`, `**t**he` |
| `vowels` | Every vowel. | `**u**nd**e**rst**a**nd`, `**ea**s**y**`, `rh**y**thm` |
| `consonants` | Every consonant. | `u**nd**e**rst**a**nd**`, `ea**s**y` |
| `third+anchor` | `third`, plus the anchor consonant in words of at least `anchorTrigger` letters. | `**und**ersta**n**d`, `**exp**erien**c**e` |

**Anchor rules (`third+anchor`)**

- Word ends in a vowel (including `y`): the anchor is its last consonant. `experience` → `c`,
  `everybody` → `d`.
- Word ends in a consonant: the anchor is the second-to-last consonant. `understand` → the second `n`.
- If the anchor is inside the bold prefix, or the word has no such consonant, the word is bolded as
  `third`. If the anchor directly follows the prefix, the two merge into one span.
- Shorter words are bolded as `third`.

## 3. Config

Two new keys, beside the existing ones:

```json
{ "bionic": true, "bionicApproach": "third", "anchorTrigger": 8, "answerFirst": true, "chunks": true,
  "actionMarkers": true, "length": 200 }
```

- `bionic` stays a boolean on/off switch. Turning `bionic` into a text value was rejected: it would
  break existing config files and every logged rating.
- `bionicApproach`: one of the four names. Missing → `third`. Anything else → `third`, reported as
  an invalid value like the other keys.
- `anchorTrigger`: integer, at least 2. Missing → 8. Invalid → 8, reported.
- Presets (`focus`, `light`, `off`, and the `on`/`off` shortcuts) change only the switches and
  `length`; they keep the user's approach and anchor trigger. `/pace reset` restores everything,
  including `third` and 8.

## 4. `/pace` command

| Invocation | Effect |
|---|---|
| `/pace bionic on\|off` | Unchanged. |
| `/pace bionic <approach>` | Sets the approach and turns `bionic` on. Case-insensitive. |
| `/pace anchor-trigger <n>` | Sets `anchorTrigger`, `n` ≥ 2. Does not change the approach. |

Status output shows the approach next to the switch, and the anchor trigger only where it applies:
`bionic on (third)`, `bionic on (vowels)`, `bionic on (third+anchor, 8+ letters)`, `bionic off`.
The usage text and the `argument-hint` in `commands/pace.md` list the approaches and `anchor-trigger`.

## 5. Rules and injection

- `rules/bionic.md` becomes four files: `bionic-third.md`, `bionic-vowels.md`,
  `bionic-consonants.md`, `bionic-third-anchor.md`. Only the active approach's file is sent.
- `bionic-third-anchor.md` contains `{anchorTrigger}`, replaced with `anchorTrigger`, as `{length}` is today.
- Each fragment shows one or two worked examples, as the current rule does. `bionic-third.md` says
  "rounded down" and uses floor examples (`**t**he **fo**cus` becomes `**t**he **f**ocus`).
- The README prose is bionic-formatted with the old rounding; regenerate it with `to_bionic` so it
  matches `third`.
- The budget test runs once per approach: every enabled fragment together stays at or under 700
  characters.
- Changing the approach or anchor trigger changes the rules, so the existing once-per-session logic
  re-sends them on the next prompt with "these replace the earlier ones". No new mechanism.

## 6. Checker and compliance

- `compliance/bionic.py` gets one word function per approach (`third_word`, `vowels_word`,
  `consonants_word`, `anchor_word(word, anchor_trigger)`) and a lookup from approach name to function.
  `score_bionic` takes the approach and anchor trigger; its defaults keep today's behaviour.
- `compliance/score.py` passes `cfg["bionicApproach"]` and `cfg["anchorTrigger"]` through. The rule
  label stays `bionic >= 90%`.
- `compliance/run.py` gains `--approach <name>` (and `--anchor-trigger <n>`), written into the harness's
  temporary config, so each approach can be scored separately. No flag means defaults, as today.

## 7. Report

- Ratings already store the whole config, so new entries carry the approach.
- Old entries have no `bionicApproach` or `anchorTrigger`; validation fills in `third` and 8, which
  is what they used.
- Before grouping, settings that have no effect are dropped from the key: the approach and anchor
  trigger when `bionic` is off, and the anchor trigger unless the approach is `third+anchor`. So
  `vowels` ratings taken with different anchor triggers land in one group.

## 8. Error handling

| Failure | Behaviour |
|---|---|
| Unknown approach in config | `third`, plus the existing invalid-value warning. |
| Invalid `anchorTrigger` in config | 8, plus the warning. |
| `/pace bionic <unknown>` or `/pace anchor-trigger <bad>` | Usage text, nothing changed. |
| Approach fragment file missing | Skip it, as for any missing fragment. |

## 9. Testing

- Config: defaults, valid and invalid values for both keys, old configs without them.
- `/pace`: each approach, case-insensitivity, `anchor-trigger` bounds, presets keeping the approach, reset
  restoring it, status text, usage and command hint listing every approach.
- Inject: the right fragment per approach, `{anchorTrigger}` substituted, budget per approach, rules
  re-sent after an approach change.
- Existing bionic tests that expect rounding up are updated to the floor table in §2.
- Checker: hand-written examples per approach, including `y`, accented vowels, apostrophes,
  hyphens, adjacent-run merging, anchor inside or next to the prefix, words shorter than
  `anchorTrigger`.
- Report: old entries counted as `third`; anchor trigger ignored outside `third+anchor`.

## 10. Out of scope

- Drift guard and `/pace experiment` (separate specs).
- Approaches other than these four.
- Changing what counts as a prose word.
