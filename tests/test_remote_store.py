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
    def test_byte_cap_evicts_oldest_and_invalid_input_never_evicts(self):
        self.enable();self.enqueue(operation='status');self.enqueue(operation='toggle')
        with self.local._lock(),self.store._db() as db:
            sizes=[n for n, in db.execute('SELECT length(body) FROM events ORDER BY ordinal')]
        with patch.object(r,'MAX_QUEUE_BYTES',sum(sizes)):
            self.enqueue(operation='rate')
            data=json.loads(self.store.preview(now=NOW))['events']
            self.assertEqual([e['operation'] for e in data],['toggle','rate'])
            e=analytics.make_event('command_invoked',now=NOW,integration='unknown',source='pace',operation='status',outcome='success')
            with self.local._lock():self.store.enqueue_locked([{**e,'note':'secret'}],now=NOW)
            self.assertEqual(self.store.status(now=NOW)['queued_count'],2)
    def test_expired_session_state_gets_new_remote_session_key(self):
        self.enable()
        def enqueue(when):
            e=analytics.make_event('prompt_observed',now=when,integration='claude',source='hook',session_key='a'*64,cfg=pc.defaults(),config_source='commands',enabled=True)
            with self.local._lock():self.store.enqueue_locked([e],now=when)
            return json.loads(self.store.preview(now=when))['events'][-1]
        first=enqueue(NOW);second=enqueue(NOW+timedelta(days=8))
        self.assertNotEqual(first['session_key'],second['session_key'])
        self.assertEqual(second['prompt_sequence'],1)
    def test_each_identity_remembers_its_collection_destination(self):
        self.enable();self.store.disable(now=NOW)
        other={**RELEASE,'endpoint':'https://new.example.test'}
        self.store.enable(now=NOW,local_enabled=True,release=other)
        targets=self.store.deletion_targets(now=NOW)
        self.assertEqual([x['recipient']['endpoint'] for x in targets],[RELEASE['endpoint'],other['endpoint']])
    def test_overflow_incoming_batch_retains_newest_suffix(self):
        self.enable()
        events=[analytics.make_event('command_invoked',now=NOW,integration='unknown',source='pace',operation=operation,outcome='success') for operation in ('status','toggle','rate')]
        with patch.object(r,'MAX_QUEUE_EVENTS',2),self.local._lock():self.store.enqueue_locked(events,now=NOW)
        self.assertEqual([e['operation'] for e in json.loads(self.store.preview(now=NOW))['events']],['toggle','rate'])
    def test_failed_enable_never_leaves_sharing_active(self):
        from contextlib import contextmanager
        @contextmanager
        def unavailable():
            raise r.RemoteError('Queue unavailable')
            yield
        with patch.object(self.store,'_db',unavailable):
            with self.assertRaises(r.RemoteError):self.enable()
        self.assertFalse(self.store.status(now=NOW)['enabled'])
