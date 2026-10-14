"""Shared strict remote contract. No filesystem or network side effects."""
import json
import re
from datetime import date
import pace_analytics as local

MAX_EVENT_BYTES = 16 * 1024
MAX_BATCH_BYTES = 256 * 1024
MAX_BATCH_EVENTS = 100
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
class ContractError(ValueError):
    def __init__(self, reason='invalid_event'):
        self.reason = reason
        super().__init__(reason)

def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError):
        raise ContractError('invalid_json') from None

def strict_json(data, *, max_bytes):
    if not isinstance(data, bytes) or len(data) > max_bytes:
        raise ContractError('oversized')
    def pairs(items):
        obj = {}
        for k, v in items:
            if k in obj: raise ContractError('duplicate_key')
            obj[k] = v
        return obj
    def invalid(value): raise ContractError('invalid_number')
    try:
        obj = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
        def depth(v, n=0):
            if n > 16: raise ContractError('nested_json')
            if isinstance(v, dict):
                for x in v.values(): depth(x, n + 1)
            elif isinstance(v, list):
                for x in v: depth(x, n + 1)
        depth(obj)
        return obj
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError('invalid_json') from None

def validate_event(value):
    try:
        if not isinstance(value, dict): raise ContractError()
        e = dict(value)
        if not HEX32.fullmatch(e.pop('installation_id')): raise ContractError()
        day = e.pop('day')
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day: raise ContractError()
        if len(e.get('plugin_version', '')) > 64: raise ContractError()
        if e.get('event') == 'prompt_observed':
            sequence = e.pop('prompt_sequence')
            if e.get('session_key') is None:
                if sequence is not None: raise ContractError()
            elif type(sequence) is not int or not 1 <= sequence <= 2**63 - 1:
                raise ContractError()
        if 'timestamp' in e: raise ContractError()
        e['timestamp'] = day + 'T00:00:00+00:00'
        if local.validate_event(e) is None or len(canonical(value)) > MAX_EVENT_BYTES:
            raise ContractError()
        return dict(value)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ContractError() from None

def encode_event(event):
    return canonical(validate_event(event))

def encode_batch(events):
    if not isinstance(events, list) or len(events) > MAX_BATCH_EVENTS: raise ContractError('oversized')
    result = canonical({'schema_version':1, 'events':[validate_event(e) for e in events]})
    if len(result) > MAX_BATCH_BYTES: raise ContractError('oversized')
    return result
