# human-pace

**A** **Cl**aude **Co**de **pl**ugin **th**at **ma**kes **re**plies **ea**sier **t**o **fo**llow: **bi**onic **re**ading, **an**swer **fi**rst, **sh**ort
**ch**unks, **ma**rked **ac**tion **it**ems **a**nd **a** **le**ngth **c**ap. **Ev**ery **pa**rt **c**an **b**e **sw**itched **o**n **o**r **o**ff.

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

## Install for Claude Code

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
| `/pace report` | Average rating per setting |

**Ch**anges **ap**ply **fr**om **yo**ur **ne**xt **pr**ompt; **t**he **up**dated **ru**les **a**re **se**nt **on**ce. **Se**ttings **li**ve **i**n `~/.claude/human-pace.json`, **a**nd **ra**tings **i**n
`~/.claude/human-pace-log.jsonl`.

**App**roaches: `third` **bo**lds **t**he **fi**rst **th**ird **o**f **ea**ch **wo**rd; `vowels` **a**nd `consonants` **bo**ld **th**ose **le**tters; `third+anchor` **ad**ds **o**ne **con**sonant **ne**ar **t**he **e**nd **o**f **lo**ng **wo**rds.

**He**adless **ru**ns (`claude -p`, **t**he **Ag**ent **S**DK) **a**re **sk**ipped, **s**o **sc**ripts **a**nd **C**I **g**et **pl**ain **ou**tput.
**S**et `HUMAN_PACE=1` **t**o **fo**rce **t**he **ru**les **o**n **th**ere, **o**r `HUMAN_PACE=0` **t**o **tu**rn **th**em **o**ff **eve**rywhere.

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
