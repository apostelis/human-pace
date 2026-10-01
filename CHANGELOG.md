# Changelog

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
