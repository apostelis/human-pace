import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from remote_test_support import NOW, prompt
from collector.store import CollectorStore, CollectorError
class CollectorTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.db=Path(tmp.name)/'events.sqlite3'
        self.key=b'k'*32;self.store=CollectorStore(self.db,key=self.key)
        self.identity='a'*32;self.creds=self.store.register(self.identity,'b'*64,now=NOW)
    def test_registration_recoverable_and_collision_refused(self):
        reopened=CollectorStore(self.db,key=self.key)
        self.assertEqual(self.creds,reopened.register(self.identity,'b'*64,now=NOW))
        with self.assertRaises(CollectorError):reopened.register(self.identity,'c'*64,now=NOW)
    def test_durable_duplicate_and_conflicting_id(self):
        event=prompt();token=self.creds['ingestion_token']
        self.assertEqual(self.store.ingest(token,[event],now=NOW)['accepted'],[event['event_id']])
        self.assertEqual(CollectorStore(self.db,key=self.key).ingest(token,[event],now=NOW)['duplicate'],[event['event_id']])
        bad={**event,'source':'pace'}
        self.assertEqual(self.store.ingest(token,[bad],now=NOW)['rejected'][0]['reason'],'conflicting_id')
        self.assertEqual(len(self.store.live_events(start=NOW.date(),end=NOW.date())),1)
    def test_auth_roles_identity_and_sequence_conflict(self):
        with self.assertRaises(CollectorError):self.store.ingest(self.creds['deletion_token'],[prompt()],now=NOW)
        self.assertEqual(self.store.ingest(self.creds['ingestion_token'],[prompt(identity='c'*32)],now=NOW)['rejected'][0]['reason'],'identity_mismatch')
        self.store.ingest(self.creds['ingestion_token'],[prompt()],now=NOW)
        self.assertEqual(self.store.ingest(self.creds['ingestion_token'],[prompt()],now=NOW)['rejected'][0]['reason'],'sequence_conflict')
    def test_revocation_immediately_excludes_and_retains_recovery(self):
        self.store.ingest(self.creds['ingestion_token'],[prompt()],now=NOW)
        receipt=self.store.request_delete(self.creds['deletion_token'],now=NOW)
        self.assertEqual(receipt['status'],'pending')
        self.assertEqual(self.store.live_events(start=NOW.date(),end=NOW.date()),[])
        with self.assertRaises(CollectorError):self.store.ingest(self.creds['ingestion_token'],[prompt()],now=NOW)
        # Recovery returns credentials without ever reactivating a revoked identity.
        self.assertEqual(self.creds,self.store.register(self.identity,'b'*64,now=NOW))
    def test_future_expired_and_bad_fields_rejected(self):
        for event,reason in [(prompt(day='2026-10-09'),'future'),(prompt(day='2026-09-30'),'expired'),({**prompt(),'note':'secret'},'invalid_event')]:
            receipt=self.store.ingest(self.creds['ingestion_token'],[event],now=NOW)
            self.assertEqual(receipt['rejected'][0]['reason'],reason)
    def test_duplicate_delivery_still_acknowledged_at_daily_cap(self):
        from unittest.mock import patch
        event=prompt()
        with patch('collector.store.MAX_DAILY_EVENTS',1):
            self.store.ingest(self.creds['ingestion_token'],[event],now=NOW)
            self.assertEqual(self.store.ingest(self.creds['ingestion_token'],[event],now=NOW)['duplicate'],[event['event_id']])
            with self.assertRaises(CollectorError):self.store.ingest(self.creds['ingestion_token'],[prompt(sequence=2)],now=NOW)
    def test_registration_storage_cap_preserves_existing_recovery(self):
        from unittest.mock import patch
        with patch('collector.store.MAX_INSTALLATIONS',1):
            with self.assertRaises(CollectorError):self.store.register('c'*32,'d'*64,now=NOW)
            self.assertEqual(self.creds,self.store.register('a'*32,'b'*64,now=NOW))
