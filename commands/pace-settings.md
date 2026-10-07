---
description: Open Human Pace settings, preferring the embedded MCP panel
---
First check whether a connected MCP tool named `open_human_pace_settings` is available (its full name may include the server prefix). If it is, call that tool to render the embedded settings panel. Do not run the Python browser launcher, fetch a localhost URL, or replace the widget with a text reply. The widget handles preview and Save through the MCP connection.

If the MCP tool is unavailable and this is Cowork or an isolated shell, explain that the embedded Human Pace connector is not available in this conversation. Ask the user to enable `human-pace-embedded-test` for the conversation and retry. Do not start the browser server in the sandbox or give a sandbox file path as a Mac terminal command.

Only when the MCP tool is unavailable and the shell is confirmed to run on the user's Mac, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/preview.py" --settings --open` with Bash for the browser fallback. Give the returned URL if the browser does not open. Do not apply human-pace formatting to this response.
