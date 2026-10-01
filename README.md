# human-pace

**A** **Cl**aude **Co**de **pl**ugin **th**at **ma**kes **re**plies **ea**sier **t**o **fo**llow: **bi**onic **re**ading, **an**swer **fi**rst, **sh**ort
**ch**unks, **ma**rked **ac**tion **it**ems **a**nd **a** **le**ngth **c**ap. **Ev**ery **pa**rt **c**an **b**e **sw**itched **o**n **o**r **o**ff.

## Install

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

## Develop

```
python3 -m unittest discover -s tests -v     # unit tests
python3 compliance/run.py                    # score real replies (calls claude -p, costs a few cents)
python3 compliance/run.py --approach vowels  # score one approach; also --anchor-trigger <n>
```

**Ru**le **wo**rding **li**ves **i**n `rules/*.md`. **Ke**ep **a**ll **fra**gments **to**gether **un**der 700 **cha**racters **p**er **ap**proach.

## License

**M**IT; **s**ee `LICENSE`.
