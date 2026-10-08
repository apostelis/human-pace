import copy
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pace_config as pc
import pace_analytics as a

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

class ContractTest(unittest.TestCase):
    def test_normalization_groups_inactive_settings_but_separates_delivery(self):
        cfg = {**pc.defaults(), 'bionic': False}
        other = {**cfg, 'bionicApproach': 'vowels', 'anchorTrigger': 3}
        self.assertEqual(a.config_identity(cfg)['format_config_id'], a.config_identity(other)['format_config_id'])
        other['driftGuard'] = 0
        self.assertNotEqual(a.config_identity(cfg)['config_id'], a.config_identity(other)['config_id'])
        self.assertEqual(a.config_identity(cfg)['format_config_id'], a.config_identity(other)['format_config_id'])
        self.assertNotEqual(a.config_identity(pc.defaults())['format_config_id'], a.config_identity(cfg)['format_config_id'])

    def test_anchor_only_matters_for_anchor_approach(self):
        cfg = pc.defaults()
        self.assertEqual(a.normalize_config(cfg), a.normalize_config({**cfg, 'anchorTrigger': 3}))
        cfg['bionicApproach'] = 'third+anchor'
        self.assertNotEqual(a.normalize_config(cfg), a.normalize_config({**cfg, 'anchorTrigger': 3}))

    def test_event_roundtrip_and_untrusted_fields_rejected(self):
        event = a.make_event('rating_submitted', now=NOW, integration='claude', source='pace',
                             cfg=pc.defaults(), config_source='commands', score=4)
        self.assertEqual(a.validate_event(event), event)
        for key, value in [('note', 'secret'), ('schema_version', 2), ('score', True), ('score', 6),
                           ('timestamp', 'not-a-date'), ('session_key', '../raw-id'), ('config_id', 'wrong')]:
            bad = {**event, key: value}
            self.assertIsNone(a.validate_event(bad), key)
        bad = copy.deepcopy(event)
        bad['settings']['extra'] = 'secret'
        self.assertIsNone(a.validate_event(bad))
        bad['settings'] = {**pc.defaults(), 'length': True}
        self.assertIsNone(a.validate_event(bad))

    def test_constructor_rejects_unknown_kind_fields_and_naive_time(self):
        for kind, fields in [('surprise', {}), ('command_invoked', {'operation': 'secret', 'outcome': 'success'}),
                             ('rating_submitted', {'score': 5, 'note': 'secret'})]:
            with self.assertRaises(ValueError):
                a.make_event(kind, now=NOW, integration='unknown', source='pace', **fields)
        with self.assertRaises(ValueError):
            a.make_event('command_invoked', now=NOW.replace(tzinfo=None), integration='unknown',
                         source='pace', operation='status', outcome='success')

    def test_changed_fields_derived_from_snapshots(self):
        cfg = {**pc.defaults(), 'length': 300}
        event = a.make_event('config_saved', now=NOW, integration='claude', source='pace',
            cfg=cfg, config_source='commands', previous_settings=pc.defaults())
        self.assertEqual(event['changed_fields'], ['length'])
        self.assertIsNone(a.validate_event({**event, 'changed_fields': ['bionic']}))

import fcntl
import json
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'analytics'
        self.store = a.AnalyticsStore(self.root)

    def event(self, **kw):
        return a.make_event('command_invoked', now=kw.pop('now', NOW), integration='unknown',
                            source='pace', operation='status', outcome='success', **kw)

    def enable(self):
        self.store.configure(enabled=True)

    def events(self):
        return self.store.read(now=NOW + timedelta(seconds=10), days=30)['events']

    def test_disabled_then_enabled_recording(self):
        self.assertFalse(self.store.record([self.event()], now=NOW))
        self.assertFalse(self.root.exists())
        self.enable()
        self.assertTrue(self.store.record([self.event()], now=NOW))
        self.assertEqual(len(self.events()), 1)
        self.store.configure(enabled=False)
        self.assertFalse(self.store.record([self.event()], now=NOW))
        self.assertEqual(len(self.events()), 1)

    def test_truncated_lines_duplicates_and_unknown_schema(self):
        self.enable()
        self.store.record([self.event()], now=NOW)
        path = next(self.root.glob('events-*.jsonl'))
        with path.open('ab') as f:
            f.write(b'{"note":"caf\xc3')
        event = self.event()
        self.assertTrue(self.store.record([event, event], now=NOW))
        with path.open('a') as f:
            f.write(json.dumps({**event, 'schema_version': 20}) + '\n')
        result = self.store.read(now=NOW, days=30)
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(result['diagnostics']['duplicates'], 1)
        self.assertEqual(result['diagnostics']['malformed'], 1)
        self.assertEqual(result['diagnostics']['unsupported'], 1)

    def test_observation_counts_prompts_and_resumes_without_extra_sessions(self):
        self.enable()
        for event in ['SessionStart', 'UserPromptSubmit', 'UserPromptSubmit', 'SessionStart']:
            self.assertTrue(self.store.observe(event=event, cfg=pc.defaults(), config_source='commands',
                session_id='raw-session', now=NOW))
        records = self.events()
        self.assertEqual(sum(e['event'] == 'prompt_observed' for e in records), 2)
        self.assertEqual(len({e['session_key'] for e in records}), 1)
        self.assertNotIn('raw-session', json.dumps(records))
        cfg = {**pc.defaults(), 'bionic': False}
        self.store.observe(event='UserPromptSubmit', cfg=cfg, config_source='commands', session_id='raw-session', now=NOW)
        self.assertEqual(sum(e['event'] == 'config_observed_changed' for e in self.events()), 1)

    def test_unknown_session_and_off_config(self):
        self.enable()
        cfg = {**pc.defaults(), **{k: False for k in pc.SWITCHES}, 'length': 0}
        for sid in [None, '../escape']:
            self.store.observe(event='UserPromptSubmit', cfg=cfg, config_source='commands', session_id=sid, now=NOW)
        self.assertEqual([e['enabled'] for e in self.events()], [False, False])
        self.assertEqual([e['session_key'] for e in self.events()], [None, None])

    def test_busy_store_fails_open_but_controls_raise(self):
        self.enable()
        with (self.root / 'store.lock').open('r+') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertFalse(self.store.record([self.event()], now=NOW))
            with self.assertRaises(a.AnalyticsError):
                self.store.clear(now=NOW)
            with self.assertRaises(a.AnalyticsError):
                self.store.configure(enabled=False)
        self.assertEqual(self.events(), [])

    def test_cap_does_not_advance_observation_state(self):
        self.enable()
        with patch.object(a, 'MAX_DAY_BYTES', 10):
            self.assertFalse(self.store.observe(event='SessionStart', cfg=pc.defaults(),
                config_source='commands', session_id='s1', now=NOW))
        self.assertEqual(self.store.read(now=NOW, days=30)['diagnostics']['capped_days'], ['2026-10-08'])
        self.store.observe(event='UserPromptSubmit', cfg={**pc.defaults(), 'length': 300},
            config_source='commands', session_id='s1', now=NOW)
        self.assertFalse(any(e['event'] == 'config_observed_changed' for e in self.events()))

    def test_retention_excludes_before_pruning_and_clear_preserves_other_files(self):
        self.enable()
        self.store.configure(retention_days=2)
        self.store.record([self.event(now=NOW - timedelta(days=4))], now=NOW - timedelta(days=4))
        self.store.record([self.event()], now=NOW)
        (self.root / 'keep.txt').write_text('keep')
        old_secret = (self.root / 'session.secret').read_bytes()
        self.assertEqual(len(self.events()), 1)
        self.store.maintain(now=NOW)
        self.assertEqual(len(list(self.root.glob('events-*.jsonl'))), 1)
        self.store.clear(now=NOW)
        self.assertTrue(self.store.preferences()['enabled'])
        self.assertEqual(self.events(), [])
        self.assertEqual((self.root / 'keep.txt').read_text(), 'keep')
        self.assertNotEqual(old_secret, (self.root / 'session.secret').read_bytes())

    def test_symlinked_event_file_never_written_or_read(self):
        self.enable()
        target = Path(self.tmp.name) / 'sentinel'
        target.write_text('do not touch')
        (self.root / 'events-2026-10-08.jsonl').symlink_to(target)
        self.assertFalse(self.store.record([self.event()], now=NOW))
        self.assertEqual(self.events(), [])
        self.store.clear(now=NOW)
        self.assertEqual(target.read_text(), 'do not touch')

    def test_invalid_preferences_disable_recording_and_report_error(self):
        self.enable()
        (self.root / 'preferences.json').write_text('{bad')
        self.assertFalse(self.store.record([self.event()], now=NOW))
        with self.assertRaises(a.AnalyticsError):
            self.store.preferences()

    def test_overlong_line_is_skipped_and_later_valid_record_retained(self):
        self.enable()
        self.store.record([self.event()], now=NOW)
        path = next(self.root.glob('events-*.jsonl'))
        with path.open('ab') as f:
            f.write(b'x' * (a.MAX_EVENT_BYTES * 3) + b'\n')
        self.store.record([self.event()], now=NOW)
        self.assertEqual(len(self.events()), 2)

    def test_lost_state_creates_baseline_not_change(self):
        self.enable()
        self.store.observe(event='UserPromptSubmit', cfg=pc.defaults(), config_source='commands', session_id='s1', now=NOW)
        for p in self.root.glob('state-*.json'):
            p.write_text('{}')
        self.store.observe(event='UserPromptSubmit', cfg={**pc.defaults(), 'length': 300},
            config_source='commands', session_id='s1', now=NOW)
        self.assertFalse(any(e['event'] == 'config_observed_changed' for e in self.events()))

    def test_concurrent_process_appends_preserve_every_successful_record(self):
        import subprocess
        self.enable()
        code = '''import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
import pace_analytics as a
s = a.AnalyticsStore(Path(sys.argv[2]))
n = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
e = a.make_event('command_invoked', now=n, integration='unknown', source='pace', operation='status', outcome='success')
print(int(s.record([e], now=n)))
'''
        children = [subprocess.Popen([sys.executable, '-c', code, str(Path(a.__file__).parent), str(self.root)],
                    stdout=subprocess.PIPE, text=True) for _ in range(8)]
        outcomes = [int(child.communicate()[0]) for child in children]
        self.assertGreater(sum(outcomes), 0)
        self.assertEqual(len(self.events()), sum(outcomes))
