import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from remote_test_support import NOW, RELEASE, prompt, analytics, pc
import pace_remote_store as r
class QueueTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)/'analytics'; self.local = analytics.AnalyticsStore(self.root)
        self.store = r.RemoteStore(self.root)
        p=patch.object(r,'RELEASE',RELEASE);p.start();self.addCleanup(p.stop)
    def enable(self): return self.store.enable(now=NOW,local_enabled=True,release=RELEASE)
    def enqueue(self, n=1, operation='status'):
        for _ in range(n):
            e=analytics.make_event('command_invoked',now=NOW,integration='unknown',source='pace',operation=operation,outcome='success')
            with self.local._lock(): self.store.enqueue_locked([e],now=NOW)
    def test_default_off_and_required_destination(self):
        self.assertFalse(self.store.status(now=NOW)['enabled']);self.assertFalse(self.root.exists())
        with self.assertRaises(r.RemoteError):self.store.enable(now=NOW,local_enabled=False,release=RELEASE)
        with self.assertRaises(r.RemoteError):self.store.enable(now=NOW,local_enabled=True,release={})
    def test_rotation_and_deletion_ledger(self):
        first=self.enable()['identity'];self.assertEqual(first,self.enable()['identity'])
        self.enqueue();self.store.disable(now=NOW)
        self.assertEqual(self.store.status(now=NOW)['queued_count'],0)
        second=self.enable()['identity'];self.assertNotEqual(first,second)
    def test_evict_oldest_and_ignore_inflight_receipt(self):
        self.enable()
        with patch.object(r,'MAX_QUEUE_EVENTS',2):
            self.enqueue(operation='status');old=self.store.claim(now=NOW)
            self.enqueue(operation='toggle');self.enqueue(operation='rate')
            self.assertEqual(self.store.status(now=NOW)['evicted_count'],1)
            self.store.finish(old,{'accepted':old['event_ids'],'duplicate':[],'rejected':[]},now=NOW)
            data=json.loads(self.store.preview(now=NOW))
            self.assertEqual([e['operation'] for e in data['events']],['toggle','rate'])
    def test_old_generation_receipt_and_expiry(self):
        self.enable();self.enqueue();old=self.store.claim(now=NOW)
        self.store.disable(now=NOW);self.enable();self.enqueue()
        self.store.finish(old,{'accepted':old['event_ids'],'duplicate':[],'rejected':[]},now=NOW)
        self.assertEqual(self.store.status(now=NOW)['queued_count'],1)
        self.assertFalse(self.store.current(old))
        self.assertEqual(json.loads(self.store.preview(now=NOW+timedelta(days=8)))['events'],[])
    def test_invitation_dismissal_and_clear(self):
        n=self.store.invitation(surface='session',now=NOW,local_enabled=True,release=RELEASE)
        self.assertTrue(n['visible'])
        self.assertFalse(self.store.invitation(surface='session',now=NOW,local_enabled=True,release=RELEASE)['visible'])
        self.store.choose_invitation('never',now=NOW,local_enabled=True,release=RELEASE)
        with self.local._lock(): self.store.clear_pending_locked(now=NOW)
        self.assertFalse(self.store.invitation(surface='settings',now=NOW,local_enabled=True,release=RELEASE)['visible'])
        self.assertFalse(self.store.status(now=NOW)['enabled'])
    def test_corrupt_prefs_and_symlink_fail_closed(self):
        self.enable();(self.root/'remote'/'preferences.json').write_text('{}')
        with self.assertRaises(r.RemoteError):self.store.status(now=NOW)
    def test_clock_rollback_does_not_queue(self):
        self.enable()
        e=analytics.make_event('command_invoked',now=NOW-timedelta(seconds=1),integration='unknown',source='pace',operation='status',outcome='success')
        with self.local._lock(): self.assertFalse(self.store.enqueue_locked([e],now=NOW-timedelta(seconds=1)))
        self.assertEqual(self.store.status(now=NOW)['queued_count'],0)
