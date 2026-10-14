import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from remote_test_support import NOW, prompt
from collector.store import CollectorStore
from collector.service import handle, Limiter
from collector.server import create_server
class ServiceTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=CollectorStore(Path(tmp.name)/'events.sqlite3',key=b'k'*32)
        self.creds=self.store.register('a'*32,'b'*64,now=NOW);self.limiter=Limiter()
    def request(self,method,path,data=None,token=None,headers=None):
        body=json.dumps(data).encode() if data is not None else b''
        h={'Content-Type':'application/json','Content-Length':str(len(body))}
        if token:h['Authorization']='Bearer '+token
        h.update(headers or {})
        status,head,raw=handle(self.store,method,path,headers=h,body=body,now=NOW,limiter=self.limiter)
        return status,json.loads(raw)
    def test_ingestion_and_role_separation(self):
        data={'schema_version':1,'events':[prompt()]}
        status,out=self.request('POST','/v1/events',data,self.creds['ingestion_token']);self.assertEqual(status,200);self.assertEqual(len(out['accepted']),1)
        self.assertEqual(self.request('POST','/v1/events',data,self.creds['deletion_token'])[0],401)
    def test_bounds_envelope_schema_and_duplicate_ids(self):
        data={'schema_version':1,'events':[prompt()]*101}
        self.assertEqual(self.request('POST','/v1/events',data,self.creds['ingestion_token'])[0],413)
        self.assertEqual(self.request('POST','/v1/events',{'schema_version':2,'events':[]},self.creds['ingestion_token'])[0],426)
        event=prompt();self.assertEqual(self.request('POST','/v1/events',{'schema_version':1,'events':[event,event]},self.creds['ingestion_token'])[0],400)
    def test_bad_media_encoding_length_and_raw_json(self):
        for headers in ({'Content-Type':'text/plain'},{'Content-Encoding':'gzip'},{'Transfer-Encoding':'chunked'},{'Content-Length':'-1'}):
            self.assertEqual(self.request('POST','/v1/events',{},self.creds['ingestion_token'],headers)[0],400)
        raw=b'{"schema_version":1,"schema_version":2,"events":[]}'
        status,_,out=handle(self.store,'POST','/v1/events',headers={'Content-Type':'application/json','Content-Length':str(len(raw))},body=raw,now=NOW,limiter=self.limiter)
        self.assertEqual(status,400);self.assertNotIn(b'schema_version',out)
    def test_rate_limit_bounded_and_no_public_reports(self):
        limiter=Limiter(clock=lambda:0)
        for _ in range(20):self.assertTrue(limiter.allow('ingress',rate=10,burst=20))
        self.assertFalse(limiter.allow('ingress',rate=10,burst=20))
        self.assertEqual(self.request('GET','/v1/report')[0],404)
    def test_http_adapter_bounded_localhost(self):
        server=create_server(self.store,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        body=json.dumps({'installation_id':'c'*32,'recovery_key':'d'*64})
        conn.request('POST','/v1/registrations',body,{'Content-Type':'application/json'})
        response=conn.getresponse();self.assertEqual(response.status,200);data=json.loads(response.read());conn.close()
        self.assertEqual(data['installation_id'],'c'*32)
