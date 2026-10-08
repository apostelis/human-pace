"""Local-only usage events. Recording defaults to on; explicit opt-out persists."""
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

# Storage is deliberately separate from config reads and rule delivery state.
import hmac
import os
import secrets
import stat
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from typing import List, Mapping
try:
    import fcntl
except ImportError:
    fcntl = None


class AnalyticsError(Exception):
    """A bounded, user-facing local analytics failure."""


def _open(path: Path, flags: int):
    fd = os.open(str(path), flags | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0), 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise AnalyticsError('Analytics requires regular local files.')
    return fd


def _small_read(path: Path, limit: int = MAX_EVENT_BYTES) -> bytes:
    fd = _open(path, os.O_RDONLY)
    with os.fdopen(fd, 'rb') as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise AnalyticsError('Analytics metadata exceeds its size limit.')
    return data


def _days(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 365:
        raise AnalyticsError('Days must be an integer from 1 to 365.')
    return value


class AnalyticsStore:
    def __init__(self, root: Path):
        try:
            self.root = Path(root).expanduser()
        except (RuntimeError, TypeError, ValueError):
            raise AnalyticsError('Invalid local analytics directory.') from None

    def _check_root(self):
        if self.root.is_symlink():
            raise AnalyticsError('The analytics directory must not be a symbolic link.')

    @contextmanager
    def _lock(self):
        self._check_root()
        if fcntl is None:
            raise AnalyticsError('Local analytics locking is unavailable on this platform.')
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = _open(self.root / 'store.lock', os.O_CREAT | os.O_RDWR)
            with os.fdopen(fd, 'r+b') as lock:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise AnalyticsError('Analytics is busy; try again.') from None
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except OSError:
            raise AnalyticsError('Could not access local analytics storage.') from None

    def _atomic(self, name: str, data: bytes):
        path = self.root / name
        if path.is_symlink():
            raise AnalyticsError('Analytics metadata must not be a symbolic link.')
        fd, tmp = tempfile.mkstemp(prefix='.analytics-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def preferences(self) -> dict:
        self._check_root()
        try:
            prefs = json.loads(_small_read(self.root / 'preferences.json'))
        except FileNotFoundError:
            return {'enabled': True, 'retention_days': 90}
        except (OSError, ValueError, TypeError, RecursionError):
            raise AnalyticsError('Invalid or unreadable analytics preferences.') from None
        if (not isinstance(prefs, dict) or set(prefs) != {'enabled', 'retention_days'}
                or type(prefs['enabled']) is not bool):
            raise AnalyticsError('Invalid analytics preferences.')
        _days(prefs['retention_days'])
        return prefs

    def _secret(self) -> bytes:
        try:
            secret = _small_read(self.root / 'session.secret', 64)
            if len(secret) == 64 and HEX64.fullmatch(secret.decode('ascii')):
                return bytes.fromhex(secret.decode('ascii'))
        except (OSError, ValueError, UnicodeError, AnalyticsError):
            pass
        # Missing/corrupt secret starts a new correlation epoch, not fake transitions.
        for path in self.root.glob('state-*.json'):
            if re.fullmatch(r'state-[0-9a-f]{64}\.json', path.name) and not path.is_symlink():
                path.unlink()
        secret = secrets.token_bytes(32)
        self._atomic('session.secret', secret.hex().encode())
        return secret

    def configure(self, *, enabled: Optional[bool] = None, retention_days: Optional[int] = None) -> dict:
        if enabled is not None and type(enabled) is not bool:
            raise AnalyticsError('Enabled must be a boolean.')
        if retention_days is not None:
            _days(retention_days)
        with self._lock():
            prefs = self.preferences()
            if enabled is not None:
                prefs['enabled'] = enabled
            if retention_days is not None:
                prefs['retention_days'] = retention_days
            if prefs['enabled']:
                self._secret()
            self._atomic('preferences.json', json.dumps(prefs).encode())
            return prefs

    def _append(self, events: List[dict], now: datetime) -> bool:
        if not events:
            return True
        marker = self.root / ('capped-' + now.date().isoformat())
        if marker.exists() or marker.is_symlink():
            return False
        if any(validate_event(e) is None or datetime.fromisoformat(e['timestamp']).date() != now.date()
               for e in events):
            return False
        data = b''.join((json.dumps(e, ensure_ascii=True, separators=(',', ':')) + '\n').encode() for e in events)
        path = self.root / ('events-' + now.date().isoformat() + '.jsonl')
        fd = _open(path, os.O_CREAT | os.O_RDWR | os.O_APPEND)
        with os.fdopen(fd, 'a+b') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            prefix = b''
            if size:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b'\n':
                    prefix = b'\n'
            if size + len(prefix) + len(data) > MAX_DAY_BYTES:
                self._atomic('capped-' + now.date().isoformat(), b'1')
                return False
            f.write(prefix + data)
        return True

    def record(self, events: List[dict], *, now: datetime) -> bool:
        try:
            now = utc(now)
            if not self.preferences()['enabled']:
                return False
            with self._lock():
                return self.preferences()['enabled'] and self._append(events, now)
        except Exception:
            return False

    def observe(self, *, event: str, cfg: dict, config_source: str,
                session_id: object, now: datetime) -> bool:
        try:
            now = utc(now)
            if event not in ('SessionStart', 'UserPromptSubmit') or not self.preferences()['enabled']:
                return False
            with self._lock():
                if not self.preferences()['enabled']:
                    return False
                key, previous = None, None
                if isinstance(session_id, str) and re.fullmatch(r'[\w-]{1,128}', session_id):
                    key = hmac.new(self._secret(), session_id.encode(), hashlib.sha256).hexdigest()
                    try:
                        state = json.loads(_small_read(self.root / ('state-' + key + '.json')))
                        if valid_config(state.get('settings')) and utc(datetime.fromisoformat(state['timestamp'])) >= now - timedelta(days=self.preferences()['retention_days']):
                            previous = state['settings']
                    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, AnalyticsError):
                        pass
                common = dict(now=now, integration='claude', source='hook', session_key=key,
                              cfg=cfg, config_source=config_source)
                events = []
                if key and (previous is None or event == 'SessionStart'):
                    events.append(make_event('session_observed', **common))
                if previous is not None and previous != cfg:
                    events.append(make_event('config_observed_changed', previous_settings=previous, **common))
                if event == 'UserPromptSubmit':
                    events.append(make_event('prompt_observed', enabled=any(cfg[k] for k in pc.SWITCHES) or cfg['length'] > 0, **common))
                if not self._append(events, now):
                    return False
                if key:
                    self._atomic('state-' + key + '.json', json.dumps({'settings': cfg, 'timestamp': now.isoformat()}).encode())
                return True
        except Exception:
            return False

    def _maintain(self, now: datetime):
        cutoff = now - timedelta(days=self.preferences()['retention_days'])
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            match = re.fullmatch(r'(?:events-(\d{4}-\d{2}-\d{2})\.jsonl|capped-(\d{4}-\d{2}-\d{2}))', path.name)
            if match:
                try:
                    expired = datetime.fromisoformat(next(g for g in match.groups() if g)).date() < cutoff.date()
                except ValueError:
                    continue
                if expired:
                    path.unlink()
            elif re.fullmatch(r'state-[0-9a-f]{64}\.json', path.name):
                try:
                    state = json.loads(_small_read(path))
                    expired = utc(datetime.fromisoformat(state['timestamp'])) < cutoff
                except (ValueError, KeyError, TypeError, RecursionError, AnalyticsError):
                    expired = True
                if expired:
                    path.unlink()

    def maintain(self, *, now: datetime) -> None:
        if not self.root.exists():
            return
        with self._lock():
            self._maintain(utc(now))

    def clear(self, *, now: datetime) -> None:
        utc(now)
        with self._lock():
            for path in self.root.iterdir():
                if (re.fullmatch(r'(?:events-\d{4}-\d{2}-\d{2}\.jsonl|state-[0-9a-f]{64}\.json|capped-\d{4}-\d{2}-\d{2})', path.name)
                        and not path.is_symlink() and path.is_file()):
                    path.unlink()
            self._atomic('session.secret', secrets.token_hex(32).encode())

    def read(self, *, now: datetime, days: int) -> dict:
        now, days = utc(now), _days(days)
        prefs = self.preferences()
        cutoff = now - timedelta(days=min(days, prefs['retention_days']))
        diagnostics = {'malformed': 0, 'unsupported': 0, 'duplicates': 0, 'capped_days': [],
                       'first': None, 'last': None, 'enabled': prefs['enabled'],
                       'retention_days': prefs['retention_days'], 'requested_days': days,
                       'window_start': cutoff.isoformat(), 'window_end': now.isoformat()}
        if not self.root.exists():
            return {'events': [], 'diagnostics': diagnostics}
        events, seen = [], set()
        with self._lock():
            for path in sorted(self.root.iterdir()):
                if path.is_symlink() or not path.is_file():
                    continue
                marker = re.fullmatch(r'capped-(\d{4}-\d{2}-\d{2})', path.name)
                if marker and cutoff.date().isoformat() <= marker[1] <= now.date().isoformat():
                    diagnostics['capped_days'].append(marker[1])
                match = re.fullmatch(r'events-(\d{4}-\d{2}-\d{2})\.jsonl', path.name)
                if not match or not cutoff.date().isoformat() <= match[1] <= now.date().isoformat():
                    continue
                fd = _open(path, os.O_RDONLY)
                with os.fdopen(fd, 'rb') as f:
                    while True:
                        line = f.readline(MAX_EVENT_BYTES + 1)
                        if not line:
                            break
                        if len(line) > MAX_EVENT_BYTES:
                            while line and not line.endswith(b'\n'):
                                line = f.readline(MAX_EVENT_BYTES + 1)
                            diagnostics['malformed'] += 1
                            continue
                        try:
                            value = json.loads(line)
                        except (ValueError, UnicodeError, RecursionError):
                            diagnostics['malformed'] += 1
                            continue
                        if isinstance(value, dict) and value.get('schema_version') != 1:
                            diagnostics['unsupported'] += 1
                            continue
                        value = validate_event(value)
                        if value is None:
                            diagnostics['malformed'] += 1
                            continue
                        if not cutoff <= datetime.fromisoformat(value['timestamp']) <= now:
                            continue
                        if value['event_id'] in seen:
                            diagnostics['duplicates'] += 1
                            continue
                        seen.add(value['event_id'])
                        events.append(value)
        events.sort(key=lambda e: e['timestamp'])
        if events:
            diagnostics['first'], diagnostics['last'] = events[0]['timestamp'], events[-1]['timestamp']
        return {'events': events, 'diagnostics': diagnostics}


def default_store(env: Optional[Mapping[str, str]] = None) -> AnalyticsStore:
    env = os.environ if env is None else env
    return AnalyticsStore(Path(env.get('HUMAN_PACE_ANALYTICS_DIR', '~/.claude/human-pace-analytics')))


def record_action(operation: str, outcome: str, *, source: str, cfg: Optional[dict],
                  config_source: str, now: datetime, events: Optional[List[dict]] = None) -> None:
    """Record an executed action and its effects without changing its result."""
    try:
        store = default_store()
        if not store.preferences()['enabled']:
            return
        common = dict(now=now, integration='unknown', source=source, cfg=cfg,
                      config_source=config_source)
        batch = [make_event('command_invoked', operation=operation, outcome=outcome, **common)]
        for descriptor in events or []:
            fields = dict(descriptor)
            kind = fields.pop('event')
            current = {**common, 'cfg': fields.pop('cfg', cfg)}
            batch.append(make_event(kind, **current, **fields))
        store.record(batch, now=now)
    except Exception:
        pass


def recording_notice() -> str:
    """Read-only disclosure for status/settings; storage errors cannot break either."""
    try:
        enabled = default_store().preferences()['enabled']
    except Exception:
        return "Local analytics status unavailable. Recording is on by default; nothing is uploaded. Check /pace analytics."
    if enabled:
        return ("Local analytics: on (on by default). Usage, settings, and numeric ratings stay on this machine; "
                "nothing is uploaded. Prompt content and rating notes are excluded. Disable: /pace analytics off.")
    return ("Local analytics: off. Nothing is uploaded. Enable: /pace analytics on. "
            "Inspect or clear retained history with /pace analytics.")
