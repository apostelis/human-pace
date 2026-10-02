---
name: human-pace
description: Apply human-pace formatting when the user requests bionic reading, human-pace, or pace settings for chat replies.
---

Apply human-pace to replies in the current conversation until the user changes or
disables it. Read [settings.md](references/settings.md) for the formatting rules.
Start with preset focus: bionic on using third, anchor trigger 8, answerFirst on,
chunks on, actionMarkers on, prose length 200. Follow explicit user preferences.

Treat `/pace ...` or an equivalent natural-language request as a settings request
when routed to this skill. It is conversational syntax, not a registered slash
command. Support:

- No arguments: show the current settings.
- `bionic`, `answerFirst`, `chunks`, `actionMarkers` followed by `on` or `off`.
- `bionic third|vowels|consonants|third+anchor`: select an approach and enable it.
- `experimental gradient off|color|weight|both`: opt-in HTML/CSS reply styling;
  default off. Non-off enables bionic; off removes only the gradient. Read the
  experimental gradients section in settings.md. Keep ordinary Markdown bionic
  formatting on unsupported surfaces. For explicitly requested HTML previews,
  the bundled `scripts/render_gradient.py --mode color|weight|both` reads plain
  prose from stdin and emits an escaped HTML fragment using the default third
  prefix. It is not a Markdown parser; pass only prose selected for the preview.
- `anchor-trigger <n>`: integer 2–50; replace `{anchorTrigger}` in the rule.
- `length <n>`: nonnegative integer; replace `{length}`, or omit the cap at 0.
- `preset focus|light|off`, `on`, `off`, `reset`.

Presets change the four switches and length while retaining approach, anchor
trigger, and experimental gradient. Focus turns all switches on with length 200. Light turns bionic off,
the other switches on, and length 300. Off disables all four and sets length 0.
On means focus; reset restores every default including third, trigger 8, and gradient off.
Reject invalid settings without changing the current ones.

Confirm settings changes with a brief plain-text status. Apply updated rules to
subsequent replies. Include the common scope rule whenever any formatting switch
or length cap is enabled. Never format files, code, tool inputs, commits, PRs or
text written for other people. When off, omit every human-pace rule.

Settings are held in this conversation; do not write local configuration or claim
they persist across chats. This skill has no session hooks or prompt counter.
`drift-guard`, `rate`, and `report` belong to the Claude integration: explain that
automatic reminders and persistent rating logs are unavailable here. Do not
fabricate ratings or pretend to run the Claude hook. If settings are lost after
compaction, ask the user to restate them rather than claim to remember them.
