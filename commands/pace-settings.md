---
description: Open Human Pace settings with live preview and Save
allowed-tools: Bash(python3:*)
---
Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/preview.py" --settings --open` with Bash. This starts a temporary local settings page and opens it in the user's browser. Give the returned URL if the browser does not open. The user can change options and select Save; command-mode settings apply from the next ordinary prompt, while native-mode settings may require a plugin reload or session restart. Do not apply human-pace formatting to this response.
