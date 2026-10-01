# Changelog

## 0.5.1 — 2026-10-01

- Roadmap and spec: the planned `/pace experiment` command is renamed `/pace experimental`.

## 0.5.0 — 2026-10-01

- Bionic approaches: `/pace bionic third|vowels|consonants|third+anchor` and `/pace anchor-trigger <n>`.
- `third` rounds up for words of up to 5 letters and down for longer ones: a 7-letter word gets 2
  bold letters, not 3.
- `/pace report` compares approaches; earlier ratings with bionic on are shown apart as
  `third, 0.4 rounding`.
- `compliance/run.py --approach <name> [--anchor-trigger <n>]` scores one approach.

## 0.4.0 — 2026-10-01

- `/pace preset focus|light|off`, with `/pace on` and `/pace off` as shortcuts.
- CI runs the unit tests on Python 3.9 and 3.12 and validates the plugin manifests.
- MIT license; homepage, repository, license and keywords in the plugin manifest.
- README states the context cost.

## 0.3.0 — 2026-09-30

- README prose in bionic format.
- Fixes from review: non-UTF-8 config and log bytes, truncated log lines.

## 0.2.0 — 2026-09-30

- Rules are sent once per session (and after `/compact` or `/resume`) instead of above every reply.

## 0.1.0 — 2026-09-30

- Switches `bionic`, `answerFirst`, `chunks`, `actionMarkers` and a `length` cap, injected by hook.
- `/pace` to show and change switches, `rate` and `report` for the experiment log.
- Compliance harness scoring real replies against the rules.
