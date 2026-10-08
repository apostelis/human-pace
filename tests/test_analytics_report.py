import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pace_config as pc
import pace_analytics as a
import pace_analytics_report as r
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

class ReportTest(unittest.TestCase):
    def prompt(self, cfg, i=0, key='a' * 64, now=NOW):
        return a.make_event('prompt_observed', now=now + timedelta(seconds=i), integration='claude',
            source='hook', session_key=key, cfg=cfg, config_source='commands',
            enabled=any(cfg[k] for k in pc.SWITCHES) or cfg['length'] > 0)

    def test_transitions_and_shares_have_hand_checked_denominators(self):
        ca, cb = pc.defaults(), {**pc.defaults(), 'bionic': False}
        events = [self.prompt(cfg, i) for i, cfg in enumerate([ca, ca, cb, cb, ca])]
        summary = r.summarize(events, now=NOW + timedelta(seconds=10), days=30)
        aid, bid = a.config_identity(ca)['format_config_id'], a.config_identity(cb)['format_config_id']
        self.assertEqual(summary['transitions'], {(aid, bid): 1, (bid, aid): 1})
        self.assertEqual(summary['configurations'][aid]['share'], 3/5)
        self.assertEqual(summary['configurations'][bid]['share'], 2/5)
        self.assertEqual(summary['active_sessions'], 1)
        self.assertEqual(summary['configurations'][aid]['sessions'], 1)
        self.assertEqual(summary['configurations'][bid]['sessions'], 1)

    def test_off_unknown_sessions_and_empty_denominators(self):
        off = {**pc.defaults(), **{k: False for k in pc.SWITCHES}, 'length': 0}
        summary = r.summarize([self.prompt(off, key=None), self.prompt(pc.defaults(), key=None)], now=NOW, days=30)
        self.assertEqual(summary['prompts'], 2)
        self.assertEqual(summary['active_prompts'], 1)
        self.assertEqual(summary['active_sessions'], 0)
        self.assertEqual(summary['unassigned_prompts'], 2)
        self.assertEqual(summary['transitions'], {})
        self.assertIsNone(summary['changes_per_active_session'])
        empty = r.summarize([], now=NOW, days=30)
        self.assertIn('on by default', r.render_usage(empty, {'enabled': True}))
        self.assertIn('analytics on', r.render_usage(empty, {'enabled': False}))

    def test_time_window_boundary_and_days_are_utc(self):
        events = [self.prompt(pc.defaults(), now=NOW - timedelta(days=30)),
                  self.prompt(pc.defaults(), now=NOW - timedelta(days=30, seconds=1)),
                  self.prompt(pc.defaults(), now=NOW + timedelta(seconds=1)),
                  self.prompt(pc.defaults(), now=NOW)]
        summary = r.summarize(events, now=NOW, days=30)
        self.assertEqual(summary['prompts'], 2)
        self.assertEqual(next(iter(summary['configurations'].values()))['days'], 2)

    def test_ratings_do_not_duplicate_and_sparse_groups_stay_visible(self):
        events = [a.make_event('rating_submitted', now=NOW, integration='unknown', source='pace',
                    cfg=pc.defaults(), config_source='commands', score=score) for score in [2, 4]]
        summary = r.summarize(events + [events[0]], now=NOW, days=30)
        row = next(iter(summary['ratings'].values()))
        self.assertEqual(row['mean'], 3)
        self.assertEqual(row['count'], 2)
        self.assertEqual(row['distribution'], {1: 0, 2: 1, 3: 0, 4: 1, 5: 0})
        text = r.render_compare(summary, {})
        self.assertIn('sparse', text.lower())
        self.assertIn('0 prompts', text)

    def test_changes_and_errors_are_not_added_to_save_count(self):
        cfg = {**pc.defaults(), 'length': 300}
        common = dict(now=NOW, integration='claude', source='hook', cfg=cfg, config_source='commands', session_key='a'*64)
        events = [self.prompt(cfg), a.make_event('config_saved', previous_settings=pc.defaults(), **common),
                  a.make_event('config_observed_changed', previous_settings=pc.defaults(), **common),
                  a.make_event('settings_error', category='invalid_settings', invalid_fields=['length'], **common)]
        summary = r.summarize(events, now=NOW, days=30)
        self.assertEqual(summary['editing']['saves'], 1)
        self.assertEqual(summary['changes_per_active_session'], 1)
        self.assertEqual(sum(summary['errors'].values()), 1)

    def test_associations_exclude_inactive_bionic_dimensions(self):
        events = [self.prompt(pc.defaults()), self.prompt({**pc.defaults(), 'chunks': False}),
                  self.prompt({**pc.defaults(), 'bionic': False})]
        summary = r.summarize(events, now=NOW, days=30)
        row = summary['associations'][('bionicApproach', 'third', 'chunks')]
        self.assertEqual(row, {'numerator': 1, 'denominator': 2})
        self.assertIn('1/2', r.render_compare(summary, {}))
