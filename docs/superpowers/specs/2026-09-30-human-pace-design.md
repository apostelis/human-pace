# human-pace — Design Spec

**Date:** 2026-09-30
**Status:** Draft, awaiting review

## 1. Purpose

A Claude Code plugin that makes Claude's chat replies easier to follow for a reader who drifts
(ADHD, focus), and slows the interaction to a human pace. The author and their team currently act
as a "meat proxy" for Claude's output — reading and relaying more than they can absorb.

**Success criteria**

- On every prompt, with no action from the user (always on, dependable).
- Every behaviour can be switched independently, so the user can test what actually helps.
- Measured, not assumed: model compliance is scored, and the user's own experience is logged.
- Never leaks formatting into artefacts other people read (commits, PRs, files, Slack/Jira).

**Context and constraints**

- Surfaces: Claude Code CLI in a terminal and in IntelliJ. The JetBrains integration renders replies
  in the IDE's built-in terminal, so both are one renderer; bold depends on the terminal font.
- Claude Code has no hook that rewrites response text. The model produces all formatting itself,
  from injected rules. Compliance is therefore probabilistic and must be measured (§6.2).
- Evidence that bionic reading improves speed or comprehension is weak. This is an experiment,
  which is why every part is toggleable and the user logs ratings (§6.3).

## 2. Behaviours (switches)

| Switch | Default | Rule injected into the model's context |
|---|---|---|
| `bionic` | on | Bold the first third of each prose word (algorithm §3). No other bold while on. |
| `answerFirst` | on | First line is the answer or outcome in one sentence; detail follows. |
| `chunks` | on | Paragraphs of at most 3 sentences; steps or options become lists. |
| `actionMarkers` | on | Anything that needs the user goes last, on its own line, prefixed `▶ You:`. |
| `length` | 200 | Soft cap in prose words, code excluded. If more is needed, give the essentials and offer the rest. `0` disables the cap. |

**Rules common to all switches**

- They apply to chat replies only. Never to commit messages, PR bodies, file contents, tool inputs,
  or text written for Slack, Jira or any other person.
- They never apply inside fenced code blocks, inline code, file paths, URLs, identifiers, or tables.

## 3. Bionic reference algorithm

One definition shared by the rule file (human-readable) and the compliance checker (code).

- **Prose word:** a maximal run of letters, allowing internal apostrophes (`don't` is one word of
  length 5, apostrophe not counted). A hyphen separates words: `Re-add` is `Re` + `add`.
- **Not words:** numbers, and anything inside the exclusions in §2.
- **Bold length:** `max(1, ceil(letters / 3))`. Examples: `a`→**a**, `the`→**t**he,
  `focus`→**fo**cus, `reading`→**rea**ding, `understand`→**unde**rstand.
- **Where it applies:** paragraphs, list items, block quotes, and the text of the `▶ You:` line.
- **Where it does not:** headings (left plain), table cells, and every exclusion in §2.
- **No other bold** while `bionic` is on; emphasis moves to `▶` markers and word order.

## 4. Architecture

```
human-pace/
├── .claude-plugin/
│   ├── plugin.json          manifest (name: human-pace)
│   └── marketplace.json     lets teammates install from this repo
├── hooks/hooks.json         UserPromptSubmit → scripts/inject.py
├── scripts/
│   ├── config.py            load/save/defaults for ~/.claude/human-pace.json
│   ├── inject.py            hook: assemble enabled rules, print hook JSON
│   └── pace.py              /pace subcommands, rating log, report
├── rules/                   one short markdown fragment per switch
│   ├── bionic.md  answer-first.md  chunks.md  action-markers.md  length.md
├── commands/pace.md         !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pace.py" $ARGUMENTS`
├── evals/                   compliance harness (§6.2)
└── tests/                   unittest suite (§6.1)
```

**State lives outside the plugin.** `${CLAUDE_PLUGIN_ROOT}` is replaced on every plugin update, so
config is `~/.claude/human-pace.json` and the rating log is `~/.claude/human-pace-log.jsonl`.

**Runtime:** Python 3.9+ standard library only (macOS system `python3` is 3.9). No third-party
packages.

### 4.1 Data flow per prompt

1. User submits a prompt; `UserPromptSubmit` runs `inject.py`, which receives the hook JSON on stdin.
2. `inject.py` exits with no output (no rules) when any of:
   - env var `HUMAN_PACE=0` is set (kill switch for scripts, CI and other automation);
   - the prompt starts with `/pace` (its output stays plain);
   - `python3` is unavailable (the hook command fails open).
3. Otherwise it loads config (defaults if missing), concatenates the rule fragments for enabled
   switches in a fixed order, substitutes `{length}`, and prints:
   `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "<rules>"}}`
4. The model receives the rules alongside the prompt every turn, so they survive `/compact` and
   `/resume` without a SessionStart hook.

**Budget:** all fragments together stay at or under ~150 tokens. They appear in the transcript as a
system reminder on every turn.

### 4.2 Config file

```json
{ "bionic": true, "answerFirst": true, "chunks": true, "actionMarkers": true, "length": 200 }
```

Missing file or missing keys take defaults. Unknown keys are ignored. Malformed JSON: use defaults
and append one line to the rules asking the model to tell the user the config is broken.

### 4.3 `/pace` command

`commands/pace.md` runs `pace.py` through the command file's `!` execution, verified on
2026-09-30 to run deterministically with `$ARGUMENTS` and `${CLAUDE_PLUGIN_ROOT}` expanded. The
model only relays the script's output verbatim.

| Invocation | Effect |
|---|---|
| `/pace` | Show current switches. |
| `/pace <switch> on\|off` | Toggle `bionic`, `answerFirst`, `chunks` or `actionMarkers`. |
| `/pace length <n>` | Set the word cap (`0` = no cap). |
| `/pace reset` | Restore defaults. |
| `/pace rate <1-5> [note]` | Append a rating to the log (§6.3). |
| `/pace report` | Average rating per switch combination. |

Changes take effect from the next prompt. Invalid input prints usage and changes nothing.
`$ARGUMENTS` is substituted into a shell command, so notes must not contain `"` or backticks;
`pace.py` documents this in its usage text.

## 5. Error handling

| Failure | Behaviour |
|---|---|
| Config missing | Defaults, no message. |
| Config malformed | Defaults, plus one rule line asking the model to flag it. |
| Rule fragment missing | Skip that fragment; continue. |
| Any exception in `inject.py` | Print nothing, exit 0. The prompt is never blocked. |
| Log file unwritable | `/pace rate` reports the error; nothing else is affected. |

## 6. Testing and measurement

### 6.1 Unit tests (`tests/`, `python3 -m unittest`)

- No config → every switch on, length 200.
- A switch off → its fragment absent from the output.
- `{length}` substituted; `length 0` omits the length fragment.
- Malformed config → defaults plus warning line.
- `HUMAN_PACE=0` and `/pace…` prompts → no output.
- Output is valid hook JSON; exit code is always 0, including on exceptions.
- `pace.py`: each subcommand changes config or log exactly as specified; invalid input changes nothing.
- The §3 bionic checker, against hand-written examples.

### 6.2 Compliance harness (`evals/`)

`evals/run.py` sends about 10 fixed prompts (`evals/prompts.txt`) through
`claude -p --plugin-dir <repo>` (verified on 2026-09-30 to load plugin hooks headless). It must not
set `HUMAN_PACE=0`. It scores each reply per rule:

- first line is one sentence;
- no paragraph over 3 sentences;
- prose word count within `length`;
- `▶ You:` appears only at the end;
- at least 90% of prose words match the §3 bionic algorithm;
- no bold inside code, paths, or text the prompt asks to be written for others (e.g. a commit message).

It prints a per-rule pass rate. It is run on demand, for example after rewording a rule, at a cost of
a few cents per run.

### 6.3 Personal experiment log

`/pace rate <1-5> [note]` appends
`{"ts": "<ISO-8601>", "switches": {…current config…}, "score": n, "note": "…"}` to
`~/.claude/human-pace-log.jsonl`. `/pace report` groups entries by switch combination and prints
count and mean score per group. Intended use: alternate settings week by week (e.g. bionic on, then
off) and compare.

## 7. Distribution

The repo is its own marketplace: `.claude-plugin/marketplace.json` lists the `human-pace` plugin with
source `./`. A teammate runs `/plugin marketplace add <git-url>` and then
`/plugin install human-pace@<marketplace-name>`. Whether a root-level plugin with source `./` is
accepted is checked during implementation; if it isn't, the plugin moves to `plugins/human-pace/`.
The repo stays local until the user pushes it.

## 8. Out of scope

- Rewriting or post-processing response text (no mechanism exists).
- Output-style variant, SessionStart hook, per-project config.
- Applying formatting to anything other than chat replies.
- Windows support (untested; `python3` assumption).
