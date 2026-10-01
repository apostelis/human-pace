# human-pace

**A** **Cl**aude **Co**de **pl**ugin **th**at **ma**kes **rep**lies **ea**sier **t**o **fo**llow: **bi**onic **rea**ding, **an**swer **fi**rst, **sh**ort
**ch**unks, **ma**rked **ac**tion **it**ems **a**nd **a** **le**ngth **c**ap. **Ev**ery **pa**rt **c**an **b**e **swi**tched **o**n **o**r **o**ff.

## Install

```
/plugin marketplace add apostelis/human-pace
/plugin install human-pace@human-pace
```

**T**he **ru**les **a**re **se**nt **on**ce **wh**en **a** **ses**sion **st**arts (**a**nd **ag**ain **af**ter `/compact` **o**r `/resume`), **n**ot **ab**ove
**ev**ery **re**ply.

**Req**uires `python3` (3.9+). **Wit**hout **i**t **t**he **pl**ugin **do**es **not**hing, **a**nd **yo**ur **pro**mpts **a**re **ne**ver **blo**cked.

**Con**text **co**st: **un**der 200 **to**kens **o**f **ru**les, **se**nt **on**ce **p**er **ses**sion, **pl**us **ab**out 40 **f**or **t**he `/pace` **com**mand.
**Wi**th `/pace off` **not**hing **i**s **se**nt.

## Use

| Command | Effect |
|---|---|
| `/pace` | Show switches |
| `/pace <switch> on\|off` | `bionic`, `answerFirst`, `chunks`, `actionMarkers` |
| `/pace length <n>` | Prose word cap, `0` = no cap |
| `/pace preset focus\|light\|off` | `focus`: all on · `light`: no bionic, 300 words · `off`: all off |
| `/pace on` / `/pace off` | Same as `preset focus` / `preset off` |
| `/pace reset` | Restore defaults |
| `/pace rate <1-5> [note]` | Log how the current setting feels |
| `/pace report` | Average rating per setting |

**Cha**nges **ap**ply **fr**om **yo**ur **ne**xt **pr**ompt; **t**he **upd**ated **ru**les **a**re **se**nt **on**ce. **Set**tings **li**ve **i**n `~/.claude/human-pace.json`, **a**nd **rat**ings **i**n
`~/.claude/human-pace-log.jsonl`.

**Hea**dless **ru**ns (`claude -p`, **t**he **Ag**ent **S**DK) **a**re **ski**pped, **s**o **scr**ipts **a**nd **C**I **g**et **pl**ain **ou**tput.
**S**et `HUMAN_PACE=1` **t**o **fo**rce **t**he **ru**les **o**n **th**ere, **o**r `HUMAN_PACE=0` **t**o **tu**rn **th**em **o**ff **ever**ywhere.

## Develop

```
python3 -m unittest discover -s tests -v     # unit tests
python3 compliance/run.py                    # score real replies (calls claude -p, costs a few cents)
```

**Ru**le **wor**ding **li**ves **i**n `rules/*.md`. **Ke**ep **a**ll **fra**gments **tog**ether **un**der 700 **char**acters.

## License

MIT; **s**ee `LICENSE`.
