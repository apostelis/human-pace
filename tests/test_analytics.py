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
