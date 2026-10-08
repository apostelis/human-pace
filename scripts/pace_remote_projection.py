"""Allowlisted projection; local history is never read here."""
import hashlib
import hmac
import uuid
from datetime import datetime
import pace_analytics as local
from pace_remote_contract import ContractError, validate_event

def project(event, *, identity, secret, sequence, previous):
    if local.validate_event(event) is None: raise ContractError()
    kind = event['event']
    if kind == 'config_observed_changed' and previous is None: return None
    result = {k:event[k] for k in local.BASE - {'timestamp', 'event_id', 'session_key'}}
    result.update(event_id=uuid.uuid4().hex, installation_id=identity,
                  day=datetime.fromisoformat(event['timestamp']).date().isoformat(),
                  session_key=hmac.new(secret, event['session_key'].encode(), hashlib.sha256).hexdigest() if event['session_key'] else None)
    if 'settings' in event: result.update({k:event[k] for k in local.CONFIG})
    result.update({k:event[k] for k in local.FIELDS[kind]})
    if kind == 'config_observed_changed':
        changed = sorted(k for k in local.pc.DEFAULTS if previous[k] != event['settings'][k])
        if not changed: return None
        result.update(previous_settings=previous, changed_fields=changed)
    if kind == 'prompt_observed': result['prompt_sequence'] = sequence if result['session_key'] else None
    return validate_event(result)
