"""Pure aggregation of validated local analytics events; no recording side effects."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import List

import pace_config as pc
from pace_analytics import normalize_config, utc, validate_event


def _ratio(n, d):
    return n / d if d else None


def summarize(events: List[dict], *, now: datetime, days: int) -> dict:
    now = utc(now)
    start = now - timedelta(days=days)
    seen, records = set(), []
    for event in events:
        if validate_event(event) is None or event['event_id'] in seen:
            continue
        if start <= datetime.fromisoformat(event['timestamp']) <= now:
            seen.add(event['event_id'])
            records.append(event)
    records.sort(key=lambda e: datetime.fromisoformat(e['timestamp']))
    configs, scores = {}, defaultdict(list)
    observed, active = set(), set()
    session_runs, changes = {}, Counter()
    invocations, errors, transitions = Counter(), Counter(), Counter()
    save_sources, fields = Counter(), Counter()
    associations = defaultdict(lambda: {'numerator': 0, 'denominator': 0})
    prompts = active_prompts = unassigned = saves = 0
    for e in records:
        kind, key = e['event'], e['session_key']
        cid = e.get('format_config_id')
        if cid is not None:
            row = configs.setdefault(cid, {'settings': normalize_config(e['settings']), 'prompts': 0,
                'active_prompts': 0, '_sessions': set(), '_days': set(), 'versions': Counter(),
                'integrations': Counter(), 'drift_guard': Counter()})
        if kind in ('session_observed', 'prompt_observed') and key:
            observed.add(key)
        if kind == 'command_invoked':
            invocations[(e['operation'], e['outcome'])] += 1
        elif kind == 'config_saved':
            saves += 1
            save_sources[(e['source'], e['config_source'])] += 1
            fields.update(e['changed_fields'])
        elif kind == 'config_observed_changed' and key:
            changes[key] += 1
        elif kind == 'rating_submitted':
            scores[cid].append(e['score'])
        elif kind == 'settings_error':
            errors[(e['source'], e['category'])] += 1
        elif kind == 'prompt_observed':
            prompts += 1
            active_prompts += int(e['enabled'])
            unassigned += int(key is None)
            row['prompts'] += 1
            row['active_prompts'] += int(e['enabled'])
            row['_days'].add(datetime.fromisoformat(e['timestamp']).date())
            row['versions'][e['plugin_version']] += 1
            row['integrations'][e['integration']] += 1
            row['drift_guard'][e['settings']['driftGuard']] += 1
            if key:
                row['_sessions'].add(key)
                if e['enabled']:
                    active.add(key)
                previous = session_runs.get(key)
                if previous is not None and previous != cid:
                    transitions[(previous, cid)] += 1
                session_runs[key] = cid
            dims = normalize_config(e['settings'], include_delivery=True)
            for dim, value in dims.items():
                if dim == 'anchorTrigger':
                    continue
                for switch in pc.SWITCHES:
                    if switch == dim:
                        continue
                    association = associations[(dim, value, switch)]
                    association['denominator'] += 1
                    association['numerator'] += int(e['settings'][switch])
    for row in configs.values():
        row['sessions'] = len(row.pop('_sessions'))
        row['days'] = len(row.pop('_days'))
        row['share'] = _ratio(row['prompts'], prompts)
        row['active_share'] = _ratio(row['active_prompts'], active_prompts)
    ratings = {cid: {'count': len(values), 'mean': sum(values)/len(values),
                    'distribution': {score: values.count(score) for score in range(1, 6)}}
               for cid, values in scores.items()}
    return {'invocations': dict(invocations), 'observed_sessions': len(observed),
            'active_sessions': len(active), 'active_prompts': active_prompts, 'prompts': prompts,
            'unassigned_prompts': unassigned, 'configurations': configs, 'transitions': dict(transitions),
            'editing': {'saves': saves, 'sources': dict(save_sources), 'fields': dict(fields)},
            'changes_per_active_session': _ratio(sum(changes[k] for k in active), len(active)),
            'ratings': ratings, 'errors': dict(errors), 'associations': dict(associations),
            'coverage': {'start': start.isoformat(), 'end': now.isoformat(),
                         'first': records[0]['timestamp'] if records else None,
                         'last': records[-1]['timestamp'] if records else None}}


def _percent(value):
    return 'not enough data' if value is None else f'{value:.1%}'


def config_label(cfg: dict) -> str:
    focus = normalize_config(pc.defaults())
    light = normalize_config({**pc.defaults(), 'bionic': False, 'length': 300})
    off = normalize_config({**pc.defaults(), **{k: False for k in pc.SWITCHES}, 'length': 0})
    preset = 'focus' if cfg == focus else 'light' if cfg == light else 'off' if cfg == off else 'custom'
    bionic = ('bionic ' + cfg['bionicApproach']) if cfg['bionic'] else 'bionic off'
    if cfg.get('bionicApproach') == 'third+anchor':
        bionic += f" ({cfg['anchorTrigger']}+ letters)"
    if cfg.get('bionicGradient', 'off') != 'off':
        bionic += ' / gradient ' + cfg['bionicGradient']
    switches = ', '.join(f"{k} {'on' if cfg[k] else 'off'}" for k in pc.SWITCHES if k != 'bionic')
    return f"{preset}: {bionic}, {switches}, length {cfg['length'] or 'uncapped'}"


def _header(summary, diagnostics):
    coverage = summary['coverage']
    start = diagnostics.get('window_start', coverage['start'])
    end = diagnostics.get('window_end', coverage['end'])
    lines = [f'Local usage · UTC {start} to {end}',
             'Claude hook coverage only; Codex/ChatGPT skill usage is unavailable.',
             'Best-effort observations of configured usage; prompt counts are hook deliveries.']
    first, last = coverage['first'], coverage['last']
    lines.append(f'Observed records: {first} to {last}' if first else 'No records in this window. Enable with /pace analytics on.')
    if diagnostics.get('retention_days', 365) < diagnostics.get('requested_days', 0):
        lines.append(f"Window limited by {diagnostics['retention_days']}-day retention.")
    if 'enabled' in diagnostics:
        lines.append('Recording: ' + ('on' if diagnostics['enabled'] else 'off'))
    for key in ('malformed', 'unsupported', 'duplicates'):
        if diagnostics.get(key):
            lines.append(f"Skipped {key} records: {diagnostics[key]}")
    if diagnostics.get('capped_days'):
        lines.append('Incomplete days (storage cap reached): ' + ', '.join(diagnostics['capped_days']))
    return lines


def _rows(summary):
    return sorted(summary['configurations'].items(), key=lambda item: (-item[1]['prompts'], item[0]))


def render_usage(summary: dict, diagnostics: dict, *, compact: bool = False) -> str:
    lines = _header(summary, diagnostics)
    lines.extend([
        f"Invocations: {sum(summary['invocations'].values())} · settings saves: {summary['editing']['saves']}",
        f"Prompts: {summary['prompts']} · enabled: {summary['active_prompts']} · off: {summary['prompts'] - summary['active_prompts']}",
        f"Sessions observed: {summary['observed_sessions']} · active: {summary['active_sessions']}",
        f"Prompts excluded from session/transition analysis (no session ID): {summary['unassigned_prompts']}"])
    changes = summary['changes_per_active_session']
    lines.append('Observed changes per active session: ' + ('not enough data' if changes is None else f'{changes:.2f}'))
    rows = _rows(summary)
    for cid, row in (rows[:3] if compact else rows):
        lines.append(f"{cid[:8]} · {row['prompts']} prompts · {_percent(row['share'])} of all / {_percent(row['active_share'])} of enabled · {row['sessions']} sessions · {row['days']} days · {config_label(row['settings'])}")
        if not compact:
            for dimension in ('versions', 'integrations', 'drift_guard'):
                values = ', '.join(f'{key}: {count}' for key, count in sorted(row[dimension].items()))
                lines.append(f'  {dimension}: {values or "no prompt exposure"}')
    if not compact:
        for (operation, outcome), count in sorted(summary['invocations'].items()):
            lines.append(f'Command {operation} / {outcome}: {count}')
        for (source, config_source), count in sorted(summary['editing']['sources'].items()):
            lines.append(f'Saves {source} / {config_source}: {count}')
        for field, count in sorted(summary['editing']['fields'].items()):
            lines.append(f'Saved field {field}: {count}')
        for (source, category), count in sorted(summary['errors'].items()):
            lines.append(f'Error observations {source} / {category}: {count}')
    lines.append('Sessions per configuration overlap. Saved edits and observed changes are separate counts.')
    if compact:
        lines.append('Details: /pace report usage 30 · /pace report compare 30')
    return '\n'.join(lines)


def render_compare(summary: dict, diagnostics: dict) -> str:
    lines = _header(summary, diagnostics)
    lines.append('Ratings recorded while analytics was enabled; no historical rating-log backfill.')
    for cid, row in _rows(summary):
        rating = summary['ratings'].get(cid)
        if rating:
            detail = f"{rating['mean']:.1f}/5 · {rating['count']} ratings"
            if rating['count'] < 5:
                detail += ' (sparse)'
            detail += ' · scores ' + ', '.join(f'{k}: {v}' for k, v in rating['distribution'].items())
        else:
            detail = 'no ratings'
        lines.append(f"{cid[:8]} · {detail} · {row['prompts']} prompts · {row['days']} days · {config_label(row['settings'])}")
    lines.append('Transitions between consecutive prompt configurations within a known session:')
    for (previous, current), count in sorted(summary['transitions'].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f'{previous[:8]} → {current[:8]}: {count}')
    if not summary['transitions']:
        lines.append('No observed transitions.')
    lines.append('Setting associations (enabled-switch prompts / prompts with the named setting):')
    for (dimension, value, switch), counts in sorted(summary['associations'].items(), key=lambda item: str(item[0])):
        n, d = counts['numerator'], counts['denominator']
        lines.append(f'{dimension}={value} → {switch} on: {n}/{d} ({_percent(_ratio(n, d))})')
    lines.append('Associations reflect local usage, not causation or reading performance. Inactive bionic options are excluded.')
    return '\n'.join(lines)
