# human-pace

A Claude Code plugin that makes replies easier to follow: bionic reading, answer first, short
chunks, marked action items and a length cap. Every part can be switched on or off.

## Install

```
/plugin marketplace add apostelis/human-pace
/plugin install human-pace@human-pace
```

The rules are sent once when a session starts (and again after `/compact` or `/resume`), not above
every reply.

Requires `python3` (3.9+). Without it the plugin does nothing, and your prompts are never blocked.

## Use

| Command | Effect |
|---|---|
| `/pace` | Show switches |
| `/pace <switch> on\|off` | `bionic`, `answerFirst`, `chunks`, `actionMarkers` |
| `/pace length <n>` | Prose word cap, `0` = no cap |
| `/pace reset` | Restore defaults |
| `/pace rate <1-5> [note]` | Log how the current setting feels |
| `/pace report` | Average rating per setting |

Changes apply from your next prompt; the updated rules are sent once. Settings live in `~/.claude/human-pace.json`, and ratings in
`~/.claude/human-pace-log.jsonl`.

Headless runs (`claude -p`, the Agent SDK) are skipped, so scripts and CI get plain output.
Set `HUMAN_PACE=1` to force the rules on there, or `HUMAN_PACE=0` to turn them off everywhere.

## Develop

```
python3 -m unittest discover -s tests -v     # unit tests
python3 compliance/run.py                    # score real replies (calls claude -p, costs a few cents)
```

Rule wording lives in `rules/*.md`. Keep all fragments together under 700 characters.
