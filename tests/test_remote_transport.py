import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from remote_test_support import NOW, RELEASE, analytics
import pace_remote_store as r
import pace_remote_transport as t
class FakeTransport:
    def __init__(self):self.calls=[];self.error=None
    def request(self,method,path,*,body,credential,deadline):
        data=json.loads(body) if body else {};self.calls.append((path,body,credential))
        if self.error:raise self.error
        if path=='/v1/registrations':return {'installation_id':data['installation_id'],'ingestion_token':'c'*64,'deletion_token':'d'*64}
        if path=='/v1/events':return {'accepted':[e['event_id'] for e in data['events']],'duplicate':[],'rejected':[]}
        return {'installation_id':self.identity,'status':'completed'}
class TransportTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'a'
        self.local=analytics.AnalyticsStore(self.root);self.store=r.RemoteStore(self.root)
        p=patch.object(r,'RELEASE',RELEASE);p.start();self.addCleanup(p.stop)
        self.identity=self.store.enable(now=NOW,local_enabled=True,release=RELEASE)['identity']
        e=analytics.make_event('command_invoked',now=NOW,integration='unknown',source='pace',operation='status',outcome='success')
        with self.local._lock():self.store.enqueue_locked([e],now=NOW)
        self.fake=FakeTransport()
    def test_retry_same_ids_and_persist_credentials(self):
        # Register, then simulate lost ingestion reply; server commit is covered by end-to-end fixture.
        creds=self.fake.request('POST','/v1/registrations',body=json.dumps({'installation_id':self.identity}).encode(),credential=None,deadline=0)
        self.store.save_credentials(self.identity,creds,generation=1)
        self.fake.error=ConnectionError()
        self.assertEqual(t.upload(self.store,self.fake,now=NOW)['state'],'retry')
        with self.assertRaises(r.RemoteError):t.upload(self.store,self.fake,now=NOW)
        self.fake.error=None
        self.assertEqual(t.upload(self.store,self.fake,now=NOW+timedelta(minutes=2))['remaining'],0)
        bodies=[body for path,body,_ in self.fake.calls if path=='/v1/events']
        self.assertEqual(bodies[0],bodies[1])
    def test_registration_and_partial_ack(self):
        self.assertEqual(t.upload(self.store,self.fake,now=NOW)['accepted'],1)
        self.assertEqual(self.store.status(now=NOW)['queued_count'],0)
    def test_malformed_receipt_acknowledges_nothing(self):
        original=self.fake.request
        def malformed(method,path,**kw):
            if path=='/v1/events':return {'accepted':['f'*32],'duplicate':[],'rejected':[]}
            return original(method,path,**kw)
        self.fake.request=malformed
        self.assertEqual(t.upload(self.store,self.fake,now=NOW)['state'],'retry')
        self.assertEqual(self.store.status(now=NOW)['queued_count'],1)
    def test_delete_all_and_complete_only_after_receipt(self):
        t.upload(self.store,self.fake,now=NOW);self.fake.identity=self.identity
        result=t.delete_all(self.store,self.fake,now=NOW)
        self.assertEqual(result['completed'],1);self.assertEqual(self.store.status(now=NOW)['prior_identities'],0)
    def test_auth_suspends_and_retry_after_bounded(self):
        self.fake.error=t.TransportError('credentials',status=401)
        self.assertEqual(t.upload(self.store,self.fake,now=NOW)['state'],'suspended')
        self.assertTrue(self.store.status(now=NOW)['suspended'])
        self.assertEqual(t.retry_seconds(0,'999999999',NOW),86400)
        self.assertEqual(t.retry_seconds(0,'-3',NOW),60)
    def test_reject_non_https_and_endpoint_credentials(self):
        for url in ('http://collector.test','https://user:pass@collector.test','https://collector.test/?x=1'):
            with self.assertRaises(r.RemoteError):t.HttpsTransport(url)
    def test_https_redirect_bad_tls_and_slow_response(self):
        import ssl
        import pace_remote_contract as c
        class Socket:
            def settimeout(self,value):self.timeout=value
        class Response:
            status=200;fp=None
            def getheader(self,name,default=None):return default
            def read1(self,n):clock[0]=20;return b'{}'
        class Connection:
            def __init__(self,*args,**kw):self.sock=Socket()
            def connect(self):pass
            def request(self,*args,**kw):pass
            def getresponse(self):return response
            def close(self):pass
        clock=[0];response=Response()
        with patch.object(t.http.client,'HTTPSConnection',Connection):
            transport=t.HttpsTransport(RELEASE['endpoint'],clock=lambda:clock[0])
            with self.assertRaises(t.TransportError):transport._request('POST','/v1/events',body=b'{}',credential=None,deadline=10)
            clock[0]=0;response.status=302
            with self.assertRaises(t.TransportError) as caught:transport._request('POST','/v1/events',body=b'{}',credential=None,deadline=10)
            self.assertEqual(caught.exception.status,302)
        with patch.object(t.http.client,'HTTPSConnection',side_effect=ssl.SSLError('bad certificate')):
            with self.assertRaises(t.TransportError):t.HttpsTransport(RELEASE['endpoint'])._request('POST','/v1/events',body=b'{}',credential=None,deadline=t.time.monotonic()+10)
    def test_worker_hard_deadline_terminates_stalled_dns_or_headers(self):
        import subprocess
        import sys
        import time
        original=subprocess.Popen
        def stalled(*args,**kw):return original([sys.executable,'-c','import time; time.sleep(30)'],**kw)
        start=time.monotonic()
        with patch.object(t.subprocess,'Popen',stalled):
            with self.assertRaises(t.TransportError):
                t.HttpsTransport(RELEASE['endpoint']).request('POST','/v1/events',body=b'{}',credential=None,deadline=start+.15)
        self.assertLess(time.monotonic()-start,1)
