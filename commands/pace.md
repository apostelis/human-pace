---
description: Show or change human-pace switches, rate the current setting, or see the report
argument-hint: "[<switch> on|off | bionic third|vowels|consonants|third+anchor | anchor-trigger <n> | length <n> | preset focus|light|off | on | off | reset | rate <1-5> [note] | report]"
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pace.py" "$ARGUMENTS"`

Reply with the output above exactly as written. Add nothing and apply no formatting.
