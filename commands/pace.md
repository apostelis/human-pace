---
description: Show or change human-pace switches, rate the current setting, or see the report
argument-hint: "[<switch> on|off | length <n> | reset | rate <1-5> [note] | report]"
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pace.py" "$ARGUMENTS"`

Reply with the output above exactly as written. Add nothing and apply no formatting.
