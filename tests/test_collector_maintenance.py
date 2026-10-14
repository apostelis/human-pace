import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from remote_test_support import NOW, prompt
from collector.store import CollectorStore, CollectorError
from collector.maintenance import maintain, restore
class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.db=self.root/'events.sqlite3';self.journal=self.root/'external'/'deletions.jsonl';self.key=b'k'*32
        self.store=CollectorStore(self.db,key=self.key,journal=self.journal)
        self.creds=self.store.register('a'*32,'b'*64,now=NOW)
        self.store.ingest(self.creds['ingestion_token'],[prompt()],now=NOW)
    def backup(self):
        path=self.root/'backup.sqlite3'
        with sqlite3.connect(str(self.db)) as source, sqlite3.connect(str(path)) as dest:source.backup(dest)
        return path
    def test_deletion_purge_and_idempotent_status(self):
        self.store.request_delete(self.creds['deletion_token'],now=NOW)
        self.assertEqual(self.store.live_events(start=NOW.date(),end=NOW.date()),[])
        maintain(self.store,self.journal,now=NOW)
        self.assertEqual(self.store.deletion_status(self.creds['deletion_token'])['status'],'completed')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_restore_replays_newer_deletion(self):
        backup=self.backup();self.store.request_delete(self.creds['deletion_token'],now=NOW)
        restore(self.db,backup,self.journal,key=self.key,now=NOW)
        recovered=CollectorStore(self.db,key=self.key,journal=self.journal)
        self.assertEqual(recovered.live_events(start=NOW.date(),end=NOW.date()),[])
        with self.assertRaises(CollectorError):recovered.ingest(self.creds['ingestion_token'],[prompt()],now=NOW)
    def test_stale_journal_refuses_restore_and_disables_reporting(self):
        backup=self.backup();self.store.request_delete(self.creds['deletion_token'],now=NOW)
        self.journal.write_bytes(b'')
        with self.assertRaises(CollectorError):restore(self.db,backup,self.journal,key=self.key,now=NOW)
        with self.assertRaises(CollectorError):self.store.live_events(start=NOW.date(),end=NOW.date())
    def test_journal_failure_never_acknowledges_and_retention(self):
        with patch('collector.maintenance.os.fsync',side_effect=OSError('secret')):
            with self.assertRaises(CollectorError):self.store.request_delete(self.creds['deletion_token'],now=NOW)
        self.assertEqual(self.store.live_events(start=NOW.date(),end=NOW.date()),[])
        self.store.request_delete(self.creds['deletion_token'],now=NOW)
        maintain(self.store,self.journal,now=NOW+timedelta(days=90))
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_restore_remembers_identity_created_after_backup(self):
        backup=self.backup()
        late=self.store.register('c'*32,'d'*64,now=NOW)
        self.store.ingest(late['ingestion_token'],[prompt(identity='c'*32)],now=NOW)
        self.store.request_delete(late['deletion_token'],now=NOW)
        restore(self.db,backup,self.journal,key=self.key,now=NOW)
        recovered=CollectorStore(self.db,key=self.key,journal=self.journal)
        recovered.register('c'*32,'d'*64,now=NOW)
        with self.assertRaises(CollectorError):recovered.ingest(late['ingestion_token'],[prompt(identity='c'*32)],now=NOW)
        self.assertEqual(recovered.deletion_status(late['deletion_token'])['status'],'completed')
    def test_maintenance_does_not_complete_revocation_after_journal_snapshot(self):
        import collector.maintenance as maintenance
        late=self.store.register('c'*32,'d'*64,now=NOW)
        self.store.ingest(late['ingestion_token'],[prompt(identity='c'*32)],now=NOW)
        self.store.request_delete(self.creds['deletion_token'],now=NOW)
        original=maintenance.append_tombstone
        raced=False
        def append_and_race(journal,identity,requested,recovery):
            nonlocal raced
            original(journal,identity,requested,recovery)
            if not raced:
                raced=True
                with patch.object(maintenance,'append_tombstone',side_effect=CollectorError('journal_unavailable')):
                    with self.assertRaises(CollectorError):self.store.request_delete(late['deletion_token'],now=NOW)
        with patch.object(maintenance,'append_tombstone',append_and_race):
            maintain(self.store,self.journal,now=NOW)
        self.assertEqual(self.store.deletion_status(late['deletion_token'])['status'],'pending')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events WHERE identity=?',('c'*32,)).fetchone()[0],1)
        maintain(self.store,self.journal,now=NOW)
        self.assertEqual(self.store.deletion_status(late['deletion_token'])['status'],'completed')
