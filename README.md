# human-pace

**A** **Cl**aude **Co**de **pl**ugin **th**at **ma**kes **re**plies **ea**sier **t**o **fo**llow: **bi**onic **re**ading, **an**swer **fi**rst, **sh**ort
**ch**unks, **ma**rked **ac**tion **it**ems **a**nd **a** **le**ngth **c**ap. **Ev**ery **pa**rt **c**an **b**e **sw**itched **o**n **o**r **o**ff.

## Install for Claude Code

Local usage recording is **on by default** in the Claude integration. Events stay
on your machine; nothing is uploaded. Disable it with `/pace analytics off`.
See [local usage analytics](#local-usage-analytics) for recorded fields and controls.

```
/plugin marketplace add apostelis/human-pace
/plugin install human-pace@human-pace
```

**T**he **ru**les **a**re **se**nt **on**ce **wh**en **a** **se**ssion **st**arts (**a**nd **ag**ain **af**ter `/compact` **o**r `/resume`), **n**ot **ab**ove
**ev**ery **re**ply.

**Re**quires `python3` (3.9+). **Wi**thout **i**t **t**he **pl**ugin **do**es **no**thing, **a**nd **yo**ur **pr**ompts **a**re **ne**ver **bl**ocked.

**Co**ntext **co**st: **un**der 200 **to**kens **o**f **ru**les, **se**nt **on**ce **p**er **se**ssion **a**nd **ag**ain **ev**ery 10 **pr**ompts, **pl**us **ab**out 40 **f**or **t**he `/pace` **co**mmand.
**Wi**th `/pace off` **no**thing **i**s **se**nt.

## Use

| Command | Effect |
|---|---|
| `/pace` | Show switches |
| `/pace <switch> on\|off` | `bionic`, `answerFirst`, `chunks`, `actionMarkers` |
| `/pace bionic <approach>` | `third`, `vowels`, `consonants` or `third+anchor`; turns bionic on |
| `/pace anchor-trigger <n>` | Word length that gets an anchor consonant in `third+anchor` (default 8) |
| `/pace length <n>` | Prose word cap, `0` = no cap |
| `/pace drift-guard <n>` | Resend the rules every n prompts (default 10, `0` = off) |
| `/pace preset focus\|light\|off` | `focus`: all on · `light`: no bionic, 300 words · `off`: all off |
| `/pace on` / `/pace off` | Same as `preset focus` / `preset off` |
| `/pace reset` | Restore defaults |
| `/pace rate <1-5> [note]` | Log how the current setting feels |
| `/pace report` | Ratings plus a compact 30-day local usage summary |

**Ch**anges **ap**ply **fr**om **yo**ur **ne**xt **pr**ompt; **t**he **up**dated **ru**les **a**re **se**nt **on**ce. **Se**ttings **li**ve **i**n `~/.claude/human-pace.json`, **a**nd **ra**tings **i**n
`~/.claude/human-pace-log.jsonl`.

**App**roaches: `third` **bo**lds **t**he **fi**rst **th**ird **o**f **ea**ch **wo**rd; `vowels` **a**nd `consonants` **bo**ld **th**ose **le**tters; `third+anchor` **ad**ds **o**ne **con**sonant **ne**ar **t**he **e**nd **o**f **lo**ng **wo**rds.

**He**adless **ru**ns (`claude -p`, **t**he **Ag**ent **S**DK) **a**re **sk**ipped, **s**o **sc**ripts **a**nd **C**I **g**et **pl**ain **ou**tput.
**S**et `HUMAN_PACE=1` **t**o **fo**rce **t**he **ru**les **o**n **th**ere, **o**r `HUMAN_PACE=0` **t**o **tu**rn **th**em **o**ff **eve**rywhere.

## Local usage analytics

Local recording starts automatically when you use the supported integration. Inspect it with:

```text
/pace analytics
/pace report usage 30
/pace report compare 30
```

Recording is on by default. An explicit `/pace analytics off` choice persists
across restarts, formatting resets, and history clears. Everything stays on this
machine; no events are uploaded. The usage report shows command invocations, enabled/off prompts,
observed and active sessions, configuration shares, repeat usage across days,
saved edits, observed changes, and settings errors. The comparison report shows
configuration transitions, ratings with sample counts, and setting associations
such as the share of prompts with chunks enabled for each bionic approach.

| Command | Effect |
|---|---|
| `/pace analytics` | Status, storage location, retention, coverage, and retained date range |
| `/pace analytics on` / `/pace analytics off` | Start/stop future local recording; retain existing history |
| `/pace analytics retention 90` | Retain 1–365 days; default 90 |
| `/pace analytics export` | Print validated retained events as JSONL |
| `/pace analytics clear` | Delete analytics history and rotate its local session secret; preserve ratings and recording preferences |
| `/pace report usage [days]` | Detailed usage; default 30 days, range 1–365 |
| `/pace report compare [days]` | Configuration comparisons over the same kind of window |

To stop recording, use `/pace analytics off`; to resume, use `/pace analytics on`.
The controls also work when native formatting options are selected. `/pace reset`
resets formatting only. The existing rating log remains the source of the first
part of `/pace report`; analytics comparisons use ratings recorded while analytics
was enabled, with no historical backfill. Reports and analytics commands never
record themselves.

**What the counts mean.** A prompt is an eligible Claude hook delivery, even when
unchanged rules are not resent. “Enabled” means at least one formatting option or
a length cap was configured; it does not verify model compliance. Resume and
compaction do not create additional distinct sessions. Without a host event ID,
repeated hook deliveries cannot be distinguished from distinct prompts. Missing
session IDs are excluded from session/transition analysis, with their count shown.
Sessions using multiple configurations appear in multiple configuration rows.

Successful changed saves measure editing. A new configuration seen by a hook
measures an observed change; these counts are separate. Native-panel or manual
file edits are detected on the next hook, so intermediate edits can be missed.
Transitions use consecutive prompt configurations in the same session. Inactive
bionic options do not split configuration groups; drift guard is shown separately.
Associations describe local usage, not reading speed or comprehension. Fewer than
five ratings is labeled sparse.

**Coverage and storage.** Automatic prompt/session recording covers the Claude
hook integration. Executed local commands and browser settings actions are also
recorded; their integration is marked unknown when the host cannot be verified.
Codex/ChatGPT's skill and the experimental embedded MCP app are not instrumented.
The hook honors `HUMAN_PACE=0` and skips SDK use unless `HUMAN_PACE=1`.

Data lives in `~/.claude/human-pace-analytics/`; `HUMAN_PACE_ANALYTICS_DIR` overrides
that directory. Events contain timestamps, plugin version, settings, bounded
operation/error categories, numeric ratings, and locally keyed session hashes.
They exclude prompts, replies, rating notes, paths, raw session IDs, and error
messages. UTC defines report windows, daily files, and active-day counts.

Recording is best effort: lock contention or storage errors can drop events and
never prevent normal formatting or a successful settings save. Each event is
limited to 16 KiB and each day's event file to 10 MiB; reports identify capped days
when a cap marker could be saved. Cleanup is lazy, during session start or analytics
controls/reports; readers exclude expired records before cleanup. Disabling keeps
history until it expires or you clear it. Local locking requires macOS/Linux
`fcntl`; unsupported platforms report that limitation for controls and skip recording.

### Why measure an open-source plugin?

Open source still needs a business case for ongoing development and maintenance.
These metrics help test whether human-pace delivers recurring value and where
further investment is justified:

| Decision | Evidence to examine |
|---|---|
| Is it used repeatedly? | Active sessions, active days, and return to configurations |
| Which features deserve investment? | Configuration exposure, common combinations, transitions, and reversions |
| Are users finding value? | Ratings alongside repeat usage and sample sizes |
| Where is support effort needed? | Settings-error observations and failed command outcomes |

Local data validates the measurements and individual usage patterns. Maintainers
cannot see it automatically, so this phase cannot establish community adoption,
revenue, or willingness to pay. A later gathering phase can support broader
adoption and retention evidence; maintenance costs and commercial demand still
need separate evidence. Remote gathering remains a separate future phase.

## Configure through Claude’s plugin panel

On Claude Code 2.1.271 or newer, open `/plugin`, select **Installed → human-pace →
Configure options**, and set **Configuration source** to **native**. You can then
change bionic reading, its approach, gradients, paragraph layout, action markers,
word limit, and reminder interval from the panel. These fields also appear in
`/config`. Let Claude reload the plugin when prompted; updated rules apply to the
next ordinary prompt.

The default source is **commands**, preserving your existing `/pace` settings in
`~/.claude/human-pace.json`. In **native** mode the panel owns the settings and
`/pace` formatting changes are declined; ratings, reports, and analytics controls still work. Switch
back to **commands** to restore the settings file without losing it. Native
values are validated again by the hook; invalid fields use their defaults.
Picker fields require Claude Code 2.1.271+, including when using commands mode.
Claude Desktop’s graphical plugin UI may not expose Configure options yet.

### Settings with live preview (including Claude Desktop)

Choose **human-pace:pace-settings** from Claude’s command picker, or ask Claude to
run the Human Pace `pace-settings` command. `/human-pace:pace-settings` and
`/human-pace:pace-preview` both open the same browser settings page. No terminal
commands are required from you. This is a separate browser page, not an embedded
Claude Desktop panel; the Desktop app may not show the native configuration dialog.

Compare all four bionic approaches, gradients, paragraph layout, and word limits,
or paste your own plain prose. Choose explanations, technical text, instructions,
or narratives, and select **New passage** to try unfamiliar text. Each category
has three passages; none repeats until that category is exhausted. Changing
formatting keeps the passage in place for comparison. These examples are not a
reading-performance assessment. Set the reminder interval and select **Save
settings** to apply your choices. In command mode, Save writes the existing
`~/.claude/human-pace.json` (or `HUMAN_PACE_CONFIG` override); changes apply on the
next ordinary prompt. In native mode, Save calls Claude’s plugin configuration
API; reload the plugin or restart the Claude session after saving. Save errors
are shown in the page and do not claim that changes were applied.

The page starts with your user-level native choices when native mode is selected,
otherwise with your `/pace` settings. Managed or inline settings are resolved by
Claude’s hooks but are not available to the settings subprocess, so its initial
choices may differ in those environments. The server listens only on localhost,
uses an unguessable page URL, and expires after 30 minutes. Reopen it from Claude
if it expires. Roboto Flex is fetched from Google Fonts for variable weights,
with a system-font fallback when unavailable. Gradients appear in the browser;
ordinary Claude chat continues to use Markdown bolding.

For a standalone preview without Save, `python3 scripts/preview.py --output
preview.html` still produces an HTML file.

## ChatGPT and Codex

This repository also packages a portable OpenAI skill in `skills/human-pace/`
and a root `plugin.json`. The Claude plugin remains in `.claude-plugin/`.

### ChatGPT website or app: custom instructions

Copy [custom-instructions.txt](integrations/chatgpt/custom-instructions.txt) into
Settings → Personalization → Custom Instructions, or into a project's instructions
to limit it to that project. You can also paste it into one chat. This enables the
default focus formatting; ask for changes in ordinary language, such as
“turn bionic reading off” or “use a 300-word cap”.

This option requires no Python or plugin installation. It does not run `/pace`,
save local settings, log ratings, or automatically resend rules. Changes made in a
chat do not edit your saved Custom Instructions. Remove the saved instructions to
disable them for future chats.

### ChatGPT Work and Codex: shared plugin

Register this checkout as a local marketplace:

```sh
codex plugin marketplace add /absolute/path/to/human-pace
```

In the desktop app's Plugins Directory, select the human-pace marketplace and
install Human Pace. Restart the app if the local marketplace is not visible.
Invoke the human-pace skill in a new chat, then request your task.
Availability depends on the host's support for local plugins and skills.

For Codex CLI or desktop without plugin installation, copy the self-contained skill
into the user's skill directory (run from this repository; do not overwrite an
existing skill):

```sh
mkdir -p ~/.agents/skills
cp -R skills/human-pace ~/.agents/skills/human-pace
```

Restart Codex and invoke `$human-pace`. To limit the skill to one repository,
copy it into that repository's `.agents/skills/` instead.

The skill supports formatting switches, all four bionic approaches, length,
anchor trigger, and presets. Settings last within the current chat. `/pace` is
conversational syntax when the request reaches the skill, not a registered OpenAI
slash command; ordinary language works too. Claude's session hooks, drift guard,
and persistent rating log are not part of this skill. Model formatting is best
effort, as it is with the Claude rules.

See OpenAI's [plugin packaging guide](https://developers.openai.com/plugins/build/plugins),
[skill guide](https://learn.chatgpt.com/docs/build-skills), and
[Custom Instructions guide](https://help.openai.com/en/articles/8096356-chatgpt-custom-instructions).


## Experimental gradients

For special cases in HTML/CSS-capable reply surfaces, opt in with:

```text
/pace experimental gradient color
/pace experimental gradient weight
/pace experimental gradient both
/pace experimental gradient off
```

`color` adds a purple-to-blue gradient to the letters selected by your bionic
approach. `weight` decreases variable-font weight from 800 to 400 across each
word. `both` combines the weight change with color fading toward normal text.
These are experimental visual styles, not established reading improvements.
They are off by default. Selecting a style enables bionic; selecting `off`
keeps your bionic approach. Presets retain the style; reset clears it.

Ordinary Markdown chat cannot display these effects and uses the selected
bionic approach instead. The plugin supplies formatting instructions, not a
chat renderer; gradients require the host to provide an HTML/CSS reply surface
and, for weight, a variable font. This setting does not generate files or
change the formatting of code, paths, URLs, identifiers, or tables.

For an explicitly requested HTML preview, `python3 scripts/render_gradient.py
--mode both` reads plain prose from stdin and emits an escaped HTML fragment.
The helper uses the default third prefix in color mode; it is not a Markdown
parser, so supply only the prose you want to preview. It is also bundled with
the portable skill.

## Develop

```
python3 -m unittest discover -s tests -v     # unit tests
python3 scripts/export_openai.py             # refresh shared skill rules and ChatGPT text
python3 scripts/export_openai.py --check     # verify exports match rules/*.md
python3 compliance/run.py                    # score real replies (calls claude -p, costs a few cents)
python3 compliance/run.py --approach vowels  # score one approach; also --anchor-trigger <n>
```

**Ru**le **wo**rding **li**ves **i**n `rules/*.md`. **Ke**ep **a**ll **fra**gments **to**gether **un**der 700 **cha**racters **p**er **ap**proach.

## License

**M**IT; **s**ee `LICENSE`.
