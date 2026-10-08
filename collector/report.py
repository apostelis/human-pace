"""Private fixed-window reports; no HTTP report endpoint or arbitrary drilldowns."""
import argparse
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pace_remote_contract as c
from collector.store import CollectorError

def summarize(events,*,start,end):
    if not isinstance(start,date) or not isinstance(end,date) or start>end:raise ValueError('Invalid UTC window')
    retained=[];seen=set()
    for raw in events:
        try:e=c.validate_event(raw)
        except c.ContractError:continue
        identity=(e['installation_id'],e['event_id'])
        if identity in seen:continue
        seen.add(identity);retained.append(e)
    selected=[e for e in retained if start.isoformat()<=e['day']<=end.isoformat()]
    prompts=[e for e in selected if e['event']=='prompt_observed']
    enabled=[e for e in prompts if e['enabled']]
    active={e['installation_id'] for e in enabled}
    configurations={}
    for e in selected:
        if 'format_config_id' not in e:continue
        row=configurations.setdefault(e['format_config_id'],dict(settings=e['settings'],prompts=0,enabled=0,identities=set(),rating_identities=set(),scores=[],rating_histogram=Counter(),score_identities=defaultdict(set),active_days=defaultdict(set)))
        if e['event']=='prompt_observed':
            row['prompts']+=1;row['enabled']+=int(e['enabled']);row['identities'].add(e['installation_id'])
            if e['enabled']:row['active_days'][e['installation_id']].add(e['day'])
        elif e['event']=='rating_submitted':
            row['rating_identities'].add(e['installation_id']);row['scores'].append(e['score']);row['rating_histogram'][e['score']]+=1;row['score_identities'][e['score']].add(e['installation_id'])
    for row in configurations.values():
        row['prompt_share']=(row['prompts'],len(prompts));row['active_prompt_share']=(row['enabled'],len(enabled))
        row['installation_adoption']=(len(row['identities']&active),len(active))
        row['rating_mean']=sum(row['scores'])/len(row['scores']) if row['scores'] else None
    sessions=defaultdict(list)
    for e in prompts:
        if e['session_key'] is not None:sessions[(e['installation_id'],e['session_key'])].append(e)
    transitions={}
    for (identity,_),values in sessions.items():
        values.sort(key=lambda e:e['prompt_sequence'])
        for a,b in zip(values,values[1:]):
            if b['prompt_sequence']==a['prompt_sequence']+1 and a['format_config_id']!=b['format_config_id']:
                row=transitions.setdefault((a['format_config_id'],b['format_config_id']),dict(count=0,identities=set()))
                row['count']+=1;row['identities'].add(identity)
    days=defaultdict(set)
    for e in retained:
        if e['event']=='prompt_observed' and e['enabled']:days[e['installation_id']].add(date.fromisoformat(e['day']))
    mature=returned=0
    for values in days.values():
        first=min(values)
        if start<=first<=end and first+timedelta(days=13)<=end:
            mature+=1;returned+=int(any(first+timedelta(days=7)<=day<=first+timedelta(days=13) for day in values))
    breakdowns={kind:{} for kind in ('config_saved','config_observed_changed','command_invoked','settings_error')}
    fields={kind:{} for kind in ('config_saved','config_observed_changed')}
    for e in selected:
        kind=e['event']
        if kind not in breakdowns:continue
        dimension=(e['source'],e['config_source']) if kind in fields else (e['operation'],e['outcome']) if kind=='command_invoked' else (e['source'],e['category'])
        row=breakdowns[kind].setdefault(dimension,dict(count=0,identities=set()));row['count']+=1;row['identities'].add(e['installation_id'])
        if kind in fields:
            for key in e['changed_fields']:
                row=fields[kind].setdefault(key,dict(count=0,identities=set()));row['count']+=1;row['identities'].add(e['installation_id'])
    return dict(start=start.isoformat(),end=end.isoformat(),reporting_installations=len({e['installation_id'] for e in selected}),
        active_installations=len(active),prompt_count=len(prompts),enabled_prompt_count=len(enabled),
        unknown_session_prompts=sum(e['session_key'] is None for e in prompts),observed_sessions=len(sessions),
        configurations=configurations,transitions=transitions,cohort_return=(returned,mature),
        breakdowns=breakdowns,changed_fields=fields,latest_day=max((e['day'] for e in selected),default=None),
        coverage=sorted({(e['integration'],e['plugin_version'],e['normalization_version'] if 'normalization_version' in e else None) for e in selected},key=str))

def ratio(pair):
    n,d=pair
    return f'{n}/{d} ({100*n/d:.1f}%)' if d else 'not enough data'

def render(s):
    lines=[f"UTC window: {s['start']} to {s['end']} (inclusive). Latest received event day: {s['latest_day'] or 'none'}.",
      f"Ingestion health: {s['reporting_installations']} reporting identities; {s['active_installations']} active identities.",
      'Identities represent consent epochs, not people. Manual uploads, eviction, expiry and missing observations create selection bias.',
      'Coverage: '+str(s['coverage'])+'; uninstrumented skill usage is unavailable.',
      'First observed activity is not installation date; missing return uploads are not proof of churn. Cohorts use retained history only.']
    rows=[(key,row) for key,row in s['configurations'].items() if row['prompts']]
    if s['active_installations']<5 or any(len(row['identities'])<5 for _,row in rows):
        lines.append('Configuration comparisons suppressed: fewer than five contributing identities in at least one slice. Complementary totals/shares withheld.')
    else:
        for key,row in sorted(rows):
            lines.append(f"Configuration {key}: exposure {ratio(row['prompt_share'])}; enabled exposure {ratio(row['active_prompt_share'])}; installation adoption {ratio(row['installation_adoption'])}.")
            if len(row['rating_identities'])>=5:
                lines.append(f"Ratings: mean {row['rating_mean']:.2f}; n={len(row['scores'])}; contributors={len(row['rating_identities'])}; {'sparse' if len(row['scores'])<5 else 'observational'}.")
                if all(len(ids)>=5 for ids in row['score_identities'].values()):lines.append('Score distribution: '+str(dict(row['rating_histogram'])))
                else:lines.append('Score distribution suppressed.')
            elif row['scores']:lines.append('Ratings suppressed: fewer than five contributors.')
            day_counts=[len(days) for days in row['active_days'].values()]
            if len(day_counts)>=5:lines.append(f"Active days per identity: mean {sum(day_counts)/len(day_counts):.2f}.")
    for kind,rows in {**s['breakdowns'],**{k+'_fields':v for k,v in s['changed_fields'].items()},'transitions':s['transitions']}.items():
        if rows and all(len(row['identities'])>=5 for row in rows.values()) and s['active_installations']>=5:
            lines.append(kind+': '+str({str(k):v['count'] for k,v in rows.items()}))
        elif rows:lines.append(kind+': suppressed (including complementary totals).')
    returned,mature=s['cohort_return']
    if mature>=5 and (returned==0 or returned>=5) and (mature-returned==0 or mature-returned>=5):
        lines.append('Mature first-observed cohort return on days 7–13: '+ratio((returned,mature)))
    else:lines.append('Cohort return: suppressed or not enough data.')
    lines.append('Usage and ratings do not establish reading speed, comprehension or causal benefit.')
    return '\n'.join(lines)

def read_events(database,*,start,end):
    database=Path(database);ready=database.with_suffix('.ready')
    if database.is_symlink() or ready.is_symlink() or not ready.exists():raise CollectorError('restore_not_ready')
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        rows=db.execute('SELECT e.body FROM events e JOIN installations i ON e.identity=i.identity WHERE i.revoked=0 AND e.day>=? AND e.day<=? ORDER BY e.day',(start.isoformat(),end.isoformat())).fetchall()
    return [c.validate_event(c.strict_json(raw,max_bytes=c.MAX_EVENT_BYTES)) for raw, in rows]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--start',type=date.fromisoformat,required=True);parser.add_argument('--end',type=date.fromisoformat,required=True)
    args=parser.parse_args();today=datetime.now(timezone.utc).date()
    if args.start>args.end or args.end>today or args.start<today-timedelta(days=89):parser.error('Window must be within retained 90 UTC days.')
    try:
        events=read_events(args.database,start=today-timedelta(days=89),end=args.end)
        print(render(summarize(events,start=args.start,end=args.end)))
    except (CollectorError,OSError,sqlite3.Error,c.ContractError):parser.exit(1,'Report unavailable; inspect restore readiness and storage.\n')
if __name__=='__main__':main()
