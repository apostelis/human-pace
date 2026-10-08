import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from remote_test_support import NOW, RELEASE, analytics, pc
import pace_remote_store as r
import pace
import inject
import preview
class IntegrationTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'analytics';self.local=analytics.AnalyticsStore(self.root);self.remote=r.RemoteStore(self.root)
        for p in [patch.dict(os.environ,{'HUMAN_PACE_ANALYTICS_DIR':str(self.root),'HUMAN_PACE_CONFIG':str(Path(tmp.name)/'config.json')}),patch.object(r,'RELEASE',RELEASE)]:
            p.start();self.addCleanup(p.stop)
    def enable(self):self.remote.enable(now=NOW,local_enabled=True,release=RELEASE)
    def record_prompt(self):return self.local.observe(event='UserPromptSubmit',cfg=pc.defaults(),config_source='commands',session_id='session',now=NOW)
    def test_default_local_recording_does_not_queue(self):
        self.assertTrue(self.record_prompt());self.assertFalse((self.root/'remote').exists())
    def test_successful_recording_queues_and_local_off_stops_sharing(self):
        self.record_prompt();self.enable();self.record_prompt();self.record_prompt()
        body=json.loads(self.remote.preview(now=NOW));self.assertEqual(len([x for x in body['events'] if x['event']=='prompt_observed']),2)
        pace.run(['analytics','off'],now=NOW)
        self.assertFalse(self.remote.status(now=NOW)['enabled']);self.assertEqual(self.remote.status(now=NOW)['queued_count'],0)
        pace.run(['analytics','on'],now=NOW);self.assertFalse(self.remote.status(now=NOW)['enabled'])
    def test_clear_preserves_consent_and_notes_excluded(self):
        self.enable();pace.run(['rate','5','secret-note'],now=NOW)
        self.assertGreater(self.remote.status(now=NOW)['queued_count'],0)
        self.assertNotIn(b'secret-note',self.remote.preview(now=NOW))
        self.local.clear(now=NOW);self.assertEqual(self.remote.status(now=NOW)['queued_count'],0)
        self.assertTrue(self.remote.status(now=NOW)['enabled'])
    def test_controls_never_record_and_invitation_only_once(self):
        pace.run(['analytics','share','on'],now=NOW)
        self.assertTrue(self.remote.status(now=NOW)['enabled']);self.assertEqual(self.remote.status(now=NOW)['queued_count'],0)
        pace.run(['analytics','share','off'],now=NOW)
        self.assertFalse(self.remote.status(now=NOW)['enabled'])
    def test_queue_failure_does_not_break_local_recording(self):
        self.enable()
        with patch.object(r.RemoteStore,'enqueue_locked',side_effect=OSError('secret')):
            self.assertTrue(self.record_prompt())
        self.assertGreater(len(self.local.read(now=NOW,days=1)['events']),0)
    def test_session_invitation_once_and_skips_headless(self):
        hook={'hook_event_name':'SessionStart','session_id':'new-session'}
        def run(env=None):
            output=io.StringIO();inject.main(io.StringIO(json.dumps(hook)),output,env=env or {'HUMAN_PACE':'1'})
            return output.getvalue()
        self.assertIn('Help improve Human Pace',run())
        self.assertNotIn('Help improve Human Pace',run())
        self.assertNotIn('Help improve Human Pace',run({'HUMAN_PACE':'0'}))
    def test_settings_consent_route_and_foreign_request_rejection(self):
        import http.client
        import threading
        server=preview.create_server('token');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda: (server.shutdown(),server.server_close(),thread.join()))
        def request(action,origin=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            conn.request('POST','/token/sharing',json.dumps(action),headers)
            response=conn.getresponse();data=response.read();conn.close();return response.status,json.loads(data)
        status,_=request({'action':'enable'},'https://evil.test');self.assertEqual(status,403)
        status,_=request({'action':'enable'});self.assertEqual(status,200)
        self.assertTrue(self.remote.status(now=NOW)['enabled'])
        status,_=request({'action':'never','extra':'bad'});self.assertEqual(status,400)
        self.assertNotIn('Enable sharing',preview.render(pc.defaults()))
        page=preview.render(pc.defaults(),settings=True)
        self.assertIn('Enable sharing',page);self.assertIn('role="status"',page)
    def test_complete_collector_lifecycle_response_loss_and_delete_all_epochs(self):
        from collector.store import CollectorStore
        from collector.service import handle,Limiter
        from collector.maintenance import maintain
        from pace_remote_transport import upload,delete_all,TransportError
        collector=CollectorStore(self.root.parent/'collector.sqlite3',key=b'k'*32)
        limiter=Limiter();local=self
        class Adapter:
            def __init__(self):self.drop=True
            def request(self,method,path,*,body,credential,deadline):
                headers={'Content-Type':'application/json','Content-Length':str(len(body))}
                if credential:headers['Authorization']='Bearer '+credential
                status,head,raw=handle(collector,method,path,headers=headers,body=body,now=NOW,limiter=limiter)
                if status!=200:raise TransportError('http',status=status)
                if path=='/v1/events' and self.drop:self.drop=False;raise ConnectionError()
                return json.loads(raw)
        transport=Adapter();self.record_prompt();self.enable();self.record_prompt()
        self.assertEqual(upload(self.remote,transport,now=NOW)['state'],'retry')
        from datetime import timedelta
        result=upload(self.remote,transport,now=NOW+timedelta(minutes=2))
        self.assertEqual(result['duplicate'],1)
        self.assertEqual(len(collector.live_events(start=NOW.date(),end=NOW.date())),1)
        self.remote.disable(now=NOW);self.enable();self.record_prompt()
        upload(self.remote,transport,now=NOW)
        self.assertEqual(delete_all(self.remote,transport,now=NOW)['pending'],2)
        self.assertEqual(collector.live_events(start=NOW.date(),end=NOW.date()),[])
        maintain(collector,collector.journal,now=NOW)
        self.assertEqual(delete_all(self.remote,transport,now=NOW)['completed'],2)
        self.assertEqual(self.remote.status(now=NOW)['prior_identities'],0)
    def test_resumed_session_configuration_change_is_queued(self):
        self.enable();self.record_prompt()
        changed={**pc.defaults(),'length':300}
        self.local.observe(event='SessionStart',cfg=changed,config_source='commands',session_id='session',now=NOW)
        events=json.loads(self.remote.preview(now=NOW))['events']
        self.assertEqual(sum(e['event']=='config_observed_changed' for e in events),1)
