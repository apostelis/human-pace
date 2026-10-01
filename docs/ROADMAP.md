# human-pace roadmap

Agreed 2026-10-01. Goals, in order: polish for picky developers, then measure what helps, then team
features. Current release: 0.3.0.

## 0.4 Polish (shipped in 0.4.0)

Make it something a fussy developer installs and keeps.

- `claude plugin validate .` already passes; run it in CI so it stays that way.
- Add a `CHANGELOG.md` and fill in marketplace metadata (description, homepage, keywords).
- Quote the token cost from `claude plugin details` in the README, so the overhead is visible.
- Presets: `/pace preset focus|light|off`, so nobody has to learn the individual switches.
- A silent per-person opt-out: one command, no reminders afterwards.

## 0.5 Experiment

Find out whether the formatting helps, instead of assuming it does.

- Drift guard: re-send the rules every N turns, because rules sent once fade in long sessions.
- `/pace experiment` alternates settings week by week; `/pace report` names the better setting.
- Bionic approaches, chosen with `/pace bionic <approach>` and compared through `/pace report`:
  - `third` (today): bold the first third of each word.
  - `vowels`: bold only the vowels.
  - `consonants`: bold only the consonants.
  - `third+anchor`: the first third, plus one consonant near the end of long words. A word is
    long at 8 or more letters by default, configurable with `/pace anchor-trigger <n>` and stored in the
    config. The anchor is the last consonant when the word ends in a vowel (`experience` → the
    `c`), and the second-to-last consonant when it ends in a consonant (`understand` → the second
    `n`).

  Each approach needs rule wording that fits the 700-character budget and a matching checker in
  `compliance/bionic.py`. `vowels` and `consonants` bold scattered single letters, which costs more
  output tokens and may be harder for the model to follow; the compliance harness will show this.

## 0.6 Team

Roll it out without forcing it on anyone.

- Repo defaults in `.claude/human-pace.json`; each developer's own settings win. The design spec
  (§8) lists per-project config as out of scope, so this reopens that decision.
- CI runs the compliance harness when `rules/*.md` change.
- Spike: can `claude plugin eval` replace the homegrown harness in `compliance/`?
