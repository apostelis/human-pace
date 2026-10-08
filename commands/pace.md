---
description: Show or change human-pace switches, rate the current setting, or inspect local usage analytics
argument-hint: "[<switch> on|off | bionic third|vowels|consonants|third+anchor | experimental gradient off|color|weight|both | anchor-trigger <n> | length <n> | drift-guard <n> | preset focus|light|off | on | off | reset | rate <1-5> [note] | report [usage|compare [days]] | analytics [on|off|retention <days>|export|clear]]"
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pace.py" "$ARGUMENTS"`

Reply with the output above exactly as written. Add nothing and apply no formatting.
