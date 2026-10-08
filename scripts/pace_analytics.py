"""Local-only usage events. No recording occurs until explicitly enabled."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pace_config as pc

MAX_EVENT_BYTES = 16 * 1024
MAX_DAY_BYTES = 10 * 1024 * 1024
OPERATIONS = {'status', 'toggle', 'approach', 'gradient', 'anchor_trigger', 'length',
              'drift_guard', 'preset', 'reset', 'rate', 'preview', 'settings_open',
              'settings_save', 'unknown'}
ERRORS = {'config_read_or_validation', 'invalid_settings', 'save_failed', 'rating_failed'}
FIELDS = {
    'command_invoked': {'operation', 'outcome'},
    'session_observed': set(),
    'prompt_observed': {'enabled'},
    'config_saved': {'previous_settings', 'changed_fields'},
    'config_observed_changed': {'previous_settings', 'changed_fields'},
    'rating_submitted': {'score'},
    'settings_error': {'category', 'invalid_fields'},
}
BASE = {'schema_version', 'event_id', 'event', 'timestamp', 'plugin_version',
        'integration', 'source', 'session_key'}
CONFIG = {'settings', 'format_config_id', 'config_id', 'normalization_version', 'config_source'}
CONFIG_REQUIRED = set(FIELDS) - {'command_invoked', 'settings_error'}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def utc(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('An aware timestamp is required')
    return now.astimezone(timezone.utc)


def valid_config(cfg: object) -> bool:
    if not isinstance(cfg, dict) or set(cfg) != set(pc.DEFAULTS):
        return False
    try:
        return not pc.validate(cfg)[1]
    except (TypeError, ValueError):
        return False


def normalize_config(cfg: dict, *, include_delivery: bool = False) -> dict:
    if not valid_config(cfg):
        raise ValueError('Invalid analytics settings snapshot')
    result = {key: cfg[key] for key in pc.DEFAULTS if key != 'driftGuard'}
    if not cfg['bionic']:
        for key in ('bionicApproach', 'anchorTrigger', 'bionicGradient'):
            result.pop(key)
    elif cfg['bionicApproach'] != 'third+anchor':
        result.pop('anchorTrigger')
    if include_delivery:
        result['driftGuard'] = cfg['driftGuard']
    return result


def config_identity(cfg: dict) -> dict:
    def digest(delivery):
        payload = json.dumps({'normalization_version': 1,
                              'settings': normalize_config(cfg, include_delivery=delivery)},
                             sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
    return {'settings': dict(cfg), 'format_config_id': digest(False),
            'config_id': digest(True), 'normalization_version': 1}


def plugin_version() -> str:
    try:
        value = json.loads((Path(__file__).resolve().parent.parent / 'plugin.json').read_text())['version']
        if isinstance(value, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][\w.-]+)?', value):
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 'unknown'


def make_event(kind: str, *, now: datetime, integration: str, source: str,
               session_key: Optional[str] = None, cfg: Optional[dict] = None,
               config_source: Optional[str] = None, **fields) -> dict:
    event = {'schema_version': 1, 'event_id': uuid.uuid4().hex, 'event': kind,
             'timestamp': utc(now).isoformat(), 'plugin_version': plugin_version(),
             'integration': integration, 'source': source, 'session_key': session_key}
    if cfg is not None:
        event.update(config_identity(cfg), config_source=config_source)
    event.update(fields)
    if kind in ('config_saved', 'config_observed_changed'):
        previous = fields.get('previous_settings')
        if not valid_config(previous) or cfg is None:
            raise ValueError('A previous settings snapshot is required')
        event['changed_fields'] = sorted(k for k in pc.DEFAULTS if previous[k] != cfg[k])
    if validate_event(event) is None:
        raise ValueError('Invalid analytics event')
    return event


def validate_event(value: object) -> Optional[dict]:
    """Reject unknown fields and forged derived values before reading or exporting."""
    try:
        if not isinstance(value, dict) or value.get('event') not in FIELDS:
            return None
        kind = value['event']
        with_cfg = 'settings' in value
        expected = BASE | FIELDS[kind] | (CONFIG if with_cfg else set())
        if set(value) != expected or (kind in CONFIG_REQUIRED and not with_cfg):
            return None
        if type(value['schema_version']) is not int or value['schema_version'] != 1:
            return None
        if not isinstance(value['event_id'], str) or not re.fullmatch(r'[0-9a-f]{32}', value['event_id']):
            return None
        timestamp = datetime.fromisoformat(value['timestamp'])
        if utc(timestamp) != timestamp or timestamp.utcoffset().total_seconds() != 0:
            return None
        if value['integration'] not in ('claude', 'unknown') or value['source'] not in ('hook', 'pace', 'preview'):
            return None
        version = value['plugin_version']
        if not isinstance(version, str) or (version != 'unknown' and not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][\w.-]+)?', version)):
            return None
        key = value['session_key']
        if key is not None and (not isinstance(key, str) or not HEX64.fullmatch(key)):
            return None
        if kind == 'session_observed' and key is None:
            return None
        if with_cfg:
            if value['config_source'] not in ('commands', 'native') or not valid_config(value['settings']):
                return None
            if type(value['normalization_version']) is not int:
                return None
            if any(value[k] != v for k, v in config_identity(value['settings']).items()):
                return None
        if kind == 'command_invoked':
            if value['operation'] not in OPERATIONS or value['outcome'] not in ('success', 'invalid', 'error'):
                return None
        elif kind == 'prompt_observed':
            enabled = any(value['settings'][k] for k in pc.SWITCHES) or value['settings']['length'] > 0
            if type(value['enabled']) is not bool or value['enabled'] != enabled:
                return None
        elif kind in ('config_saved', 'config_observed_changed'):
            previous = value['previous_settings']
            if not valid_config(previous):
                return None
            changed = sorted(k for k in pc.DEFAULTS if previous[k] != value['settings'][k])
            if not changed or value['changed_fields'] != changed:
                return None
        elif kind == 'rating_submitted':
            if type(value['score']) is not int or not 1 <= value['score'] <= 5:
                return None
        elif kind == 'settings_error':
            if value['category'] not in ERRORS or not isinstance(value['invalid_fields'], list):
                return None
            if any(k not in pc.DEFAULTS for k in value['invalid_fields']):
                return None
        if len(json.dumps(value, ensure_ascii=True).encode()) + 1 > MAX_EVENT_BYTES:
            return None
        return value
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None
