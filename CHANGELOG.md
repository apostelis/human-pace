# Changelog

## 0.10.0 — 2026-10-07

- Prefer the connected embedded MCP settings tool when opening settings or preview.
- Avoid launching unreachable browser servers in Cowork; retain the browser fallback for a confirmed local Mac shell. The embedded connector must be installed separately.

## 0.9.0 — 2026-10-07

- Add twelve sample passages across four text types, with a New passage button and no repeats within a category until exhausted.

- Add a browser settings page with live preview and Save, opened through `/pace-settings` or `/pace-preview`, including a reminder-interval control.
- Save to existing command settings or Claude’s native configuration API, with validation and visible errors.

## 0.8.0 — 2026-10-07

- Add native Claude Code plugin configuration for all formatting settings, with an explicit source selector preserving existing command settings. Requires Claude Code 2.1.271+.
- Add `/pace-preview` to open a local interactive browser preview; preview controls do not modify saved settings.

## 0.7.3 — 2026-10-06

- Use explicit `ceil(letters / 3)` for the `third` calculation and the shared prefix in `third+anchor`.
- State the ceiling formula in shared formatting rules and generated custom instructions.

## 0.7.2 — 2026-10-02

- Fix `third` to round the prefix length up for every word length, including the shared prefix in `third+anchor`.
- Update formatting rules and generated custom instructions to match.

## 0.7.1 — 2026-10-02

- Add opt-in experimental bionic gradients (`color`, `weight`, `both`) for HTML/CSS reply surfaces, with Markdown fallback.

## 0.7.0 — 2026-10-02

- Add a portable plugin and self-contained human-pace skill for ChatGPT Work and Codex.
- Add copyable custom instructions for ChatGPT, generated from the shared formatting rules.
- Document installation and chat-local switches; persistent ratings and automatic reminders remain Claude-only.
- Check generated OpenAI resources for drift in CI.

## 0.6.0 — 2026-10-01

- Drift guard: the rules are resent every 10 prompts so they don't fade in long sessions;
  `/pace drift-guard <n>` changes the interval, `0` turns it off. Ratings ignore it.

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
